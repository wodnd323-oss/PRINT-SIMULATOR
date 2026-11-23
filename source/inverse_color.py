"""Discrete inverse search through the existing FOGRA39 and photo model."""
import hashlib,itertools,json,math,pathlib
import numpy as np
from PIL import Image,ImageCms
from color_model import PhotoModel,SRGB,rgb_to_lab
from reference_support import reference_support
BASE=pathlib.Path(__file__).resolve().parent

def _image(points,mode):
    values=np.asarray(points,dtype=np.uint8).reshape(1,-1,len(mode))
    return Image.frombytes(mode,(values.shape[1],1),values.tobytes())

def _search(points,forward,target_lab,extra=(),project=None):
    points=np.vstack([points,*extra]) if len(extra) else points
    def evaluate(p):
        p=np.clip(np.rint(p),0,255).astype(np.int16)
        if project is not None:p=project(p)
        p=np.unique(p,axis=0)
        predicted,_,_,valid=forward(p)
        score=np.linalg.norm(rgb_to_lab(predicted)-target_lab,axis=1)
        score=np.where(valid,score,np.inf)
        return p,score
    p,score=evaluate(points);best=p[np.argsort(score,kind='stable')[:16]]
    dimensions=p.shape[1];directions=[np.zeros(dimensions,dtype=int)]
    for axes in itertools.chain(itertools.combinations(range(dimensions),1),itertools.combinations(range(dimensions),2)):
        for signs in itertools.product((-1,1),repeat=len(axes)):
            d=np.zeros(dimensions,dtype=int);d[list(axes)]=signs;directions.append(d)
    directions=np.asarray(directions)
    for step in (32,16,8,4,2,1):
        for _ in range(5):
            candidate=(best[:,None,:]+directions[None,:,:]*step).reshape(-1,dimensions)
            p,score=evaluate(candidate);order=np.argsort(score,kind='stable')[:16]
            updated=p[order]
            if np.array_equal(updated,best):break
            best=updated
    p,score=evaluate(best);index=int(np.argmin(score))
    if not math.isfinite(float(score[index])):raise ValueError('현재 잉크량 제한 안에서 후보를 찾지 못했습니다.')
    return p[index],float(score[index])

def inverse_color(payload,document):
    rgb=payload.get('rgb')
    if not isinstance(rgb,list) or len(rgb)!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=255 for v in rgb):
        raise ValueError('목표 RGB는 각각 0~255 사이로 입력해 주세요.')
    strength=float(payload.get('strength',1));tac=float(payload.get('tac',300))
    if not math.isfinite(strength) or not 0<=strength<=1:raise ValueError('반영 강도는 0~1 사이여야 합니다.')
    if not math.isfinite(tac) or not 100<=tac<=400:raise ValueError('총 잉크량 상한은 100~400%여야 합니다.')
    rgb=np.rint(rgb).astype(int);target_lab=rgb_to_lab(rgb)
    model=PhotoModel(document);limit=int(math.floor(tac*255/100+1e-8))
    from prediction import Predictor,gamut_flags
    mode=payload.get('model_mode','photo')
    if mode=='icc':strength=0.
    predictor=Predictor(document,strength,mode)
    to_ink=predictor.to_ink
    def forward(points,input_mode='CMYK'):
        predicted,baseline,cmyk=predictor.forward(points,input_mode)
        return predicted,baseline,cmyk,cmyk.sum(axis=1)<=limit
    def project(points):
        factor=np.minimum(1,limit/np.maximum(points.sum(axis=1),1))
        return np.floor(points*factor[:,None]+1e-8).astype(int)
    levels=np.rint(np.linspace(0,255,9)).astype(int)
    cgrid=np.array(list(itertools.product(levels,repeat=4)))
    seed=np.asarray(ImageCms.applyTransform(_image([rgb],'RGB'),to_ink)).reshape(-1,4)
    cpoint,cdelta=_search(cgrid,forward,target_lab,extra=(seed,),project=project)
    cp,base,cink,_=forward([cpoint])
    rgrid=np.array(list(itertools.product(levels,repeat=3)))
    rpoint,rdelta=_search(rgrid,lambda p:forward(p,'RGB'),target_lab,extra=(np.vstack([base,rgb]),))
    rp,rbase,rink,_=forward([rpoint],'RGB')
    def record(point,predicted,baseline,ink,delta,kind):
        distance=float(model.nearest(baseline)[0])
        percentages=(np.floor(ink[0]*10000/255)/100).tolist()
        return {'input_rgb':point.tolist() if kind=='rgb' else baseline[0].tolist(),
                'cmyk':percentages,'predicted_rgb':predicted[0].tolist(),
                'baseline_rgb':baseline[0].tolist(),'delta_e76':round(delta,2),
                'total_ink_percent':round(sum(percentages),2),
                'near_reference':distance<=12,'distance_from_reference':round(distance,2),
                'reference_support':reference_support(model,baseline) if mode=='photo' else None}
    cresult=record(cpoint,cp,base,cink,cdelta,'cmyk')
    rresult=record(rpoint,rp,rbase,rink,rdelta,'rgb')
    gamut_warning=bool(gamut_flags([rgb])[0])
    assessment='difficult' if cdelta>5 else 'gamut_warning' if gamut_warning else 'close' if cdelta<=2 else 'approximate'
    return {'target_rgb':rgb.tolist(),'cmyk_result':cresult,'rgb_result':rresult,
            'assessment':assessment,'icc_gamut_warning':gamut_warning,'strength':strength,'tac_limit':tac,'model_mode':mode,'input_cmyk_profile':predictor.input_profile,
            'model_name':document.get('name'),'calibration_sha256':hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest(),
            'metric':'Delta E 76, sRGB-derived D65 Lab','thresholds':{'close':2,'approximate':5},
            'scope':'Source sRGB photo estimate OR separate FOGRA39 proof; numerical candidates, not measured print validation. CMYK output must be tagged with input_cmyk_profile.'}
