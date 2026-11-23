"""Reproduce one full-ramp TAC boundary using the unmodified released app.

Portable to bundled Windows Python. Needs stdlib, numpy and Pillow; no GS,
scipy, browser or server startup. Exit 0 means the audit completed, NOT that
no application finding was found. See finding_reproduced in the output JSON.
"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import hashlib, io, json, math, platform, time
import numpy as np
from PIL import Image, ImageCms

HERE=Path(__file__).resolve().parent
APP=HERE.parent/'released_app'
sys.path.insert(0,str(APP))
import inverse_gradient as g
from color_model import save_srgb

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
paths=['inverse_gradient.py','inverse_color.py','prediction.py','icc/GRACoL2013_CRPC6.icc']
before={name:sha(APP/name) for name in paths}
runtime=HERE/'runtime';(runtime/'exports').mkdir(parents=True,exist_ok=True);g.BASE=runtime
doc=json.loads((APP/'default_calibration.json').read_text(encoding='utf8'))
stops=np.array([[26,34,218],[140,116,2],[105,2,81]])
t=np.linspace(0,1,33)
# Define the fixture independently of the application's interpolation helper.
target=np.rint(np.stack([np.interp(t,[0,.5,1],stops[:,c]) for c in range(3)],axis=-1)).astype(np.uint8)
pixels=np.tile(target[np.rint(np.linspace(0,32,197)).astype(int)][None,:,:],(51,1,1))
fixture=HERE/'quantized_tac_197_target.png';save_srgb(Image.fromarray(pixels),fixture)
payload={'asset':'synthetic/quantized_tac_197_target.png','model_mode':'photo','strength':0,'tac':212.55}
started=time.monotonic()
sampled,axis,_,analysis=g._analyze(fixture,{})
response=g.inverse_gradient(fixture,payload,doc)
srgb=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
gracol=ImageCms.getOpenProfile(str(APP/'icc/GRACoL2013_CRPC6.icc'))
rows={}
for key in ('two_stop','three_stop'):
    record=response[key]
    if record is None:continue
    input_path=runtime/record['input_preview']
    with Image.open(input_path) as image:
        source=ImageCms.ImageCmsProfile(io.BytesIO(image.info['icc_profile']))
        rgb=np.asarray(image.convert('RGB')).copy()
        # Independent direct source-ICC -> GRACoL transform on the actual saved
        # input PNG; no Predictor.forward or application ink helper is used.
        ink=np.asarray(ImageCms.profileToProfile(image.convert('RGB'),source,gracol,outputMode='CMYK',renderingIntent=1,
                                                 flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)).copy()
    total=ink.astype(int).sum(axis=-1);y,x=np.unravel_index(int(np.argmax(total)),total.shape)
    chosen=np.asarray([s['input_rgb'] for s in record['stops']])
    enumerated=g._quantized_ramp(chosen)
    enumerated_image=Image.fromarray(enumerated.astype(np.uint8).reshape(1,-1,3))
    enumerated_ink=np.asarray(ImageCms.profileToProfile(enumerated_image,srgb,gracol,outputMode='CMYK',renderingIntent=1,
                                                        flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)).astype(int)
    bound=math.floor(payload['tac']*255/100+1e-8)
    rows[key]={'stops':chosen.tolist(),'reported_mean_delta_e76':record['mean_delta_e76'],
               'reported_max_ink_percent':record['max_ink_percent'],'enumerated_max_ink_codes':int(enumerated_ink.sum(-1).max()),
               'actual_saved_png_max_ink_codes':int(total.max()),'actual_saved_png_max_ink_percent':float(total.max()*100/255),
               'requested_tac_percent':payload['tac'],'allowed_ink_code_sum':bound,
               'pixels_exceeding_requested_limit':int((total>bound).sum()),'total_pixels':int(total.size),
               'offending_pixel_xy':[int(x),int(y)],'offending_rgb':rgb[y,x].tolist(),'offending_cmyk8':ink[y,x].tolist(),
               'offending_rgb_in_enumerator':bool(np.any(np.all(enumerated==rgb[y,x],axis=1))),
               'input_preview_path':str(input_path)}
three=rows.get('three_stop',{})
result={'audit_completed':True,'finding_reproduced':bool(three and three['actual_saved_png_max_ink_codes']>three['allowed_ink_code_sum']
                                                       and three['reported_max_ink_percent']<=payload['tac']),
        'scope':'Fractional TAC is accepted by the API. 212.55 is not one of the current UI select choices; no UI-limit violation is claimed.',
        'severity':'low','location':'inverse_gradient.py:15-31,169-186,225-230',
        'environment':{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__,'pillow':Image.__version__,
                       'lcms':ImageCms.core.littlecms_version},
        'payload':payload,'target_size':[197,51],'target_33_sample_max_difference':int(np.abs(sampled.astype(int)-target).max()),
        'analysis':analysis,'variants':rows,'product_sha256_before':before,
        'product_unchanged':{name:sha(APP/name)==value for name,value in before.items()},
        'elapsed_seconds':round(time.monotonic()-started,3)}
(HERE/'tac_boundary_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
(HERE/'quantized_tac_197_full_response.json').write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
