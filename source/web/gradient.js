'use strict';
const gradientState={asset:null,image:null,rect:null,line:[],drag:null,result:null,uploading:false,running:false,sequence:0};
function gradientMessage(text){$('gradientMessage').textContent=text;}
function gradientResetResult(){gradientState.sequence++;if($('gradientCompareDialog').open)$('gradientCompareDialog').close();gradientState.result=null;$('gradientResult').hidden=true;gradientMessage('');}
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
    gradientState.running=true;gradientResetResult();sequence=gradientState.sequence;['calculateGradient','targetImageTool','targetImageInput','inverseMode','inverseTac','calculateInverse'].forEach(id=>$(id).disabled=true);gradientMessage('두 입력색을 역산하고 중간 구간의 인쇄 예상색까지 비교하고 있습니다…');
    const j=await request('/api/inverse-gradient',{payload});const r=await waitJob(j.job);if(sequence!==gradientState.sequence)return;gradientState.result=r;
    gradientRows(r.two_stop,$('gradientStopRows'),r);$('gradientDirection').textContent=r.analysis.style+' · '+r.analysis.direction+' · 색상 동그라미에 아래 순서대로 입력하세요.';
    $('gradientTargetPreview').src=assetURL(r.target_preview);$('gradientInputPreview').src=assetURL(r.two_stop.input_preview);$('gradientOutputPreview').src=assetURL(r.two_stop.predicted_preview);
    $('gradientStatistics').textContent='33개 표본 평균 색차 ΔE76 '+r.two_stop.mean_delta_e76+' / 표본 최대 '+r.two_stop.max_delta_e76+' · 전체 구간 최대 잉크량 '+r.two_stop.max_ink_percent+'% · '+correctionLabel(r);
    const notes=['FOGRA39 표준 ICC 색역 경고 표본 '+r.icc_gamut_warning_percent+'%. 색차 경고와 별개이며, 경고 없음은 4도 재현 보장이 아닙니다.'];if(r.analysis.flat_image)notes.push('단색에 가까운 이미지로 분석됐습니다.');
    if(r.analysis.spatial_residual_delta_e76>5)notes.push('선택 영역에 다른 색이나 그림이 섞여 있습니다. 그라데이션만 있는 부분을 다시 선택하는 편이 좋습니다.');
    if(r.two_stop.mean_delta_e76>5||r.two_stop.max_delta_e76>10)notes.push('현재 인쇄 조건에서는 목표 그라데이션과 차이가 큽니다.');
    if(!notes.length)notes.push('현재 모델에서 두 색의 조합을 찾았습니다. 목표와 인쇄 예상색을 비교하세요.');
    $('gradientAssessment').textContent=notes.join(' ');$('gradientThreeResult').hidden=!r.three_stop;
    if(r.three_stop){gradientRows(r.three_stop,$('gradientThreeRows'),r);$('gradientThreeNote').textContent='두 색만 사용할 때보다 가운데 색을 더하면 33개 표본 평균 색차가 '+r.two_stop.mean_delta_e76+' → '+r.three_stop.mean_delta_e76+'로 줄어듭니다. 디자인 도구의 ＋로 가운데 색을 추가하세요.';$('gradientThreePreview').src=assetURL(r.three_stop.predicted_preview);}
    $('gradientResult').hidden=false;gradientMessage('그라데이션 역산 완료');$('gradientDirection').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(e){if(sequence===undefined||sequence===gradientState.sequence)gradientMessage(e.message);}finally{gradientState.running=false;['calculateGradient','targetImageTool','targetImageInput','inverseMode','inverseTac','calculateInverse'].forEach(id=>$(id).disabled=false);}
}
function gradientText(r){
  const lines=['HARDYS 목표 그라데이션 역산','방향: '+r.analysis.direction,'스타일: '+r.analysis.style,'기준: '+predictionModeLabel(r)+' / CMYK 프로파일 '+r.input_cmyk_profile+' / '+correctionLabel(r)+' / 잉크량 상한 '+r.tac_limit+'%'];
  const add=(record,title)=>{lines.push('',title);record.stops.forEach((s,i)=>lines.push('색상 '+(i+1)+' ('+s.position_percent+'%): '+hex(s.input_rgb).toUpperCase()+' / 목표 '+hex(s.target_rgb).toUpperCase()+' / 예상 '+hex(s.predicted_rgb).toUpperCase()));lines.push('33개 표본 평균 ΔE76 '+record.mean_delta_e76+' / 표본 최대 '+record.max_delta_e76+' / 전체 구간 최대 잉크량 '+record.max_ink_percent+'%');};
  add(r.two_stop,'2색 입력값');if(r.three_stop)add(r.three_stop,'가운데 색을 추가한 3색 대안');lines.push('',r.note,'디자인 도구에서 같은 방향의 그라데이션을 고르고 순서대로 입력하세요. 중간색 혼합 방식이 다르면 최종 PDF를 다시 확인하세요.');return lines.join('\n');
}
function bindGradient(){
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
  $('saveGradientPng').onclick=async()=>{try{if(!gradientState.result)return;const response=await fetch(assetURL(gradientState.result.two_stop.input_preview));if(!response.ok)throw Error('추천 그라데이션을 읽지 못했습니다.');await saveBlob(await response.blob(),'HARDYS_gradient_input.png','image/png');}catch(e){gradientMessage(e.message);}};
}
