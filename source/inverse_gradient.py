"""Read a target gradient and jointly fit printable RGB gradient stops."""
import hashlib,json,math,pathlib
import numpy as np
from PIL import Image,ImageCms
from color_model import PhotoModel,SRGB,rgb_to_lab,save_srgb
from inverse_color import inverse_color,_image
from proof_rgb_image import read_image_srgb
from reference_support import reference_support
BASE=pathlib.Path(__file__).resolve().parent

def _curve(stops,positions):
    stops=np.asarray(stops,dtype=float);knots=np.linspace(0,1,len(stops))
    return np.stack([np.interp(positions,knots,stops[:,c]) for c in range(3)],axis=-1)

def _quantized_ramp(stops):
    """Enumerate 8-bit RGB states, including half-code transition boundaries.

    Fixed-distance samples can skip short-lived combinations of channel codes.
    The path is piecewise constant after rounding; its transitions occur at
    each channel's half-integer crossings. Boundary neighbours conservatively
    include floating-point interpolation/tie-rounding variants.
    """
    stops=np.asarray(stops,dtype=int);segments=[]
    for a,b in zip(stops[:-1],stops[1:]):
        delta=b-a;cuts=[0.,1.]
        for c in range(3):
            if delta[c]:cuts.extend(((np.arange(min(a[c],b[c]),max(a[c],b[c]))+.5-a[c])/delta[c]).tolist())
        cuts=np.unique(cuts)
        positions=np.r_[cuts,(cuts[:-1]+cuts[1:])/2,np.clip(cuts-1e-12,0,1),np.clip(cuts+1e-12,0,1)]
        segments.append(np.rint(a+positions[:,None]*delta).astype(int))
    return np.unique(np.vstack(segments),axis=0)

