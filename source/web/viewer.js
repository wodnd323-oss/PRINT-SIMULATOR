'use strict';
const viewerState={drag:null};
function fitViewerImages(){
  const value=$('zoomSelect').value;let displayed=1;
  ['before','after'].forEach(side=>{
    const im=$(side+'Image'),stage=$(side+'Stage');if(!im.naturalWidth||!im.naturalHeight)return;
    const available=window.innerHeight-Math.max(12,stage.getBoundingClientRect().top)-20;
    stage.style.height=Math.max(260,Math.min(window.innerHeight-120,available))+'px';
    const css=getComputedStyle(stage),width=Math.max(1,stage.clientWidth-parseFloat(css.paddingLeft)-parseFloat(css.paddingRight)),height=Math.max(1,stage.clientHeight-parseFloat(css.paddingTop)-parseFloat(css.paddingBottom));
    let scale=value==='fit'?Math.min(width/im.naturalWidth,height/im.naturalHeight):value==='width'?width/im.naturalWidth:Number(value);
    if(!Number.isFinite(scale)||scale<=0)scale=1;
    im.style.width=Math.max(1,Math.round(im.naturalWidth*scale))+'px';im.style.height=Math.max(1,Math.round(im.naturalHeight*scale))+'px';im.style.maxWidth='none';im.style.maxHeight='none';im.dataset.viewerScale=String(scale);
    if(side==='before')displayed=scale;
  });
  $('viewerZoomValue').textContent=Math.round(displayed*100)+'%'+(value==='fit'?' · 전체 맞춤':value==='width'?' · 가로 맞춤':'');
}
function viewerScale(scale,source,event){
  scale=Math.max(.08,Math.min(8,Math.round(scale*100)/100));const select=$('zoomSelect');
  let option=Array.from(select.options).find(o=>Number(o.value)===scale);
  if(!option){option=select.querySelector('option[data-custom]');if(!option){option=new Option();option.dataset.custom='true';select.add(option);}option.value=String(scale);option.textContent=Math.round(scale*100)+'%';}
  const sourceImage=source?source.querySelector('img'):null;const sourceRect=sourceImage?.getBoundingClientRect(),sourceStage=source?.getBoundingClientRect();
  const snapshots=['before','after'].map(side=>{
    const stage=$(side+'Stage'),im=$(side+'Image'),r=im.getBoundingClientRect(),s=stage.getBoundingClientRect();
    const px=event?(event.clientX-sourceStage.left)/sourceStage.width*stage.clientWidth:stage.clientWidth/2,py=event?(event.clientY-sourceStage.top)/sourceStage.height*stage.clientHeight:stage.clientHeight/2;
    const fx=event?(event.clientX-sourceRect.left)/Math.max(1,sourceRect.width):(s.left+px-r.left)/Math.max(1,r.width),fy=event?(event.clientY-sourceRect.top)/Math.max(1,sourceRect.height):(s.top+py-r.top)/Math.max(1,r.height);
    return {stage,im,px,py,fx:Math.max(0,Math.min(1,fx)),fy:Math.max(0,Math.min(1,fy))};
  });
  select.value=String(scale);fitViewerImages();
  snapshots.forEach(({stage,im,px,py,fx,fy})=>{const r=im.getBoundingClientRect(),s=stage.getBoundingClientRect();stage.scrollLeft=stage.scrollLeft+r.left-s.left+fx*r.width-px;stage.scrollTop=stage.scrollTop+r.top-s.top+fy*r.height-py;});
}
function viewerStep(factor){viewerScale((Number($('beforeImage').dataset.viewerScale)||1)*factor);}
async function viewerFullscreen(){
  const area=$('compareArea');
  try{
    if(document.fullscreenElement===area)await document.exitFullscreen();
    else if(area.classList.contains('wide-view'))area.classList.remove('wide-view');
    else{try{await area.requestFullscreen();}catch(e){area.classList.add('wide-view');}}
  }finally{viewerRefreshFullscreen();}
}
function viewerRefreshFullscreen(){const wide=document.fullscreenElement===$('compareArea')||$('compareArea').classList.contains('wide-view');$('viewerFullscreen').textContent=wide?'크게 보기 해제':'비교 화면 크게';requestAnimationFrame(fitViewerImages);}
function bindViewer(){
  $('viewerZoomIn').onclick=()=>viewerStep(1.25);$('viewerZoomOut').onclick=()=>viewerStep(.8);$('viewerFit').onclick=()=>{$('zoomSelect').value='fit';fitViewerImages();};$('viewerFullscreen').onclick=viewerFullscreen;
  document.addEventListener('fullscreenchange',viewerRefreshFullscreen);window.addEventListener('resize',fitViewerImages);
  ['before','after'].forEach(side=>{
    const stage=$(side+'Stage'),im=$(side+'Image');im.draggable=false;stage.tabIndex=0;
    stage.addEventListener('wheel',event=>{if(!im.naturalWidth)return;event.preventDefault();viewerScale((Number(im.dataset.viewerScale)||1)*Math.exp(-event.deltaY*.0015),stage,event);},{passive:false});
    stage.addEventListener('pointerdown',event=>{if(event.button!==0||$('pickMode').checked)return;viewerState.drag={stage,x:event.clientX,y:event.clientY,left:stage.scrollLeft,top:stage.scrollTop};stage.setPointerCapture(event.pointerId);stage.classList.add('grabbing');});
    stage.addEventListener('pointermove',event=>{const d=viewerState.drag;if(!d||d.stage!==stage)return;stage.scrollLeft=d.left-event.clientX+d.x;stage.scrollTop=d.top-event.clientY+d.y;});
    const end=()=>{if(viewerState.drag?.stage===stage)viewerState.drag=null;stage.classList.remove('grabbing');};stage.addEventListener('pointerup',end);stage.addEventListener('pointercancel',end);stage.addEventListener('lostpointercapture',end);
    stage.addEventListener('keydown',event=>{if(event.key==='+'||event.key==='='){event.preventDefault();viewerStep(1.25);}if(event.key==='-'){event.preventDefault();viewerStep(.8);}if(event.key==='0'){event.preventDefault();$('zoomSelect').value='fit';fitViewerImages();}});
  });
  $('pickMode').addEventListener('change',()=>{['beforeStage','afterStage'].forEach(id=>$(id).classList.toggle('picking',$('pickMode').checked));});
}
