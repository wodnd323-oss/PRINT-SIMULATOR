"""Independent V11 math verification. From the application folder, run:

runtime\\python\\python.exe -X utf8 verification_sources/verify_math_v11.py

Writes state/verification_math_v11.json and temporary gradient previews in exports.
Does not change the active calibration. Results refer to default_calibration.json."""
import sys,json
from pathlib import Path
B=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent.parent
sys.path.insert(0,str(B))
import numpy as np
from PIL import Image,ImageCms
from color_model import PhotoModel,rgb_to_lab,lab_to_rgb,SRGB
from prediction import Predictor,image
from inverse_color import inverse_color
from inverse_gradient import inverse_gradient,_quantized_ramp,_curve,_analyze
D=json.loads((B/'default_calibration.json').read_text('utf8'));m=PhotoModel(D)
old={};exec((B/'reference_archive/library_v10_color_model.py').read_text('utf8'),old)
# Keep old anchors fixed when isolating the neutral-gate code change.
original_doc=json.loads((B/'reference_archive/library_v10_calibration.json').read_text('utf8'))
old_model=old['PhotoModel'](original_doc);new_gate_model=PhotoModel(original_doc)
pairs=lab_to_rgb([[50,8-1e-6,0],[50,8+1e-6,0]])
delta=lambda p:float(np.linalg.norm(rgb_to_lab(p[1])-rgb_to_lab(p[0])))
old_jump=delta(old_model.transform(pairs));new_jump=delta(new_gate_model.transform(pairs));assert new_jump<1e-4 and old_jump>1
assert np.max(np.abs(old_model.transform([a['source_rgb'] for a in original_doc['anchors']])-new_gate_model.transform([a['source_rgb'] for a in original_doc['anchors']])))<1e-8
gray=np.arange(256)[:,None].repeat(3,axis=1);assert np.array_equal(np.rint(m.transform(gray)),gray)
colors=np.random.default_rng(826).integers(0,256,(10000,3))
assert np.max(np.abs(lab_to_rgb(rgb_to_lab(colors))-colors))<1e-8
assert np.array_equal(m.transform(colors,0),colors)
im=Image.fromarray(colors.astype('uint8').reshape(100,100,3));assert np.array_equal(np.array(m.apply(im)).reshape(-1,3),np.rint(m.transform(colors)).astype('uint8'))
invalid=0
icc=Predictor(D,1,'icc')
proof=ImageCms.buildProofTransformFromOpenProfiles(SRGB,SRGB,icc.profile,'RGB','RGB',renderingIntent=1,proofRenderingIntent=1,flags=ImageCms.Flags.BLACKPOINTCOMPENSATION|ImageCms.Flags.SOFTPROOFING)
proof_expected=np.asarray(ImageCms.applyTransform(image(colors),proof)).reshape(-1,3)
assert np.array_equal(icc.forward(colors)[0],proof_expected)
# Separated FOGRA ink retains its finite printed black on the display leg.
# BPC applies to source normalization/separation, not proof ink -> display.
cmyk_oracle=ImageCms.buildTransformFromOpenProfiles(icc.profile,SRGB,'CMYK','RGB',renderingIntent=1,flags=0)
ink_samples=np.random.default_rng(913).integers(0,256,(2048,4))
cmyk_expected=np.asarray(ImageCms.applyTransform(image(ink_samples,'CMYK'),cmyk_oracle)).reshape(-1,3)
assert np.array_equal(icc.forward(ink_samples,'CMYK')[0],cmyk_expected)
for point in [[float('nan'),0,0],[float('inf'),0,0],[-1,2,3],[256,2,3],[1,2]]:
 for fn in [m.transform,Predictor(D).forward]:
  try:fn([point])
  except ValueError:invalid+=1
  else:raise AssertionError(point)
for strength in [-1,float('nan'),1.1]:
 try:Predictor(D,strength)
 except ValueError:invalid+=1
 else:raise AssertionError(strength)
inverse_checks=[]
known_ramp=np.array([[199,124,42],[236,15,101]])
photo=Predictor(D)
old_tac=float(photo.forward(np.rint(_curve(known_ramp,np.linspace(0,1,513))))[2].sum(axis=1).max()*100/255)
exact_tac=float(photo.forward(_quantized_ramp(known_ramp))[2].sum(axis=1).max()*100/255)
assert exact_tac>old_tac
for mode in ['photo','icc']:
 p=Predictor(D,1,mode)
 for target,tac in [([0,0,0],100),([255,255,255],300),([0,255,0],300),([230,0,225],300),([47,103,135],400)]:
  r=inverse_color({'rgb':target,'model_mode':mode,'tac':tac},D)
  for key,input_mode in [('rgb_result','RGB'),('cmyk_result','CMYK')]:
   rec=r[key];point=rec['input_rgb'] if input_mode=='RGB' else np.rint(np.array(rec['cmyk'])*255/100)
   pred,_,ink=p.forward([point],input_mode)
   assert pred[0].tolist()==rec['predicted_rgb'];assert ink[0].sum()*100/255<=tac+1e-9
  inverse_checks.append({'mode':mode,'target':target,'tac':tac,'rgb_de':r['rgb_result']['delta_e76'],'cmyk_de':r['cmyk_result']['delta_e76']})
 print('inverse checks passed',mode,flush=True)