def _analyze(filename,payload):
    im,_=read_image_srgb(filename)
    w,h=im.size;line=payload.get('line');rect=payload.get('rect')
    geometry={'source_image_size':[w,h],'source_coordinate_system':'pixel centers; origin top-left; x right; y down','css_angle_convention':'0 degrees up; 90 degrees right; clockwise'}
    if line is not None:
        p=np.asarray(line,dtype=float)
        if p.shape!=(2,2) or not np.isfinite(p).all() or np.linalg.norm(p[1]-p[0])<4:raise ValueError('그라데이션의 서로 떨어진 두 위치를 선택해 주세요.')
        if (p[:,0]<0).any() or (p[:,0]>=w).any() or (p[:,1]<0).any() or (p[:,1]>=h).any():raise ValueError('선택 위치가 이미지 밖에 있습니다.')
        colors=[]
        for t in np.linspace(0,1,33):
            x,y=np.rint(p[0]*(1-t)+p[1]*t).astype(int)
            patch=np.asarray(im.crop((max(0,x-2),max(0,y-2),min(w,x+3),min(h,y+3)))).reshape(-1,3)
            colors.append(np.median(patch,axis=0))
        target=np.rint(colors).astype(int);axis=np.array([1.,0.]);preview=Image.fromarray(np.tile(_curve(target,np.linspace(0,1,700)).astype(np.uint8)[None,:,:],(180,1,1)))
        info={'selection':'line','start_label':'선택한 1번 위치','end_label':'선택한 2번 위치','direction':'선택한 1번 → 2번 위치','style':'선택한 두 위치의 방향','css_angle':None,'source_points':p.tolist(),'spatial_residual_delta_e76':0}
        dx,dy=p[1]-p[0]
        info.update(geometry)
        info.update({'source_points_normalized':(p/np.array([max(w-1,1),max(h-1,1)])).tolist(),'source_points_normalization':'x/(width-1), y/(height-1); a singleton axis uses denominator 1','source_line_css_angle':round(math.degrees(math.atan2(dx,-dy))%360,4),'source_line_angle_scope':'Direction of selected source points only; not an inferred whole-area gradient angle','preview_css_angle':90.0,'line_sample_count':33,'line_sampling':'rounded pixel center; median of clipped 5x5 neighborhood'})
        return target,axis,preview,info
    bounds=[0,0,w,h]
    if rect is not None:
        values=np.asarray(rect,dtype=float)
        if values.shape!=(4,) or not np.isfinite(values).all():raise ValueError('선택 영역이 올바르지 않습니다.')
        x0,x1=sorted([int(values[0]),int(values[2])]);y0,y1=sorted([int(values[1]),int(values[3])])
        if not(0<=x0<x1<=w and 0<=y0<y1<=h) or x1-x0<4 or y1-y0<4:raise ValueError('이미지 안에서 조금 더 넓은 영역을 선택해 주세요.')
        bounds=[x0,y0,x1,y1]
    crop=im.crop(tuple(bounds));thumb=crop.copy();thumb.thumbnail((180,180))
    a=np.asarray(thumb,dtype=float);hh,ww=a.shape[:2]
    yy,xx=np.meshgrid(np.linspace(0,1,hh),np.linspace(0,1,ww),indexing='ij')
    coordinates=np.stack([np.ones_like(xx),xx,yy],axis=-1).reshape(-1,3);pixels=a.reshape(-1,3)
    coefficients=np.linalg.lstsq(coordinates,pixels,rcond=None)[0]
    plane=np.clip(coordinates@coefficients,0,255)
    plane_error=float(np.mean(np.linalg.norm(rgb_to_lab(plane)-rgb_to_lab(pixels),axis=1)))
    gradient=coefficients[1:,:];_,singular,vt=np.linalg.svd(gradient.T,full_matrices=False)
    orientation_method='RGB plane slope'
    if plane_error<=1.5 and singular[0]>1:axis=vt[0]
    else:
        # A symmetric A -> B -> A gradient has zero whole-image slope. Local
        # derivatives still share its direction: their outer products preserve
        # that direction when the color derivative reverses sign. Smooth in
        # float to suppress 8-bit staircase noise without quantizing again.
        padded=np.pad(a,((0,0),(1,1),(0,0)),mode='edge')
        smooth=(padded[:,:-2]+2*padded[:,1:-1]+padded[:,2:])/4
        padded=np.pad(smooth,((1,1),(0,0),(0,0)),mode='edge')
        smooth=(padded[:-2]+2*padded[1:-1]+padded[2:])/4
        gx=np.gradient(smooth,axis=1)*(ww-1) if ww>1 else np.zeros_like(smooth)
        gy=np.gradient(smooth,axis=0)*(hh-1) if hh>1 else np.zeros_like(smooth)
        field=np.stack([gx,gy],axis=-1)
        if hh>4:field=field[2:-2]
        field=field[:,2:-2] if ww>4 else field
        field=field.reshape(-1,2)
        values,vectors=np.linalg.eigh(field.T@field/max(len(field),1))
        if values[-1]>1:
            axis=vectors[:,-1];orientation_method='local RGB gradient structure tensor'
        elif singular[0]>1:axis=vt[0]
        else:
            axis=np.array([1.,0.]) if np.var(a.mean(axis=0),axis=0).sum()>=np.var(a.mean(axis=1),axis=0).sum() else np.array([0.,1.])
            orientation_method='dominant spatial variance (flat or weak gradient)'
    dominant=int(np.argmax(np.abs(axis)))
    if axis[dominant]<0:axis=-axis
    low=np.minimum(axis,0).sum();span=np.abs(axis).sum()
    positions=((xx*axis[0]+yy*axis[1]-low)/span).reshape(-1)
    knots=np.linspace(0,1,33);colors=[]
    for t in knots:
        mask=np.abs(positions-t)<=.025
        if not mask.any():mask=np.abs(positions-t)<=np.min(np.abs(positions-t))+1e-9
        colors.append(np.median(pixels[mask],axis=0))
    colors=np.asarray(colors)
    if plane_error<=1.5:
        fit=np.linalg.lstsq(np.stack([np.ones_like(positions),positions],axis=-1),pixels,rcond=None)[0]
        colors=np.clip(fit[0]+knots[:,None]*fit[1],0,255)
    target=np.rint(colors).astype(int)
    reconstructed=_curve(target,positions)
    residual=float(np.mean(np.linalg.norm(rgb_to_lab(reconstructed)-rgb_to_lab(pixels),axis=1)))
    dx,dy=axis
    # Style and CSS angle use physical pixel axes, not normalized rectangle
    # coordinates: a 45-degree ramp remains diagonal on a wide rectangle.
    nx,ny=dx/max(crop.width-1,1),dy/max(crop.height-1,1)
    small=min(abs(nx),abs(ny))/max(abs(nx),abs(ny),1e-9)
    if small<.23:
        if abs(nx)>=abs(ny):
            start,end=('왼쪽','오른쪽') if dx>=0 else ('오른쪽','왼쪽');style='가로 그라데이션'
        else:
            start,end=('위쪽','아래쪽') if dy>=0 else ('아래쪽','위쪽');style='세로 그라데이션'
    else:
        start=('왼쪽' if dx>=0 else '오른쪽')+(' 위' if dy>=0 else ' 아래')
        end=('오른쪽' if dx>=0 else '왼쪽')+(' 아래' if dy>=0 else ' 위');style='대각선 그라데이션'
    angle=math.degrees(math.atan2(nx,-ny))%360
    info={'selection':'rect' if rect is not None else 'auto','rect':bounds,'start_label':start,'end_label':end,'direction':start+' → '+end,'style':style,'css_angle':round(angle,1),'orientation_method':orientation_method,'spatial_residual_delta_e76':round(residual,2),'flat_image':bool(np.max(np.std(pixels,axis=0))<=1)}
    info.update(geometry)
    info['rect_coordinate_convention']='left, top inclusive; right, bottom exclusive'
    preview=crop.copy();preview.thumbnail((700,300))
    return target,axis,preview,info

