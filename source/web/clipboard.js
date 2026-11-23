'use strict';
const clipboardState={busy:false,bound:false};
function clipboardTarget(){
  if(Array.from(document.querySelectorAll('dialog[open]')).some(dialog=>dialog.id!=='inverseDialog'))return null;
  return $('inverseDialog').open?'target':'main';
}
function clipboardMessage(target,text,failed=false){
  const node=$(target==='target'?'pasteTargetMessage':'pasteImageMessage');
  node.textContent=text;node.classList.toggle('paste-error',failed);
}
function clipboardTextField(node){
  return node instanceof Element&&(node.isContentEditable||Boolean(node.closest('textarea,input:not([type]),input[type=text],input[type=search],input[type=url],input[type=email],input[type=tel],input[type=password],input[type=number]')));
}
function clipboardBlocked(target){
  return !state.catalog||state.busy||(target==='target'&&(gradientState.running||gradientState.uploading||$('calculateInverse').disabled));
}
function clipboardImageFile(data){
  const isImage=file=>file&&(/^image\//i.test(file.type)||/\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name||''));
  for(const item of Array.from(data?.items||[])){
    if(item.kind==='file'){const file=item.getAsFile();if(isImage(file))return file;}
  }
  return Array.from(data?.files||[]).find(isImage)||null;
}
async function clipboardReadImage(){
  if(!navigator.clipboard?.read)throw Error('이 브라우저에서는 버튼으로 붙여넣을 수 없습니다. 화면의 빈 부분을 클릭한 뒤 Ctrl+V를 눌러 주세요.');
  let items;
  try{items=await navigator.clipboard.read();}
  catch(e){throw Error('클립보드를 읽지 못했습니다. 화면의 빈 부분을 클릭한 뒤 Ctrl+V를 눌러 주세요.');}
  for(const item of items){
    const type=['image/png','image/jpeg','image/webp','image/gif','image/bmp'].find(t=>item.types.includes(t));
    if(type)return await item.getType(type);
  }
  throw Error('복사된 이미지가 없습니다. 이미지에서 “이미지 복사”를 하거나 Win+Shift+S로 캡처한 뒤 다시 붙여넣어 주세요.');
}
async function clipboardPrepareFile(blob){
  if(!blob||!blob.size)throw Error('복사된 이미지 데이터를 읽을 수 없습니다. 이미지를 다시 복사해 주세요.');
  if(blob.size>220*1024*1024)throw Error('220MB 이하 이미지를 붙여넣어 주세요.');
  let type=blob.type.toLowerCase(),ext;
  // Keep original PNG/JPEG bytes and embedded ICC profiles whenever available.
  if(type==='image/png')ext='png';
  else if(type==='image/jpeg'||type==='image/jpg'){ext='jpg';type='image/jpeg';}
  else if(!type&&/\.(png|jpe?g)$/i.test(blob.name||'')){
    ext=/\.png$/i.test(blob.name)?'png':'jpg';type=ext==='png'?'image/png':'image/jpeg';
  }else{
    if(!/^image\/(webp|gif|bmp|x-ms-bmp)$/i.test(type))throw Error('이 복사 형식은 지원되지 않습니다. PNG/JPG 파일을 선택하거나 화면을 캡처해 붙여넣어 주세요.');
    let bitmap;
    try{
      bitmap=await createImageBitmap(blob);
      if(bitmap.width*bitmap.height>80000000)throw Error('이미지가 너무 큽니다. 필요한 부분만 캡처해 주세요.');
      const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
      canvas.getContext('2d',{colorSpace:'srgb'}).drawImage(bitmap,0,0);
      blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
      if(!blob)throw Error('이미지 변환에 실패했습니다.');
      ext='png';type='image/png';
    }catch(e){throw Error('복사된 이미지를 열지 못했습니다. PNG/JPG로 저장하거나 화면을 캡처해 주세요.');}
    finally{bitmap?.close();}
  }
  const stamp=new Date().toISOString().replace(/[^0-9]/g,'');
  return new File([blob],'붙여넣은_이미지_'+stamp+'.'+ext,{type});
}
async function pasteClipboardImage(target,getBlob){
  if(clipboardState.busy||clipboardBlocked(target)){clipboardMessage(target,'현재 이미지 처리가 끝난 뒤 다시 붙여넣어 주세요.',true);return;}
  clipboardState.busy=true;
  ['pasteImageBtn','pasteTargetBtn'].forEach(id=>$(id).disabled=true);
  clipboardMessage(target,'복사한 이미지를 읽고 있습니다…');
  try{
    const file=await clipboardPrepareFile(await getBlob());
    if(clipboardTarget()!==target)throw Error('열려 있는 화면이 바뀌었습니다. 붙여넣을 화면에서 다시 시도해 주세요.');
    if(clipboardBlocked(target))throw Error('현재 이미지 처리가 끝난 뒤 다시 붙여넣어 주세요.');
    if(target==='target')$('targetImagePanel').open=true;
    const ok=target==='target'?await uploadTargetImage(file):await importFile(file,'rgb');
    if(!ok)throw Error(target==='target'?$('gradientMessage').textContent:($('error').textContent||'이미지를 불러오지 못했습니다. 다시 붙여넣어 주세요.'));
    clipboardMessage(target,target==='target'?'목표 이미지 붙여넣기 완료':'비교 이미지 붙여넣기 완료');
  }catch(e){clipboardMessage(target,e.message,true);}
  finally{clipboardState.busy=false;['pasteImageBtn','pasteTargetBtn'].forEach(id=>$(id).disabled=false);}
}
function bindClipboard(){
  if(clipboardState.bound)return;clipboardState.bound=true;
  $('pasteImageBtn').onclick=()=>pasteClipboardImage('main',clipboardReadImage);
  $('pasteTargetBtn').onclick=()=>pasteClipboardImage('target',clipboardReadImage);
  document.addEventListener('paste',event=>{
    if(event.defaultPrevented||clipboardTextField(event.target))return;
    const target=clipboardTarget();if(!target)return;
    // Capture the File synchronously: browser paste data expires after the event.
    const file=clipboardImageFile(event.clipboardData);if(!file)return;
    event.preventDefault();void pasteClipboardImage(target,()=>file);
  });
}