(B/'exports').mkdir(exist_ok=True);gradient_checks=[]
for mode in ['photo','icc']:
 file=B/'exports/math_regression_target.png';a=np.tile(np.linspace([70,115,170],[185,156,98],81).round().astype('uint8')[None,:,:],(12,1,1));Image.fromarray(a).save(file)
 r=inverse_gradient(file,{'model_mode':mode,'tac':300},D);p=Predictor(D,1,mode)
 for name in ['two_stop','three_stop']:
  rec=r[name]
  if rec is None:continue
  assert np.array_equal(p.forward(rec['input_samples'])[0],rec['predicted_samples'])
  source=np.array(Image.open(B/rec['input_preview']));actual=np.array(Image.open(B/rec['predicted_preview']));expected=p.forward(source.reshape(-1,3))[0].reshape(actual.shape)
  assert np.array_equal(actual,expected)
  if mode=='icc':
   upload_standard=np.asarray(ImageCms.applyTransform(image(source.reshape(-1,3)),proof)).reshape(actual.shape)
   assert np.array_equal(actual,upload_standard)
  all_ink=p.forward(_quantized_ramp([stop['input_rgb'] for stop in rec['stops']]))[2]
  assert all_ink.sum(axis=1).max()*100/255<=300+1e-9
  gradient_checks.append({'mode':mode,'stops':name,'mean_de':rec['mean_delta_e76'],'max_de':rec['max_delta_e76']})
# Independently synthesized A -> B -> A image: a whole-image first derivative
# cancels, but the correct diagonal is recoverable from local spatial changes.
yy,xx=np.meshgrid(np.arange(240),np.arange(360),indexing='ij')
t=(xx+yy)/(359+239);v=1-np.abs(2*t-1)
a=np.array([170,25,70]);b=np.array([240,220,180])
pixels=np.rint(a+(b-a)*v[...,None]).astype(np.uint8)
direction_file=B/'exports/math_symmetric_diagonal.png';Image.fromarray(pixels).save(direction_file)
target,axis,_,analysis=_analyze(direction_file,{})
expected_axis=np.array([359,239],dtype=float);expected_axis/=np.linalg.norm(expected_axis)
axis_cos=abs(float(axis@expected_axis));assert axis_cos>.9999
assert analysis['spatial_residual_delta_e76']<1.5
r=inverse_gradient(direction_file,{'model_mode':'photo','strength':0,'tac':400},D)
assert r['three_stop'] is not None
positions=np.linspace(0,1,33);idx=np.minimum((positions*2).astype(int),1);fraction=positions*2-idx
seed=target[[0,16,32]]
known_feasible=np.rint(seed[idx]*(1-fraction[:,None])+seed[idx+1]*fraction[:,None])
weights=np.ones(33);weights[[0,-1]]=2
def objective(values):
 de=np.linalg.norm(rgb_to_lab(values)-rgb_to_lab(target),axis=1)
 return float(np.average(de**2,weights=weights)+.2*np.max(de**2))
oracle_cost=objective(known_feasible);returned_cost=objective(r['three_stop']['predicted_samples'])
assert returned_cost<=oracle_cost+1e-9
report={'neutral_boundary_old_de76':old_jump,'neutral_boundary_new_de76':new_jump,'same_original_anchors_unchanged_by_gate':True,'neutral_256_pass':True,'lab_roundtrip_10000_pass':True,'image_forward_pixel_equality_10000_pass':True,'icc_upload_standard_matches_inverse_forward_10000':True,'icc_cmyk_relative_no_bpc_oracle_2048':True,'icc_gradient_matches_uploaded_standard':True,'tac_counterexample':{'old_513_percent':old_tac,'all_quantized_percent':exact_tac},'invalid_values_rejected':invalid,'inverse_checks':inverse_checks,'gradient_checks':gradient_checks,'symmetric_diagonal':{'axis_cosine':axis_cos,'residual_delta_e76':analysis['spatial_residual_delta_e76'],'feasible_seed_objective':oracle_cost,'returned_objective':returned_cost,'three_stop_mean_delta_e76':r['three_stop']['mean_delta_e76']}}
(B/'state').mkdir(exist_ok=True);(B/'state/verification_math_v11.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(report,ensure_ascii=False,indent=2))