def inverse_gradient(filename,payload,document):
    strength=float(payload.get('strength',1));tac=float(payload.get('tac',300))
    if not math.isfinite(strength) or not 0<=strength<=1:raise ValueError('반영 강도는 0~1 사이여야 합니다.')
    if not math.isfinite(tac) or not 100<=tac<=400:raise ValueError('잉크량 상한은 100~400%여야 합니다.')
    target,axis,target_preview,analysis=_analyze(filename,payload)
    model=PhotoModel(document);limit=math.floor(tac*255/100+1e-8)
    from prediction import Predictor,gamut_flags
    mode=payload.get('model_mode','photo')
    if mode=='icc':strength=0.
    predictor=Predictor(document,strength,mode)
    def forward(points):
        predicted,baseline,values=predictor.forward(points,'RGB')
        return predicted,values
    sample_t=np.linspace(0,1,33);target_lab=rgb_to_lab(target)
    weights=np.ones(33);weights[[0,-1]]=2
    endpoints=[inverse_color({'rgb':target[n].tolist(),'strength':strength,'tac':tac,'model_mode':mode},document) for n in (0,-1)]
    seeds=[np.array([r['rgb_result']['input_rgb'] for r in endpoints]).reshape(-1),target[[0,-1]].reshape(-1),np.full(6,255)]
    def score(candidates,count):
        candidates=np.asarray(candidates,dtype=int).reshape(-1,count,3)
        inputs=np.rint(np.stack([_curve(s,sample_t) for s in candidates])).astype(int)
        predicted,ink=forward(inputs.reshape(-1,3));predicted=predicted.reshape(-1,33,3);ink=ink.reshape(-1,33,4)
        delta=np.linalg.norm(rgb_to_lab(predicted)-target_lab,axis=-1)
        cost=np.average(delta**2,axis=1,weights=weights)+.2*np.max(delta**2,axis=1)
        valid=np.max(ink.sum(axis=-1),axis=1)<=limit
        return np.where(valid,cost,np.inf)
    def fit(seeds,count):
        seeds=np.clip(np.rint(seeds),0,255).astype(int).reshape(-1,count*3);scores=score(seeds,count)
        current=seeds[int(np.argmin(scores))];best=float(np.min(scores))
        for step in (16,8,4,2,1):
            for _ in range(6):
                directions=[np.zeros(count*3,dtype=int)]
                for n in range(count*3):
                    for sign in (-1,1):
                        d=np.zeros(count*3,dtype=int);d[n]=sign;directions.append(d)
                for channel in range(3):
                    for sign in (-1,1):
                        d=np.zeros(count*3,dtype=int);d[channel::3]=sign;directions.append(d)
                candidates=np.unique(np.clip(current+np.array(directions)*step,0,255),axis=0)
                scores=score(candidates,count);index=int(np.argmin(scores))
                if float(scores[index])>=best-1e-9:break
                current=candidates[index];best=float(scores[index])
        return current.reshape(count,3)
    def repair(stops):
        stops=np.clip(np.rint(stops),0,255).astype(int).reshape(-1,3)
        # Verify every quantized RGB state, rather than only 513 sample points.
        for _ in range(256):
            _,fine_ink=forward(_quantized_ramp(stops))
            if int(fine_ink.sum(axis=1).max())<=limit:break
            stops=np.minimum(stops+1,255)
        else:raise ValueError('그라데이션 전체 구간에서 잉크량 제한을 만족하는 후보를 찾지 못했습니다.')
        return stops,fine_ink
    def result(stops):
        stops,fine_ink=repair(stops)
        inputs=np.rint(_curve(stops,sample_t)).astype(int);predicted,ink=forward(inputs)
        delta=np.linalg.norm(rgb_to_lab(predicted)-target_lab,axis=1)
        stop_t=np.linspace(0,1,len(stops));stop_targets=np.rint(_curve(target,stop_t)).astype(int);stop_pred,stop_ink=forward(stops)
        rows=[]
        for n,(rgb,desired,printed,channels) in enumerate(zip(stops,stop_targets,stop_pred,stop_ink)):
            rows.append({'position_percent':round(stop_t[n]*100),'input_rgb':rgb.tolist(),'target_rgb':desired.tolist(),'predicted_rgb':printed.tolist(),'converted_cmyk':(np.floor(channels*10000/255)/100).tolist(),'delta_e76':round(float(np.linalg.norm(rgb_to_lab(printed)-rgb_to_lab(desired))),2)})
        return {'stops':rows,'mean_delta_e76':round(float(delta.mean()),2),'max_delta_e76':round(float(delta.max()),2),'max_ink_percent':round(float(fine_ink.sum(axis=1).max()*100/255),2),'ink_validation':'all quantized RGB states on encoded-sRGB linear segments','predicted_samples':predicted.tolist(),'input_samples':inputs.tolist(),'reference_support':reference_support(model,inputs) if mode=='photo' else None}
    def final_cost(record):
        delta=np.linalg.norm(rgb_to_lab(record['predicted_samples'])-target_lab,axis=1)
        return float(np.average(delta**2,weights=weights)+.2*np.max(delta**2))
    # Keep the V11.1 result as a baseline. An otherwise useful endpoint seed
    # can exceed TAC by only one or two codes and be rejected by score(); a
    # separate feasible start avoids falling back to a poor white-only basin.
    # Retain both the feasible seed and its refinement, then compare AFTER
    # complete-ramp repair so extra starts cannot worsen the old objective.
    baseline_two=result(fit(seeds,2))
    alternatives=[baseline_two];seen=set()
    for seed in seeds:
        feasible,_=repair(np.asarray(seed).reshape(2,3))
        signature=tuple(feasible.reshape(-1))
        if signature in seen:continue
        seen.add(signature)
        alternatives.extend([result(feasible),result(fit([feasible],2))])
    two=min(alternatives,key=final_cost);three=None
    if (two['mean_delta_e76']>3 or two['max_delta_e76']>6) and analysis['spatial_residual_delta_e76']<=5:
        middle=inverse_color({'rgb':target[16].tolist(),'strength':strength,'tac':tac,'model_mode':mode},document)['rgb_result']['input_rgb']
        seed3=[two['stops'][0]['input_rgb'],middle,two['stops'][1]['input_rgb']]
        # A two-stop fit can move both endpoints far from their target colors
        # while compromising for a bright/dark middle. Retain that candidate,
        # but also refine independent endpoint inverses and raw target stops.
        # Compare the actual objective AFTER complete-ramp TAC repair, so these
        # additional starts cannot worsen the former seed's final objective.
        independent=[endpoints[0]['rgb_result']['input_rgb'],middle,endpoints[1]['rgb_result']['input_rgb']]
        # Preserve the former two-stop-derived three-stop start as well as
        # the improved two-stop start; all prior independent starts remain.
        former_seed3=[baseline_two['stops'][0]['input_rgb'],middle,baseline_two['stops'][1]['input_rgb']]
        starts=[seed3,former_seed3,independent,target[[0,16,32]],np.full((3,3),255)]
        starts=list({tuple(np.asarray(start,dtype=int).reshape(-1)):start for start in starts}.values())
        alternatives=[result(fit([start],3)) for start in starts]
        constant=min(alternatives,key=final_cost)
        if constant['mean_delta_e76']<two['mean_delta_e76']-.35:three=constant
    key=hashlib.sha256((json.dumps(payload,sort_keys=True)+json.dumps(document,sort_keys=True)+str(pathlib.Path(filename).stat().st_mtime_ns)).encode()).hexdigest()[:20]
    out=BASE/'exports'/('gradient_'+key);out.mkdir(exist_ok=True)
    save_srgb(target_preview,out/'target.png')
    ph,pw=target_preview.height,target_preview.width
    yy,xx=np.meshgrid(np.linspace(0,1,ph),np.linspace(0,1,pw),indexing='ij')
    t=(xx*axis[0]+yy*axis[1]-np.minimum(axis,0).sum())/np.abs(axis).sum()
    def previews(record,name):
        input_pixels=np.clip(np.rint(_curve([s['input_rgb'] for s in record['stops']],t.reshape(-1))),0,255).astype(np.uint8).reshape(ph,pw,3)
        output_pixels=forward(input_pixels.reshape(-1,3))[0].astype(np.uint8).reshape(ph,pw,3)
        save_srgb(Image.fromarray(input_pixels),out/(name+'_input.png'));save_srgb(Image.fromarray(output_pixels),out/(name+'_predicted.png'))
        record['input_preview']=(out/(name+'_input.png')).relative_to(BASE).as_posix();record['predicted_preview']=(out/(name+'_predicted.png')).relative_to(BASE).as_posix()
    previews(two,'two')
    if three:previews(three,'three')
    return {'analysis':analysis,'target_stops':[target[0].tolist(),target[-1].tolist()],'target_preview':(out/'target.png').relative_to(BASE).as_posix(),'two_stop':two,'three_stop':three,'strength':strength,'tac_limit':tac,'model_mode':mode,'input_cmyk_profile':predictor.input_profile,'icc_gamut_warning_percent':round(float(gamut_flags(target).mean()*100),2),'icc_gamut_scope':'FOGRA39 target-color sample alarm; not empirical fit residual','extrapolated_sample_percent':round(float((model.nearest(two['input_samples'])>12).mean()*100),2) if mode=='photo' else None,'model_name':document.get('name'),'metric':'Delta E 76, sRGB-derived D65 Lab','interpolation':'encoded sRGB linear interpolation','note':'사진 모드는 sRGB 입력을 새 사진 모델로 직접 예측합니다. ICC 모드는 별도 FOGRA39 표준 조건입니다. 색차 임계값과 ICC 색역 경고는 다르며, 경고 없음은 4도 재현 보장이 아닙니다. 최종 인쇄 PDF로 확인해 주세요. 사진 보정과 방향·색 추출은 추정입니다.'}
