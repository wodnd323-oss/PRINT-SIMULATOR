"""Fresh V11.2 inverse/geometry audit; writes only next to this script.

The released application is read only. No server import or browser execution.
The actual OS is recorded at runtime. Pure server functions are compiled from
AST to avoid startup writes.
"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import ast, hashlib, io, json, math, platform, time
import numpy as np
from PIL import Image, ImageCms

HERE = Path(__file__).resolve().parent
APP = HERE.parent / 'released_app'
sys.path.insert(0, str(APP))
import inverse_gradient as gradient
from inverse_color import inverse_color
from prediction import Predictor
from color_model import save_srgb

RUNTIME = HERE / 'runtime'
(RUNTIME / 'exports').mkdir(parents=True, exist_ok=True)
gradient.BASE = RUNTIME
DOC = json.loads((APP / 'default_calibration.json').read_text(encoding='utf8'))
STARTED = time.monotonic()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
PRODUCTS = ['inverse_color.py','inverse_gradient.py','prediction.py','color_model.py','server.py','proof_rgb_image.py','default_calibration.json']
BEFORE = {name:sha(APP/name) for name in PRODUCTS}
RESULT = {'environment': {'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,
                          'pillow':Image.__version__,'lcms':ImageCms.core.littlecms_version},
          'scope':f'Published V11.2; no product edits or browser execution; actual platform {sys.platform}; fresh risk-based cases.',
          'product_sha256_before':BEFORE, 'tests':{}, 'findings':[]}

def independent_lab(rgb):
    """Explicit D65 sRGB/Lab oracle, independent of application helpers."""
    encoded = np.asarray(rgb,dtype=float)/255
    linear = np.where(encoded<=0.04045,encoded/12.92,((encoded+0.055)/1.055)**2.4)
    xyz = linear @ np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]]).T
    q = xyz/np.array([.95047,1.,1.08883])
    f = np.where(q>(6/29)**3,np.cbrt(q),q/(3*(6/29)**2)+4/29)
    return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),axis=-1)

def de(a,b): return np.linalg.norm(independent_lab(a)-independent_lab(b),axis=-1)
def read(path):
    with Image.open(path) as im: return np.asarray(im).copy()
def maxdiff(a,b): return float(np.max(np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float))))
def write_result():
    (HERE/'inverse_geometry_results.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2),encoding='utf8')
def record(name,data):
    RESULT['tests'][name]=data;write_result();print(name,json.dumps(data,ensure_ascii=False)[:700],flush=True)

def render_target(name, width, height, stops, positions=None, direction='x'):
    knots = np.asarray(positions if positions is not None else np.linspace(0,1,len(stops)))
    yy,xx=np.meshgrid(np.linspace(0,1,height),np.linspace(0,1,width),indexing='ij')
    t = xx if direction=='x' else yy if direction=='y' else ((xx*(width-1)+yy*(height-1))/(width+height-2))
    values=np.asarray(stops)
    a=np.stack([np.interp(t,knots,values[:,c]) for c in range(3)],axis=-1)
    path=HERE/name;save_srgb(Image.fromarray(np.rint(a).astype(np.uint8)),path);return path

def actual_curve(stops,t):
    values=np.asarray(stops,dtype=float);knots=np.linspace(0,1,len(values))
    return np.rint(np.stack([np.interp(t,knots,values[:,c]) for c in range(3)],axis=-1)).astype(int)

def float_boundary_states(stops):
    """Global t interpolation, including both representable neighbours of crossings."""
    values=np.asarray(stops,dtype=int);segments=len(values)-1;t=[0.,1.]
    for k,(a,b) in enumerate(zip(values[:-1],values[1:])):
        for c in range(3):
            if b[c]!=a[c]:
                cuts=(((np.arange(min(a[c],b[c]),max(a[c],b[c]))+.5-a[c])/(b[c]-a[c]))+k)/segments
                t.extend(cuts);t.extend(np.nextafter(cuts,0));t.extend(np.nextafter(cuts,1))
    t=np.unique(np.r_[t,np.linspace(0,1,4097)])
    states=actual_curve(values,t)
    return t,states

# Compile only the actual pure function bodies; importing server would create
# application state directories and initialize user calibration.
server_tree=ast.parse((APP/'server.py').read_text(encoding='utf8'))
namespace={'BASE':RUNTIME,'model_doc':lambda:DOC,'hashlib':hashlib,'json':json}
for name in ('color_sample','safe_asset'):
    node=next(node for node in server_tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(APP/'server.py'),'exec'),namespace)
api_color=namespace['color_sample']

# Displayed percentages and RGB integers are checked by the real API function,
# plus an independent Delta E calculation and the quantized TAC contract.
single_cases=[('photo',1.,300,[50,86,120]),('photo',1.,300,[0,185,65]),
              ('photo',.37,280.01,[254,1,254]),('photo',1.,100,[0,0,0]),
              ('icc',.75,299.99,[32,32,32]),('icc',0.,400,[255,0,0])]
single_rows=[]
for mode,strength,tac,target in single_cases:
    output=inverse_color({'rgb':target,'model_mode':mode,'strength':strength,'tac':tac},DOC)
    expected_strength=0. if mode=='icc' else strength
    row={'mode':mode,'strength':expected_strength,'target':target,'tac':tac,'records':{}}
    for kind,key in [('cmyk','cmyk_result'),('rgb','rgb_result')]:
        candidate=output[key]
        payload={kind:candidate['cmyk'] if kind=='cmyk' else candidate['input_rgb'],
                 'model_mode':mode,'strength':expected_strength,'calibration_sha256':output['calibration_sha256']}
        got=api_color(payload)
        delta=round(float(de(got['matched_rgb'],target)),2)
        codes=np.rint(np.asarray(candidate['cmyk'])*255/100).astype(int)
        row['records'][kind]={'input':payload[kind],'reported_rgb':candidate['predicted_rgb'],'actual_api_rgb':got['matched_rgb'],
                              'reported_delta':candidate['delta_e76'],'independent_delta':delta,
                              'quantized_ink_codes':codes.tolist(),'quantized_tac':float(codes.sum()*100/255),
                              'pass':got['matched_rgb']==candidate['predicted_rgb'] and delta==candidate['delta_e76']
                                     and int(codes.sum())<=math.floor(tac*255/100+1e-8)
                                     and got['input_cmyk_profile']==output['input_cmyk_profile']}
    original=api_color({'rgb':target,'model_mode':mode,'strength':expected_strength})
    original_ink=np.rint(np.asarray(original['cmyk'])*255/100).astype(int).sum()
    if original_ink<=math.floor(tac*255/100+1e-8):
        row['raw_rgb_target_error']=float(de(original['matched_rgb'],target))
        row['recommended_rgb_not_worse_than_feasible_raw_target']=output['rgb_result']['delta_e76']<=row['raw_rgb_target_error']+.005
    row['pass']=all(x['pass'] for x in row['records'].values()) and row.get('recommended_rgb_not_worse_than_feasible_raw_target',True)
    single_rows.append(row)
record('displayed_single_color_roundtrip',{'pass':all(x['pass'] for x in single_rows),'cases':single_rows})
try:
    api_color({'rgb':[20,40,60],'model_mode':'photo','strength':1,'calibration_sha256':'stale'})
    stale=False
except ValueError:stale=True
record('stale_calibration_contract',{'pass':stale})

# A narrow perpendicular gradient is a concrete risk of isotropic thumbnailing.
thin_cases=[('thin_default',1800,8,1.),('thin_identity',1800,8,0.),('coarse_short_axis',1000,10,0.),('normal_aspect_control',600,60,0.)]
for name,w,h,strength in thin_cases:
    path=render_target(name+'.png',w,h,[[5,92,124],[205,30,40]],direction='y')
    target,axis,preview,analysis=gradient._analyze(path,{})
    payload={'asset':'synthetic/'+path.name,'model_mode':'photo','strength':strength,'tac':300}
    output=gradient.inverse_gradient(path,payload,DOC)
    predicted=read(RUNTIME/output['two_stop']['predicted_preview'])
    desired=read(RUNTIME/output['target_preview'])
    errors=de(predicted,desired)
    data={'input_size':[w,h],'payload':payload,'analysis':analysis,'target_unique_rgb':np.unique(target,axis=0).tolist(),
          'reported_33_sample_mean':output['two_stop']['mean_delta_e76'],'reported_33_sample_max':output['two_stop']['max_delta_e76'],
          'actual_stored_png_mean_delta_e76':float(errors.mean()),'actual_stored_png_max_delta_e76':float(errors.max()),
          'comparison_uses':'Independent D65 Lab oracle on the stored target.png and two_predicted.png at identical dimensions.',
          'target_png':str(RUNTIME/output['target_preview']),'predicted_png':str(RUNTIME/output['two_stop']['predicted_preview']),
          'recommended_stops':[s['input_rgb'] for s in output['two_stop']['stops']],
          'expected_axis':'vertical','measured_axis':axis.tolist(),'three_stop_returned':output['three_stop'] is not None}
    (HERE/(name+'_full_response.json')).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    record(name,data)
RESULT['findings'].append({'id':'IG-01','severity':'medium','title':'A very short image/rectangle axis is averaged away before gradient analysis.',
                          'location':'inverse_gradient.py:59-65,89-106',
                          'reproduction':'1800x8 vertical sRGB ramp [5,92,124] -> [205,30,40], auto, photo, strength 0 or 1, TAC300.',
                          'scope':'Both auto and rect use the same thumbnail path. The UI honestly labels the reported errors as 33 samples, but the samples have collapsed to the wrong constant color and the inferred direction is wrong.'})

# Reversal and selected-point geometry are checked directly against a second
# independently sampled image implementation, without the solver in the way.
diagonal=render_target('physical_diagonal.png',241,97,[[20,40,80],[180,200,220]],direction='diagonal')
points=[[20,15],[221,80]]
forward,_,_,info=gradient._analyze(diagonal,{'line':points})
reverse,_,_,reverse_info=gradient._analyze(diagonal,{'line':points[::-1]})
im=read(diagonal);expected=[]
for t in np.linspace(0,1,33):
    x,y=np.rint(np.asarray(points[0])*(1-t)+np.asarray(points[1])*t).astype(int)
    expected.append(np.median(im[max(y-2,0):min(y+3,im.shape[0]),max(x-2,0):min(x+3,im.shape[1])].reshape(-1,3),axis=0))
_,_,_,auto_info=gradient._analyze(diagonal,{})
record('line_reversal_and_physical_angle',{'pass':maxdiff(forward,np.rint(expected))==0 and maxdiff(forward,reverse[::-1])==0 and abs(auto_info['css_angle']-135)<.2,
                                         'manual_33_sample_max_difference':maxdiff(forward,np.rint(expected)),
                                         'reversed_sample_max_difference':maxdiff(forward,reverse[::-1]),
                                         'forward_metadata':info,'reverse_metadata':reverse_info,'auto_diagonal_metadata':auto_info})

# Target ICC/alpha are interpreted before extraction. Compare against a
# separately normalized source image, not another call to read_image_srgb.
a98=ImageCms.getOpenProfile(str(APP/'runtime/ghostscript/iccprofiles/a98.icc'))
srgb=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
base=np.tile(np.rint(np.linspace([0,255,80],[180,40,220],101)).astype(np.uint8)[None,:,:],(21,1,1))
rgb=Image.fromarray(base)
converted=ImageCms.profileToProfile(rgb,a98,srgb,outputMode='RGB',renderingIntent=1,flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
icc_rows=[]
for transparent in (False,True):
    label='a98_alpha' if transparent else 'a98_opaque';path=HERE/(label+'.png')
    if transparent:
        alpha=np.tile(np.rint(np.linspace(0,255,101)).astype(np.uint8),(21,1));source=rgb.convert('RGBA');source.putalpha(Image.fromarray(alpha))
        layer=converted.convert('RGBA');layer.putalpha(Image.fromarray(alpha));oracle=Image.alpha_composite(Image.new('RGBA',rgb.size,'white'),layer).convert('RGB')
    else:source=rgb;oracle=converted
    source.save(path,icc_profile=a98.tobytes());oracle_path=HERE/(label+'_normalized.png');save_srgb(oracle,oracle_path)
    p={'line':[[2,10],[98,10]]}
    actual=gradient._analyze(path,p)[0];expected=gradient._analyze(oracle_path,p)[0]
    icc_rows.append({'kind':label,'maximum_target_sample_difference':maxdiff(actual,expected),'pass':maxdiff(actual,expected)==0})
record('target_icc_and_alpha',{'pass':all(x['pass'] for x in icc_rows),'cases':icc_rows})

# Known linear and nonlinear target shapes exercise both candidate counts,
# exact displayed stop reconstruction, constraints and fixed 50% middle stop.
gradient_cases=[('encoded_linear',[[0,0,0],[255,255,255]],None,'photo',0.,400),
                ('symmetric_three',[[20,60,120],[220,210,30],[20,60,120]],None,'photo',0.,400),
                ('unequal_knot_25_percent',[[20,60,120],[220,210,30],[20,60,120]],[0,.25,1],'photo',0.,400),
                ('dark_tac_100',[[2,8,32],[10,50,90]],None,'photo',1.,100),
                ('icc_diagonal_stops',[[50,10,80],[20,160,100]],None,'icc',0.,270.01)]
gradient_rows=[]
for name,stops,knots,mode,strength,tac in gradient_cases:
    path=render_target(name+'.png',201,51,stops,knots)
    payload={'asset':'synthetic/'+path.name,'model_mode':mode,'strength':strength,'tac':tac}
    output=gradient.inverse_gradient(path,payload,DOC)
    sampled=gradient._analyze(path,payload)[0]
    predictor=Predictor(DOC,strength,mode)
    rows={}
    for key in ('two_stop','three_stop'):
        variant=output[key]
        if variant is None:continue
        chosen=[stop['input_rgb'] for stop in variant['stops']]
        independent_input=actual_curve(chosen,np.linspace(0,1,33))
        predictions=predictor.forward(independent_input,'RGB')[0]
        errors=de(predictions,sampled)
        _,states=float_boundary_states(chosen)
        ink=predictor.forward(np.unique(states,axis=0),'RGB')[2]
        max_ink=int(ink.sum(1).max())
        actual_input=read(RUNTIME/variant['input_preview'])
        actual_output=read(RUNTIME/variant['predicted_preview'])
        preview_pred=predictor.forward(actual_input.reshape(-1,3),'RGB')[0].reshape(actual_output.shape)
        rows[key]={'stops':chosen,'positions_percent':[s['position_percent'] for s in variant['stops']],
                   'sample_input_max_difference':maxdiff(independent_input,variant['input_samples']),
                   'sample_prediction_max_difference':maxdiff(predictions,variant['predicted_samples']),
                   'stored_preview_prediction_max_difference':maxdiff(preview_pred,actual_output),
                   'mean_delta_independent':float(errors.mean()),'reported_mean':variant['mean_delta_e76'],
                   'max_delta_independent':float(errors.max()),'reported_max':variant['max_delta_e76'],
                   'weighted_search_objective':float(np.average(errors**2,weights=np.r_[2,np.ones(31),2])+.2*max(errors**2)),
                   'independent_global_boundary_max_ink_percent':max_ink*100/255,'reported_max_ink_percent':variant['max_ink_percent'],
                   'pass':maxdiff(independent_input,variant['input_samples'])==0 and maxdiff(predictions,variant['predicted_samples'])==0
                          and maxdiff(preview_pred,actual_output)==0 and round(float(errors.mean()),2)==variant['mean_delta_e76']
                          and round(float(errors.max()),2)==variant['max_delta_e76'] and max_ink<=math.floor(tac*255/100+1e-8)}
    gradient_rows.append({'name':name,'payload':payload,'interpolation':output['interpolation'],'variants':rows,
                          'pass':all(v['pass'] for v in rows.values())})
    (HERE/(name+'_full_response.json')).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
record('gradient_stops_predictions_and_tac',{'pass':all(x['pass'] for x in gradient_rows),'cases':gradient_rows,
                                          'encoded_black_white_half_code':actual_curve([[0]*3,[255]*3],np.array([.5]))[0].tolist(),
                                          'linear_light_half_code_for_contrast':[188,188,188]})

# A truly two-dimensional target should be treated as a limitation and flagged,
# not conflated with the short-axis loss of a perfectly linear input above.
yy,xx=np.meshgrid(np.linspace(-1,1,91),np.linspace(-1,1,91),indexing='ij')
t=np.minimum(np.sqrt(xx**2+yy**2),1)
radial=np.rint(np.array([20,60,120])*(1-t[...,None])+np.array([220,210,30])*t[...,None]).astype(np.uint8)
path=HERE/'radial_target.png';save_srgb(Image.fromarray(radial),path)
_,_,_,analysis=gradient._analyze(path,{})
record('nonlinear_2d_target_limitation',{'analysis':analysis,'ui_warning_condition_met':analysis['spatial_residual_delta_e76']>5,
                                     'interpretation':'33 color samples do not measure whole-image agreement; this genuinely 2D target triggers the existing mixed-region warning.'})

RESULT['product_unchanged']={name:sha(APP/name)==before for name,before in BEFORE.items()}
RESULT['elapsed_seconds']=round(time.monotonic()-STARTED,3)
write_result()
print(json.dumps({'product_unchanged':all(RESULT['product_unchanged'].values()),'elapsed_seconds':RESULT['elapsed_seconds'],
                  'recorded_test_groups':len(RESULT['tests']),'findings':RESULT['findings']},ensure_ascii=False),flush=True)
