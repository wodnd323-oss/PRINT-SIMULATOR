'use strict';
const $=id=>document.getElementById(id);
const state={catalog:null,calibration:null,current:null,page:0,preview:null,photo:null,photoName:'7번 파란 케이스',sourcePick:null,targetPick:null,busy:false,sequence:0,inverseSequence:0};
const assetURL=p=>'/'+p.split('/').map(encodeURIComponent).join('/');
const safeText=value=>String(value??'');
function status(text,busy=false){$('status').textContent=text;$('status').classList.toggle('busy',busy);}
function error(message){$('error').hidden=!message;$('error').textContent=message||'';}
function busy(value,text){state.busy=value;['savePng','openPng','addAnchor','resetModel','quitBtn'].forEach(id=>$(id).disabled=value);if(text)status(text,value);}
async function session(){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),3500);
  try{
    const response=await fetch('/api/session',{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error('현재 창은 이전 실행 버전입니다. START.cmd로 새로 열린 창을 사용해 주세요.');
    const data=await response.json();
    if(window.HARDYS_ROOT&&data.root_id!==window.HARDYS_ROOT)throw Error('다른 프로그램 폴더에 연결됐습니다. START.cmd로 새 창을 열어 주세요.');
    window.HARDYS_TOKEN=data.token;return data;
  }catch(e){if(e instanceof TypeError||e.name==='TimeoutError'||e.name==='AbortError')throw connectionError();throw e;}
  finally{clearTimeout(timer);}
}
function connectionError(){return Error('이미지 처리 프로그램과 연결이 끊겼습니다. START.cmd를 다시 실행하고 자동으로 열리는 새 창을 사용해 주세요.');}
async function request(route,{payload,body,type}={}){
  const posting=payload!==undefined||body!==undefined;
  if(body instanceof Blob)await session();
  for(let attempt=0;attempt<2;attempt++){
    const opts=posting?{method:'POST',headers:{'X-Hardys-Token':window.HARDYS_TOKEN,'Content-Type':type||'application/json'},body:body??JSON.stringify(payload)}:{};
    let response;try{response=await fetch(route,opts);}catch(e){throw connectionError();}
    let data;try{data=await response.json();}catch(e){throw Error('처리 응답을 읽지 못했습니다. [다시 연결]을 눌러 주세요.');}
    if(response.status===403&&data.code==='SESSION_EXPIRED'&&attempt===0){await session();continue;}
    if(!response.ok||data.error)throw Error(data.error||'요청을 처리하지 못했습니다.');return data;
  }
}
async function waitJob(id){
  for(let count=0;count<1600;count++){
    const result=await request('/api/job?id='+encodeURIComponent(id));
    if(result.status==='done')return result.result;
    if(result.status==='error')throw Error(result.error);
    await new Promise(resolve=>setTimeout(resolve,600));
  }throw Error('변환 시간이 길어지고 있습니다. 파일을 다시 선택하기 전에 잠시 기다려 주세요.');
}
function currentPage(){return state.current.pages[state.page];}
function cmykImage(item=state.current){return item?.gamut_info?.working_mode==='CMYK';}
function fillCases(){const select=$('caseSelect');select.replaceChildren();state.catalog.cases.forEach(c=>{const option=new Option(c.name,c.id);select.add(option);});if(state.current)select.value=state.current.id;}
function fitImages(){return fitViewerImages();}
function paintView(){
  if(!state.preview||!state.current)return;const mode=$('viewSelect').value;const page=currentPage();let path=state.preview.matched,title='전체색 추정 보정 후',tag='차이 반영 '+Math.round(state.preview.statistics.strength*100)+'%';
  if(mode==='range'){path=state.preview.range;title='기준색과 새 색의 구분';tag='자주색: 새 색 외삽';}
  if(mode==='paper'){path=page.relative;title=state.current.kind==='rgb'?(cmykImage()?'CMYK 원본의 FOGRA39 예상색':'RGB 원본의 FOGRA39 예상색'):'FOGRA39 표준 소프트 프루핑';tag='사진 보정 미적용';}
  if(mode==='ink'){path=page.TAC300;title=state.current.kind==='rgb'?(cmykImage()?'CMYK 입력 · RGB 색역 검사 해당 없음':'CMYK 색역 초과 예상'):'총 잉크량 300% 초과';tag=cmykImage()?'CMYK에서 변환 전 RGB 색역은 판정할 수 없습니다':'자주색: 경고 표시';}
  $('afterTitle').textContent=title;$('afterTag').textContent=tag;$('afterImage').src=assetURL(path);
  const stats=state.preview.statistics;$('nearStat').textContent=stats.near_reference_percent+'%';$('transitionStat').textContent=stats.transition_percent+'%';$('unknownStat').textContent=stats.unsupported_percent+'%';
  state.displayOutput={path,name:mode==='matched'?state.preview.export_name:mode==='paper'?'HARDYS_FOGRA39_standard.png':mode==='range'?'HARDYS_reference_range.png':state.current.kind==='rgb'?'HARDYS_gamut_warning.png':'HARDYS_TAC300.png'};
  $('savePng').textContent=title+' PNG · 다른 이름으로 저장';
  $('openPng').textContent=title+' 열기 · 직접 저장';
}
async function refreshPreview(){
  if(!state.current)return;const sequence=++state.sequence;busy(true,'사진 차이 반영 중…');error('');
  try{const j=await request('/api/preview',{payload:{asset:currentPage().source,strength:Number($('strength').value)/100}});const result=await waitJob(j.job);if(sequence!==state.sequence)return;state.preview=result;paintView();status('비교 준비 완료');}
  catch(e){if(sequence!==state.sequence)return;state.preview=null;error(e.message);status('처리 확인 필요');}
  finally{if(sequence===state.sequence)busy(false);}
}
async function selectCase(id){
  const item=state.catalog.cases.find(c=>c.id===id);if(!item)return;state.current=item;state.page=0;state.preview=null;$('caseSelect').value=id;$('fileTitle').textContent=item.name;
  $('pageSelect').replaceChildren();item.pages.forEach((p,i)=>$('pageSelect').add(new Option((i+1)+' / '+item.pages.length,i)));
  $('profileNote').textContent='사진 예측 입력: '+(item.source_profile_description||item.gamut_info?.source_profile||'sRGB')+' → sRGB · FOGRA39 표준 검사는 별도'+(item.source_profile_note?' · '+item.source_profile_note:'')+(item.gamut_info?.profile_assumed?' · 내장 ICC 없음/부적합: 표시한 프로파일 가정':'');
  if(item.warnings?.length)$('profileNote').textContent+=' · '+item.warnings.join(' ');
  if(item.gamut_info?.input_warnings?.length)$('profileNote').textContent+=' · '+item.gamut_info.input_warnings.join(' ');
  $('viewSelect').options[3].textContent=item.kind==='rgb'?(cmykImage(item)?'CMYK 입력 · RGB 색역 검사 해당 없음':'RGB 원본의 CMYK 색역 초과'):'총 잉크량 300% 초과';
  $('beforeImage').src=assetURL(currentPage().source);clearPicks();await refreshPreview();
}
async function importFile(file,kind='auto'){
  if(!file)return;
  if(kind==='auto')kind=/\.pdf$/i.test(file.name)?'pdf':/\.(png|jpe?g)$/i.test(file.name)?'rgb':null;
  if(!kind){error('PDF, PNG 또는 JPG 파일을 선택해 주세요.');return;}
  if(file.size>220*1024*1024){error('220MB 이하 파일을 선택해 주세요.');return;}
  if(state.busy){error('현재 작업이 끝난 뒤 파일을 선택해 주세요.');return;}
  busy(true,kind==='pdf'?'원본 프로파일 해석 및 별도 표준 프루핑 중…':'이미지 형식 및 인쇄색 확인 중…');error('');
  try{const j=await request('/api/'+kind+'?name='+encodeURIComponent(file.name),{body:file,type:kind==='pdf'?'application/pdf':file.type||'application/octet-stream'});const record=await waitJob(j.job);const prior=state.catalog.cases.findIndex(c=>c.id===record.id);if(prior>=0)state.catalog.cases[prior]=record;else state.catalog.cases.push(record);fillCases();await selectCase(record.id);if(record.gamut_info)status(record.gamut_info.gamut_check_applicable===false?'CMYK 이미지 비교 준비 완료':'색역 초과 예상 '+record.gamut_info.gamut_alarm_percent+'%');return true;}
  catch(e){error(e.message);status('파일 확인 필요');return false;}finally{busy(false);}
}
function clearPicks(){state.sourcePick=null;state.targetPick=null;['source','target'].forEach(side=>{$(side+'Swatch').style.background='white';$(side+'Value').textContent=side==='source'?'왼쪽 그림을 클릭하세요':'기준 사진을 클릭하세요';});}
function paintAnchors(){
  const tbody=$('anchorRows');tbody.replaceChildren();let enabled=0;
  state.calibration.anchors.forEach((a,index)=>{
    if(a.enabled!==false)enabled++;const tr=document.createElement('tr');tr.classList.toggle('disabled',a.enabled===false);
    const use=document.createElement('input');use.type='checkbox';use.checked=a.enabled!==false;use.setAttribute('aria-label',a.label+' 사용');use.onchange=async()=>{a.enabled=use.checked;await saveCalibration();};
    const tdu=document.createElement('td');tdu.append(use);tr.append(tdu);const name=document.createElement('td');name.append(document.createTextNode(a.label));const group=document.createElement('small');group.textContent=a.group||'';name.append(group);tr.append(name);
    ['source_rgb','target_rgb'].forEach(key=>{const td=document.createElement('td');const chip=document.createElement('i');chip.className='chip';chip.style.background='rgb('+a[key].join(',')+')';td.append(chip,document.createTextNode(a[key].join(' · ')));tr.append(td);});
    const n=document.createElement('td');n.textContent=a.sample_count||'직접 선택';tr.append(n);tbody.append(tr);
  });
  $('anchorCount').textContent=enabled+'개 기준 사용';
  const hasGreen=state.calibration.anchors.some(a=>a.enabled!==false&&/녹색|초록|green/i.test(a.label+' '+a.group));
  document.querySelector('.unverified').textContent=hasGreen?'녹색 기준 추가됨 · 전체색 추정에 반영':'녹색 기준 미등록 · 전체 경향으로 추정';
  const s=state.calibration.comparison_statistics;$('modelStats').textContent=s?'초기 기준 구성: '+s.patches+'개 사진 대응 표본을 '+s.anchors+'개 색 기준으로 묶었습니다. 이 통계는 같은 사진을 사용한 비교이며, 독립적인 인쇄 검증 결과가 아닙니다.':'';
}
async function saveCalibration(){
  error('');try{const result=await request('/api/calibration',{payload:state.calibration});state.calibration=result.calibration;invalidatePredictions();paintAnchors();await refreshPreview();}catch(e){error(e.message);}
}
async function pick(event,side){
  if(!$('pickMode').checked||state.busy)return;const im=event.currentTarget,rect=im.getBoundingClientRect();if(!im.naturalWidth)return;
  const x=Math.floor((event.clientX-rect.left)/rect.width*im.naturalWidth),y=Math.floor((event.clientY-rect.top)/rect.height*im.naturalHeight);
  try{const result=await request('/api/pick',{payload:{asset:side==='source'?currentPage().source:state.photo,x,y}});state[side+'Pick']=result;$(side+'Swatch').style.background='rgb('+result.rgb.join(',')+')';$(side+'Value').textContent=result.rgb.join(' · ');}
  catch(e){error(e.message);}
}
async function saveBlob(blob,name,mime){
  if('showSaveFilePicker' in window){
    try{const handle=await window.showSaveFilePicker({suggestedName:name,types:[{description:mime==='image/png'?'PNG 이미지':mime==='text/plain'?'텍스트 결과':'보정 기준 JSON',accept:{[mime]:['.'+name.split('.').pop()]}}]});const writable=await handle.createWritable();await writable.write(blob);await writable.close();status('저장 완료');return;}
    catch(e){if(e.name==='AbortError')return;if(e.name!=='SecurityError')throw e;}
  }
  const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),15000);status('브라우저 저장 창을 확인하세요');
}
function resetInverseResult(){state.inverseSequence++;state.inverse=null;$('inverseResult').hidden=true;$('inverseError').textContent='';}
function invalidatePredictions(){resetInverseResult();gradientResetResult();}
function correctionLabel(r){return r.model_mode==='icc'?'사진 보정 미적용':'사진 보정 '+Math.round(r.strength*100)+'%';}
function predictionModeLabel(r){return r.model_mode==='icc'?'FOGRA39 표준 프루프':'전달본 기준 사진 모델';}
function hex(rgb){return '#'+rgb.map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');}
async function checkColor(kind='rgb'){
  try{
    let payload={strength:Number($('strength').value)/100};
    if(kind==='cmyk'){payload.cmyk=['c','m','y','k'].map(k=>Number($(k+'Input').value));}
    else{const value=$('hexInput').value.trim();if(!/^#[0-9a-f]{6}$/i.test(value))throw Error('HEX를 #00b941 형식으로 입력해 주세요.');payload.rgb=[1,3,5].map(n=>parseInt(value.slice(n,n+2),16));$('colorPicker').value=value;}
    const result=await request('/api/color',{payload});
    [['input',result.input_rgb],['basic',result.baseline_rgb],['global',result.matched_rgb]].forEach(([id,rgb])=>{$(id+'Color').style.background=hex(rgb);$(id+'ColorValue').textContent=hex(rgb).toUpperCase()+' · '+rgb.join(', ');});
    $('inputColorLabel').textContent=kind==='cmyk'?'입력 CMYK의 화면색':'원본 RGB';
    $('colorDetail').textContent='CMYK 해석/분해 프로파일: '+result.input_cmyk_profile+' · 값: '+['C','M','Y','K'].map((n,i)=>n+' '+result.cmyk[i]+'%').join(' / ')+(result.outside_cmyk_gamut===true?' · RGB 원본은 FOGRA39 색역 밖으로 추정됩니다.':result.outside_cmyk_gamut===false?' · FOGRA39 ICC 색역 경고 없음. 실제 4도 인쇄 재현 보장은 아닙니다.':' · CMYK 직접 입력.');
    $('colorScope').textContent=result.near_reference?'기존 인쇄 기준색에 가까운 색입니다. 사진에 맞춘 보정도 함께 적용됩니다.':'기존 인쇄 기준에 없는 색입니다. 전체 채도·색조·밝기 경향으로 계산한 외삽 추정입니다.';
    $('colorScope').className=result.near_reference?'near-color':'extrapolated-color';
  }catch(e){$('colorScope').textContent=e.message;$('colorScope').className='extrapolated-color';}
}
function setupPresets(){
  const presets=[['하디스 빨강','#d80202'],['녹색','#00b941'],['청록','#009baa'],['파랑','#176bc1'],['보라','#8a43bf'],['주황','#ef7d21'],['금색','#e3c084'],['연두','#9bc830'],['분홍','#db76a5'],['남색','#243c78'],['갈색','#8b5941'],['회색','#808080']];
  presets.forEach(([name,value])=>{const button=document.createElement('button');button.type='button';button.textContent=name;const chip=document.createElement('i');chip.style.background=value;button.prepend(chip);button.onclick=()=>{$('hexInput').value=value;$('colorPicker').value=value;checkColor();};$('colorPresets').append(button);});
}

function inverseText(r){
  const c=r.cmyk_result,g=r.rgb_result;
  return ['HARDYS 목표색 역산 결과','목표 HEX: '+hex(r.target_rgb).toUpperCase(),'기준: '+predictionModeLabel(r)+' / CMYK 프로파일 '+r.input_cmyk_profile+' / '+correctionLabel(r)+' / 잉크량 상한 '+r.tac_limit+'%',
    'CMYK 추천: '+['C','M','Y','K'].map((n,i)=>n+' '+c.cmyk[i]+'%').join(' / '),'CMYK 예상 결과: '+hex(c.predicted_rgb).toUpperCase()+' / 색차 ΔE76 '+c.delta_e76+' / 총 잉크량 '+c.total_ink_percent+'%',
    'RGB 디자인 입력용 HEX: '+hex(g.input_rgb).toUpperCase(),'RGB 경로 예상 결과: '+hex(g.predicted_rgb).toUpperCase()+' / 색차 ΔE76 '+g.delta_e76+' / 변환 후 총 잉크량 '+g.total_ink_percent+'%',
    '목표색 FOGRA39 색역 경고: '+(r.icc_gamut_warning?'있음':'없음'),'보정 기준 식별값: '+r.calibration_sha256,
    '사진 모드의 RGB 추천은 sRGB 원본 입력 기준입니다. CMYK 추천은 표시한 프로파일을 지정해야 합니다. 최종 PDF로 다시 확인하세요.',
    '수치 검색에서 찾은 가까운 후보이며, 실제 인쇄의 정확도나 전역 최적해를 보장하지 않습니다. 새 색의 사진 보정은 외삽 추정입니다. ΔE76의 2·5 구분은 프로그램 안내 기준입니다.'].join('\n');
}
async function runInverse(){
  if(gradientState.running||gradientState.uploading||$('calculateInverse').disabled)return;
  const sequence=++state.inverseSequence;state.inverse=null;
  const controls=['calculateInverse','inversePicker','inverseHex','inverseMode','inverseTac'];
  try{
    const value=$('inverseHex').value.trim();if(!/^#[0-9a-f]{6}$/i.test(value))throw Error('목표색을 #D80202 형식으로 입력해 주세요.');
    $('inversePicker').value=value;controls.forEach(id=>$(id).disabled=true);$('inverseError').textContent='목표색에 가까운 입력색을 계산하고 있습니다…';$('inverseResult').hidden=true;
    const rgb=[1,3,5].map(n=>parseInt(value.slice(n,n+2),16));
    const j=await request('/api/inverse',{payload:{rgb,model_mode:$('inverseMode').value,strength:Number($('strength').value)/100,tac:Number($('inverseTac').value)}});
    const r=await waitJob(j.job);if(sequence!==state.inverseSequence)return;state.inverse=r;const c=r.cmyk_result,g=r.rgb_result;
    const messages={close:'계산상 목표색에 가까운 CMYK 후보를 찾았습니다.',approximate:'근사 재현 후보입니다. 목표색과 예상색의 차이를 확인하세요.',gamut_warning:'목표색에 FOGRA39 색역 경고가 있습니다. 아래의 가까운 예상색을 확인하세요.',difficult:'현재 조건에서 목표색과 가까운 4도 후보를 찾지 못했습니다. 아래는 검색에서 찾은 가장 가까운 후보입니다.'};
    $('inverseAssessment').textContent=messages[r.assessment];$('inverseAssessment').dataset.state=r.assessment;
    [['Target',r.target_rgb],['Cmyk',c.predicted_rgb],['Rgb',g.predicted_rgb]].forEach(([id,color])=>{$('inverse'+id+'Swatch').style.background=hex(color);$('inverse'+id+'Value').textContent=hex(color).toUpperCase();});
    $('inverseCmykValue').textContent+=' · ΔE76 '+c.delta_e76;$('inverseRgbValue').textContent+=' · ΔE76 '+g.delta_e76+(g.delta_e76>5?' · 이 RGB 변환 경로에서는 차이가 큽니다':'');
    $('inverseCmykInput').value=['C','M','Y','K'].map((n,i)=>n+' '+c.cmyk[i]+'%').join(' / ');$('inverseRgbInput').value=hex(g.input_rgb).toUpperCase();
    $('inverseDetail').textContent='CMYK 입력 프로파일: '+r.input_cmyk_profile+' · 총 잉크량: CMYK 추천 '+c.total_ink_percent+'% / RGB 변환 후 '+g.total_ink_percent+'% · '+correctionLabel(r)+' · 목표색 FOGRA39 색역 경고 '+(r.icc_gamut_warning?'있음':'없음');
    $('inverseScope').textContent=r.model_mode==='icc'?'별도 FOGRA39 ICC 표준 예상색을 기준으로 역산했습니다.':c.near_reference&&g.near_reference?'기존 기준색 근처의 사진 보정을 포함한 역산입니다.':'기존 기준에서 먼 새 색의 역산이 포함됩니다. 사진에서 추정한 전체 색상 경향을 확장한 결과입니다.';
    $('inverseError').textContent='';$('inverseResult').hidden=false;
  }catch(e){if(sequence===state.inverseSequence)$('inverseError').textContent=e.message;}
  finally{controls.forEach(id=>$(id).disabled=false);}
}

function bind(){
  bindClipboard();bindGradientCompare();
  bindViewer();
  bindGradient();
  $('inverseDialogBtn').onclick=()=>{$('inverseDialog').showModal();invalidatePredictions();};$('closeInverse').onclick=()=>$('inverseDialog').close();
  $('calculateInverse').onclick=runInverse;$('inversePicker').oninput=()=>{$('inverseHex').value=$('inversePicker').value;resetInverseResult();};
  $('inverseHex').oninput=resetInverseResult;$('inverseHex').onkeydown=e=>{if(e.key==='Enter')runInverse();};
  ['inverseMode','inverseTac'].forEach(id=>$(id).onchange=resetInverseResult);
  $('saveInverseTxt').onclick=async()=>{try{if(state.inverse)await saveBlob(new Blob([inverseText(state.inverse)],{type:'text/plain'}),'HARDYS_inverse_color.txt','text/plain');}catch(e){$('inverseError').textContent=e.message;}};

  $('reconnectBtn').onclick=async()=>{try{await session();error('');if(!state.current){window.location.reload();return;}await refreshPreview();}catch(e){error(e.message);}};
  $('quitBtn').onclick=async()=>{try{await request('/api/shutdown',{payload:{}});status('프로그램 종료됨');error('프로그램을 종료했습니다. 다음에는 START.cmd를 실행해 주세요.');}catch(e){error(e.message);}};
  $('pdfInput').onchange=e=>{const file=e.target.files[0];e.target.value='';importFile(file);};$('rgbInput').onchange=e=>{const file=e.target.files[0];e.target.value='';importFile(file,'rgb');};
  $('caseSelect').onchange=e=>selectCase(e.target.value);$('pageSelect').onchange=async e=>{state.page=Number(e.target.value);$('beforeImage').src=assetURL(currentPage().source);clearPicks();await refreshPreview();};
  $('zoomSelect').onchange=fitImages;['beforeImage','afterImage'].forEach(id=>$(id).onload=fitImages);
  $('strength').oninput=()=>{$('strengthValue').textContent=$('strength').value+'%';};$('strength').onchange=()=>{resetInverseResult();refreshPreview();};$('viewSelect').onchange=paintView;
  $('rangeBtn').onclick=()=>{$('viewSelect').value=$('viewSelect').value==='range'?'matched':'range';paintView();};
  $('pickMode').onchange=()=>{const value=$('pickMode').checked;['beforeImage','photoImage'].forEach(id=>$(id).classList.toggle('pick',value));};
  $('beforeImage').onclick=e=>pick(e,'source');$('photoImage').onclick=e=>pick(e,'target');
  $('photoInput').onchange=async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;busy(true,'기준 사진의 색상 프로파일 해석 중…');try{const r=await request('/api/photo?name='+encodeURIComponent(file.name),{body:file,type:file.type});state.photo=r.photo;state.photoName=r.name;$('photoImage').src=assetURL(r.photo);$('photoCaption').textContent=r.name+' · '+r.info.source_profile+' → sRGB'+(r.info.profile_assumed?' (프로파일 가정)':'')+(r.info.input_warnings?.length?' · '+r.info.input_warnings.join(' '):'');state.targetPick=null;$('targetValue').textContent='기준 사진을 클릭하세요';status('사진 변경 완료 · 기준점을 새로 추가하세요');}catch(e){error(e.message);}finally{busy(false);}};
  $('addAnchor').onclick=async()=>{
    if(!state.sourcePick||!state.targetPick){error('색 선택 모드를 켠 뒤 왼쪽 예상색과 기준 사진에서 같은 인쇄 요소를 각각 클릭해 주세요.');return;}
    const label=$('anchorLabel').value.trim()||'직접 선택한 색 '+(state.calibration.anchors.length+1);
    state.calibration.anchors.push({id:'user_'+Date.now(),label,group:state.current.name+' / '+state.photoName,source_rgb:state.sourcePick.rgb,target_rgb:state.targetPick.rgb,source_xy:state.sourcePick.xy,target_xy:state.targetPick.xy,reference_asset:currentPage().source,photo_asset:state.photo,enabled:true,sample_count:1});
    await saveCalibration();$('anchorLabel').value='';clearPicks();
  };
  $('savePng').onclick=async()=>{if(!state.preview)return;try{const selected=state.displayOutput;const response=await fetch(assetURL(selected.path));if(!response.ok)throw Error('결과 PNG를 읽지 못했습니다. 다시 계산해 주세요.');await saveBlob(await response.blob(),selected.name,'image/png');}catch(e){error(e.message);}};
  $('openPng').onclick=()=>{if(state.preview)window.open(assetURL(state.displayOutput.path),'_blank','noopener');};
  $('saveModel').onclick=async()=>{try{await saveBlob(new Blob([JSON.stringify(state.calibration,null,2)],{type:'application/json'}),'HARDYS_photo_calibration.json','application/json');}catch(e){error(e.message);}};
  $('loadModel').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const doc=JSON.parse(await f.text());if(!Array.isArray(doc.anchors))throw Error('올바른 보정 기준 JSON이 아닙니다.');const result=await request('/api/calibration',{payload:doc});state.calibration=result.calibration;invalidatePredictions();paintAnchors();await refreshPreview();}catch(e){error(e.message);}};
  $('resetModel').onclick=async()=>{try{const result=await request('/api/reset',{payload:{}});state.calibration=result.calibration;invalidatePredictions();paintAnchors();await refreshPreview();}catch(e){error(e.message);}};
  $('colorDialogBtn').onclick=()=>{$('colorDialog').showModal();checkColor();};$('closeColor').onclick=()=>$('colorDialog').close();$('checkHex').onclick=()=>checkColor();$('checkCmyk').onclick=()=>checkColor('cmyk');$('colorPicker').oninput=()=>{$('hexInput').value=$('colorPicker').value;};$('colorPicker').onchange=()=>checkColor();$('hexInput').onkeydown=e=>{if(e.key==='Enter')checkColor();};setupPresets();
  $('helpBtn').onclick=()=>$('help').showModal();$('closeHelp').onclick=()=>$('help').close();
  const drop=$('drop');drop.ondragover=e=>{e.preventDefault();drop.classList.add('drag');};drop.ondragleave=()=>drop.classList.remove('drag');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drag');importFile(e.dataTransfer.files[0]);};
  let syncing=false;['beforeStage','afterStage'].forEach(id=>$(id).onscroll=()=>{if(syncing)return;const from=$(id),to=$(id==='beforeStage'?'afterStage':'beforeStage');syncing=true;to.scrollTop=from.scrollTop;to.scrollLeft=from.scrollLeft;requestAnimationFrame(()=>syncing=false);});
}
async function init(){try{bind();const result=await request('/api/state');state.catalog=result.catalog;state.calibration=result.calibration;if(result.migration_notice){$('migrationNotice').hidden=false;$('migrationNotice').textContent=result.migration_notice.message;}state.photo=state.catalog.photo;$('photoImage').src=assetURL(state.photo);fillCases();paintAnchors();await selectCase(state.catalog.cases[0].id);}catch(e){error(e.message);status('START.cmd로 다시 실행해 주세요');}}
init();

