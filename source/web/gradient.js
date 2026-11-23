'use strict';
const gradientState={asset:null,image:null,rect:null,line:[],drag:null,result:null,requestContext:null,selectedVariant:'two_stop',preferredVariant:null,uploading:false,running:false,sequence:0};
function gradientMessage(text){$('gradientMessage').textContent=text;}
function gradientResetResult(){gradientState.sequence++;if($('gradientCompareDialog').open)$('gradientCompareDialog').close();gradientState.result=null;gradientState.requestContext=null;$('gradientResult').hidden=true;gradientMessage('');}
function gradientVariantLabel(key){return key==='three_stop'?'3색':'2색';}
function gradientSelectedVariant(result=gradientState.result){return result&&result[gradientState.selectedVariant]?gradientState.selectedVariant:'two_stop';}
function gradientSelectedRecord(result=gradientState.result){return result?result[gradientSelectedVariant(result)]:null;}
function gradientPreferredVariant(result){
  if(gradientState.preferredVariant&&result[gradientState.preferredVariant])return gradientState.preferredVariant;
  return result.three_stop&&Number(result.three_stop.mean_delta_e76)<Number(result.two_stop.mean_delta_e76)?'three_stop':'two_stop';
}
function gradientNumber(value,digits=1){return Number.isFinite(Number(value))?String(Number(Number(value).toFixed(digits))):String(value);}
function gradientGeometryLines(result,context){
  const a=result.analysis,lines=['방향: '+a.direction,'스타일: '+a.style];
  if(a.css_angle!==null&&a.css_angle!==undefined&&Number.isFinite(Number(a.css_angle)))lines.push('각도: '+Number(a.css_angle).toFixed(1)+'° · CSS 기준 0°는 위, 90°는 오른쪽, 시계방향');
  else lines.push(a.selection==='line'?'CSS 각도: 두 점 선택에서는 전체 영역의 그라데이션 각도를 추정하지 않습니다.':'CSS 각도: 분석값 없음');
  const saved=context||(result===gradientState.result?gradientState.requestContext:null);
  const points=a.source_points||saved?.line;
  if(Array.isArray(points)&&points.length===2)lines.push('선택한 1번 위치: ('+points[0].map(v=>gradientNumber(v,2)).join(', ')+') px → 2번 위치: ('+points[1].map(v=>gradientNumber(v,2)).join(', ')+') px','좌표 기준: 원본 이미지 왼쪽 위가 (0, 0), x는 오른쪽, y는 아래쪽. 두 점 사이의 색 변화만 분석합니다.');
  if(a.source_line_css_angle!==null&&a.source_line_css_angle!==undefined&&Number.isFinite(Number(a.source_line_css_angle)))lines.push('선택선 1번 → 2번 방향: '+Number(a.source_line_css_angle).toFixed(1)+'° · CSS 기준이며 전체 영역의 색 변화 방향을 뜻하지 않습니다.');
  if(a.selection==='line'&&a.preview_css_angle!==null&&a.preview_css_angle!==undefined&&Number.isFinite(Number(a.preview_css_angle)))lines.push('미리보기 방향: '+Number(a.preview_css_angle).toFixed(1)+'° · 두 점 사이의 색 변화를 가로로 펼친 보기');
  if(Array.isArray(a.source_points_normalized)&&a.source_points_normalized.length===2)lines.push('선택점 원본 비율 (x, y): '+a.source_points_normalized.map(point=>'('+point.map(v=>gradientNumber(Number(v)*100,2)+'%').join(', ')+')').join(' → '));
  const rect=a.rect||saved?.rect;
  if(Array.isArray(rect)&&rect.length===4)lines.push('분석 영역 [왼쪽, 위, 오른쪽, 아래]: ['+rect.map(v=>gradientNumber(v,2)).join(', ')+'] px · 오른쪽·아래 끝 좌표 제외');
  const size=a.source_image_size||saved?.image_size;if(size)lines.push('목표 원본 이미지: '+size.join(' × ')+' px');
  return lines;
}
function gradientSupportLines(record,result){
  if(result.model_mode==='icc')return ['FOGRA39 표준 프루프를 사용합니다. 사진 기준색의 근접·외삽 비율은 이 계산에 적용하지 않습니다. 낮은 ΔE76도 실제 인쇄 일치를 보장하지 않습니다.'];
  const s=record.reference_support;
  if(!s)return ['기준색 범위 정보가 없습니다. 모델의 낮은 ΔE76는 실제 인쇄 정확도를 뜻하지 않습니다.'];
  const chromatic=s.chromatic_samples,neutral=s.neutral_samples,total=s.total_samples;
  const lines=[];
  if(Number(chromatic)>0){
    lines.push('사진 기준색과의 거리 · 유채색 '+chromatic+'개 기준: 가까움 '+gradientNumber(s.near_percent)+'% ('+s.near_samples+'개) / 전환 '+gradientNumber(s.transition_percent)+'% ('+s.transition_samples+'개) / 외삽 '+gradientNumber(s.extrapolated_percent)+'% ('+s.extrapolated_samples+'개)');
  }else lines.push('사진 기준색과의 거리: 유채색 표본이 없어 근접·전환·외삽 비율을 계산하지 않습니다.');
  if(total!==undefined&&neutral!==undefined){const neutralLimit=s.neutral_chroma_max??16,nearLimit=s.near_delta_e76_max??12,farLimit=s.extrapolated_delta_e76_min??26;const ranges=Number(farLimit)>Number(nearLimit)?'가까움 ≤'+nearLimit+', 전환 '+nearLimit+' 초과·'+farLimit+' 미만, 외삽 ≥'+farLimit:'가까움 <'+farLimit+', 전환 구간 없음, 외삽 ≥'+farLimit;lines.push('전체 '+total+'개 중 중성·저채도(C*≤'+neutralLimit+') '+neutral+'개는 비율의 분모에서 제외합니다. 거리 분류: '+ranges+'.');}
  lines.push('이 비율은 사진 기준색과의 거리이며 정확도·신뢰확률이 아닙니다. 낮은 ΔE76도 실제 인쇄 일치를 보장하지 않습니다.');
  return lines;
}
function gradientSetSelector(id,result){
  const control=$(id);if(!control)return;
  control.replaceChildren();
  ['two_stop','three_stop'].filter(key=>result[key]).forEach(key=>{
    const option=document.createElement('option');option.value=key;
    option.textContent=gradientVariantLabel(key)+' · 평균 ΔE76 '+result[key].mean_delta_e76+(key==='three_stop'&&Number(result[key].mean_delta_e76)<Number(result.two_stop.mean_delta_e76)?' · 더 가까운 후보':'');
    control.append(option);
  });
  control.value=gradientSelectedVariant(result);control.disabled=!result.three_stop;
}
function selectGradientVariant(key,userSelected=true){
  const result=gradientState.result;if(!result||!['two_stop','three_stop'].includes(key)||!result[key])return;
  gradientState.selectedVariant=key;if(userSelected)gradientState.preferredVariant=key;
  renderGradientResult();
}
function renderGradientResult(){
  const result=gradientState.result,record=gradientSelectedRecord(result);if(!result||!record)return;
  const key=gradientSelectedVariant(result),label=gradientVariantLabel(key);
  gradientSetSelector('gradientVariant',result);gradientSetSelector('gradientCompareVariant',result);
  $('gradientResultTitle').textContent='그라데이션에 입력할 '+label;
  $('gradientVariantSummary').textContent=result.three_stop?'2색 평균 ΔE76 '+result.two_stop.mean_delta_e76+' / 3색 평균 '+result.three_stop.mean_delta_e76+' · 선택한 '+label+' 결과가 미리보기·저장·큰 비교에 함께 적용됩니다.':'2색 후보를 찾았습니다. 현재 결과에 별도 3색 대안은 없습니다.';
  gradientRows(record,$('gradientStopRows'),result);$('gradientStopRows').dataset.stopCount=String(record.stops.length);
  $('gradientDirection').textContent=gradientGeometryLines(result).join('\n');
  $('gradientTargetPreview').src=assetURL(result.target_preview);
  $('gradientInputPreview').src=assetURL(record.input_preview);$('gradientInputPreview').alt=label+' 입력용 그라데이션';
  $('gradientOutputPreview').src=assetURL(record.predicted_preview);$('gradientOutputPreview').alt=label+' 추천의 인쇄 예상색';
  $('gradientInputSummary').textContent='선택한 '+label+' 입력색을 넣은 화면 보기';
  $('gradientStatistics').textContent='선택: '+label+' · 33개 표본 평균 ΔE76 '+record.mean_delta_e76+' / 표본 최대 '+record.max_delta_e76+' · 전체 구간 최대 잉크량 '+record.max_ink_percent+'% · '+predictionModeLabel(result)+' · '+correctionLabel(result);
  $('gradientSupport').textContent=gradientSupportLines(record,result).join('\n');
  const notes=['목표색의 FOGRA39 색역 경고 표본 '+result.icc_gamut_warning_percent+'%. 모델 잔여 색차와는 별도이며, 경고 없음도 실제 4도 재현을 보장하지 않습니다.'];
  if(result.analysis.flat_image)notes.push('단색에 가까워 방향 수치의 의미가 작습니다.');
  if(result.analysis.spatial_residual_delta_e76>5)notes.push('선택 영역에 다른 색이나 그림이 섞여 있습니다. 그라데이션 부분만 다시 선택해 주세요.');
  if(record.mean_delta_e76>5||record.max_delta_e76>10)notes.push('선택한 '+label+' 후보는 현재 모델에서도 목표와 차이가 큽니다.');
  $('gradientAssessment').textContent=notes.join(' ');
  $('gradientAssessment').dataset.state=record.mean_delta_e76>5||record.max_delta_e76>10?'difficult':'close';
  $('saveGradientPng').textContent='선택한 '+label+' 입력 PNG 저장';
  $('gradientResult').hidden=false;
  if(typeof refreshGradientCompare==='function')refreshGradientCompare();
}
function gradientPosition(event){const c=$('targetImageCanvas'),r=c.getBoundingClientRect(),im=gradientState.image;return [Math.max(0,Math.min(im.naturalWidth-1,(event.clientX-r.left)/r.width*im.naturalWidth)),Math.max(0,Math.min(im.naturalHeight-1,(event.clientY-r.top)/r.height*im.naturalHeight))];}
function paintTargetImage(){
  const im=gradientState.image;if(!im)return;const canvas=$('targetImageCanvas'),ctx=canvas.getContext('2d'),scale=Math.min(740/im.naturalWidth,300/im.naturalHeight,1);
  canvas.width=Math.round(im.naturalWidth*scale);canvas.height=Math.round(im.naturalHeight*scale);ctx.drawImage(im,0,0,canvas.width,canvas.height);
  ctx.lineWidth=2;ctx.strokeStyle='#ffe04c';ctx.fillStyle='#ffe04c';
  const rect=gradientState.drag||gradientState.rect;
  if(rect){ctx.fillStyle='#167dc633';ctx.fillRect(rect[0]*scale,rect[1]*scale,(rect[2]-rect[0])*scale,(rect[3]-rect[1])*scale);ctx.strokeRect(rect[0]*scale,rect[1]*scale,(rect[2]-rect[0])*scale,(rect[3]-rect[1])*scale);}
  if(gradientState.line.length){ctx.fillStyle='#ffe04c';ctx.font='bold 14px sans-serif';ctx.beginPath();gradientState.line.forEach((p,i)=>{if(i)ctx.lineTo(p[0]*scale,p[1]*scale);else ctx.moveTo(p[0]*scale,p[1]*scale);});ctx.stroke();gradientState.line.forEach((p,i)=>{ctx.beginPath();ctx.arc(p[0]*scale,p[1]*scale,5,0,Math.PI*2);ctx.fill();ctx.fillText(String(i+1),p[0]*scale+8,p[1]*scale+16);});}
}
async function uploadTargetImage(file){
  if(!file)return;if(gradientState.running||gradientState.uploading)return;
  if(!/\.(png|jpe?g)$/i.test(file.name)){gradientMessage('목표 이미지는 PNG 또는 JPG를 선택해 주세요.');return;}
  if(file.size>220*1024*1024){gradientMessage('220MB 이하 이미지를 선택해 주세요.');return;}
  gradientState.uploading=true;gradientResetResult();gradientMessage('목표 이미지의 색상 프로파일을 읽고 있습니다…');
  $('calculateGradient').disabled=true;
  try{
    const r=await request('/api/photo?name='+encodeURIComponent(file.name),{body:file,type:file.type||'application/octet-stream'});
    const im=new Image();await new Promise((resolve,reject)=>{im.onload=resolve;im.onerror=()=>reject(Error('이미지 미리보기를 열 수 없습니다.'));im.src=assetURL(r.photo);});
    gradientState.asset=r.photo;gradientState.image=im;gradientState.rect=null;gradientState.line=[];$('targetImageTool').value='auto';$('targetImageArea').hidden=false;
    $('targetImageCaption').textContent=file.name+' · '+r.info.source_profile+' → sRGB'+(r.info.profile_assumed?' (프로파일 가정)':'')+(r.info.input_warnings?.length?' · '+r.info.input_warnings.join(' '):'');paintTargetImage();gradientMessage('전체 그림을 자동 분석할 수 있습니다. 포장 이미지라면 그라데이션 부분만 영역으로 선택하세요.');return true;
  }catch(e){gradientMessage(e.message);return false;}finally{gradientState.uploading=false;$('calculateGradient').disabled=false;}
}
function gradientRows(record,parent,result){
  parent.replaceChildren();record.stops.forEach((s,index)=>{
    const row=document.createElement('div');row.className='gradient-stop';
    const chip=document.createElement('i');chip.style.background=hex(s.input_rgb);
    const body=document.createElement('div'),label=document.createElement('b');
    label.textContent='색상 '+(index+1)+' · '+s.position_percent+'%'+(index===0?' · '+result.analysis.start_label:index===record.stops.length-1?' · '+result.analysis.end_label:' · 가운데');
    const value=document.createElement('input');value.readOnly=true;value.value=hex(s.input_rgb).toUpperCase();value.setAttribute('aria-label','색상 '+(index+1)+' 입력 HEX');value.onclick=()=>value.select();
    const note=document.createElement('small');note.textContent='목표 '+hex(s.target_rgb).toUpperCase()+' → 예상 '+hex(s.predicted_rgb).toUpperCase()+' · ΔE76 '+s.delta_e76;
    body.append(label,value,note);row.append(chip,body);parent.append(row);
  });
}
async function runGradient(){
  if(gradientState.running||gradientState.uploading||$('calculateInverse').disabled)return;
  let sequence;
  try{
    if(!gradientState.asset)throw Error('먼저 목표 이미지를 올려 주세요.');
    const tool=$('targetImageTool').value;if(tool==='color')throw Error('단색은 이미지의 원하는 위치를 클릭하면 단색 역산에 반영됩니다.');
    const payload={asset:gradientState.asset,model_mode:$('inverseMode').value,strength:Number($('strength').value)/100,tac:Number($('inverseTac').value)};
    if(tool==='rect'){if(!gradientState.rect)throw Error('그라데이션만 있는 영역을 드래그해 선택해 주세요.');payload.rect=gradientState.rect;}
    if(tool==='line'){if(gradientState.line.length!==2)throw Error('색상 1과 색상 2의 위치를 차례로 클릭해 주세요.');payload.line=gradientState.line;}
    const context={line:payload.line?.map(point=>point.slice()),rect:payload.rect?.slice(),image_size:gradientState.image?[gradientState.image.naturalWidth,gradientState.image.naturalHeight]:null};
    gradientState.running=true;gradientResetResult();sequence=gradientState.sequence;['calculateGradient','targetImageTool','targetImageInput','inverseMode','inverseTac','calculateInverse'].forEach(id=>$(id).disabled=true);gradientMessage('두 입력색을 역산하고 중간 구간의 인쇄 예상색까지 비교하고 있습니다…');
    const j=await request('/api/inverse-gradient',{payload});const r=await waitJob(j.job);if(sequence!==gradientState.sequence)return;gradientState.result=r;
    gradientState.requestContext=context;gradientState.selectedVariant=gradientPreferredVariant(r);renderGradientResult();
    gradientMessage('그라데이션 역산 완료 · '+gradientVariantLabel(gradientSelectedVariant(r))+' 후보 선택');$('gradientDirection').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){if(sequence===undefined||sequence===gradientState.sequence)gradientMessage(e.message);}finally{gradientState.running=false;['calculateGradient','targetImageTool','targetImageInput','inverseMode','inverseTac','calculateInverse'].forEach(id=>$(id).disabled=false);}
}
function gradientText(r){
  const selected=gradientSelectedVariant(r);
  const lines=['HARDYS 목표 그라데이션 역산 · V11.2','현재 선택: '+gradientVariantLabel(selected)+' · 미리보기와 PNG 저장에 적용',...gradientGeometryLines(r),'기준: '+predictionModeLabel(r)+' / CMYK 프로파일 '+r.input_cmyk_profile+' / '+correctionLabel(r)+' / 잉크량 상한 '+r.tac_limit+'%'];
  const add=key=>{const record=r[key];if(!record)return;lines.push('',(key===selected?'[현재 선택] ':'[다른 후보] ')+gradientVariantLabel(key)+' 입력값');record.stops.forEach((s,i)=>lines.push('색상 '+(i+1)+' ('+s.position_percent+'%): '+hex(s.input_rgb).toUpperCase()+' / 목표 '+hex(s.target_rgb).toUpperCase()+' / 예상 '+hex(s.predicted_rgb).toUpperCase()));lines.push('33개 표본 평균 ΔE76 '+record.mean_delta_e76+' / 표본 최대 '+record.max_delta_e76+' / 전체 구간 최대 잉크량 '+record.max_ink_percent+'%',...gradientSupportLines(record,r));};
  add(selected);add(selected==='two_stop'?'three_stop':'two_stop');
  lines.push('',r.note,'HEX는 sRGB 원본에서 수치가 선형으로 혼합되는 그라데이션을 기준으로 합니다. 끝색만 CMYK로 바꿔 CMYK에서 혼합하면 중간색이 달라집니다.','각도는 CSS 기준입니다. 디자인 도구의 각도 기준·선택 영역·중간색 혼합 방식이 다르면 그대로 재현되지 않을 수 있으므로 최종 PDF를 다시 확인하세요.');return lines.join('\n');
}
function bindGradient(){
  $('gradientVariant').onchange=e=>selectGradientVariant(e.target.value);
  $('gradientCompareVariant').onchange=e=>selectGradientVariant(e.target.value);
  ['inverseMode','inverseTac','strength'].forEach(id=>$(id).addEventListener('change',gradientResetResult));
  $('targetImageInput').onchange=e=>{const file=e.target.files[0];e.target.value='';uploadTargetImage(file);};
  $('calculateGradient').onclick=runGradient;$('targetImageTool').onchange=()=>{gradientState.rect=null;gradientState.line=[];gradientResetResult();paintTargetImage();gradientMessage($('targetImageTool').value==='color'?'목표로 사용할 단색 위치를 클릭하세요.':$('targetImageTool').value==='line'?'색상 1과 색상 2 위치를 차례로 클릭하세요.':$('targetImageTool').value==='rect'?'그라데이션만 있는 부분을 드래그하세요.':'전체 그림을 분석합니다.');};
  const canvas=$('targetImageCanvas');canvas.onpointerdown=async e=>{
    if(!gradientState.image||gradientState.running||gradientState.uploading||$('calculateInverse').disabled)return;const p=gradientPosition(e),tool=$('targetImageTool').value;
    if(tool==='rect'){gradientState.drag=[...p,...p];canvas.setPointerCapture(e.pointerId);}
    if(tool==='line'){if(gradientState.line.length===2)gradientState.line=[];gradientState.line.push(p);gradientResetResult();paintTargetImage();gradientMessage(gradientState.line.length===1?'2번 위치를 클릭하세요.':'두 위치가 선택됐습니다. 그라데이션 색상 계산을 누르세요.');}
    if(tool==='color'){try{const r=await request('/api/pick',{payload:{asset:gradientState.asset,x:Math.floor(p[0]),y:Math.floor(p[1])}});$('inverseHex').value=hex(r.rgb);$('inversePicker').value=hex(r.rgb);gradientMessage('목표 단색 '+hex(r.rgb).toUpperCase()+'를 선택했습니다.');await runInverse();}catch(err){gradientMessage(err.message);}}
  };
  canvas.onpointermove=e=>{if(!gradientState.drag)return;const p=gradientPosition(e);gradientState.drag[2]=p[0];gradientState.drag[3]=p[1];paintTargetImage();};
  canvas.onpointerup=()=>{if(!gradientState.drag)return;const a=gradientState.drag;gradientState.drag=null;gradientState.rect=[Math.floor(Math.min(a[0],a[2])),Math.floor(Math.min(a[1],a[3])),Math.ceil(Math.max(a[0],a[2])),Math.ceil(Math.max(a[1],a[3]))];gradientResetResult();paintTargetImage();gradientMessage('영역이 선택됐습니다. 그라데이션 색상 계산을 누르세요.');};
  canvas.onpointercancel=()=>{gradientState.drag=null;paintTargetImage();};
  $('saveGradientTxt').onclick=async()=>{try{if(gradientState.result)await saveBlob(new Blob([gradientText(gradientState.result)],{type:'text/plain'}),'HARDYS_gradient_colors.txt','text/plain');}catch(e){gradientMessage(e.message);}};
  $('saveGradientPng').onclick=async()=>{try{const record=gradientSelectedRecord();if(!record)return;const key=gradientSelectedVariant(),response=await fetch(assetURL(record.input_preview));if(!response.ok)throw Error('추천 그라데이션을 읽지 못했습니다.');await saveBlob(await response.blob(),'HARDYS_gradient_'+(key==='three_stop'?'3':'2')+'_color_input.png','image/png');}catch(e){gradientMessage(e.message);}};
}
