'use strict';
const gradientCompare={zoom:1,drag:null,syncing:false};
function fitGradientCompare(){
  if(!$('gradientCompareDialog').open)return;
  ['gradientCompareTarget','gradientCompareOutput'].forEach(id=>{
    const im=$(id),stage=im.parentElement;if(!im.naturalWidth)return;
    const w=Math.max(1,stage.clientWidth-24),h=Math.max(1,stage.clientHeight-24);
    const scale=Math.min(w/im.naturalWidth,h/im.naturalHeight)*gradientCompare.zoom;
    im.style.width=(im.naturalWidth*scale)+'px';im.style.height=(im.naturalHeight*scale)+'px';
    im.style.marginTop=Math.max(0,(h-im.naturalHeight*scale)/2)+'px';
  });
  $('gradientCompareZoomValue').textContent='맞춤 기준 '+Math.round(gradientCompare.zoom*100)+'%';
  $('gradientCompareZoomOut').disabled=gradientCompare.zoom<=1;
  $('gradientCompareZoomIn').disabled=gradientCompare.zoom>=8;
}
function zoomGradientCompare(value){
  const stages=['gradientCompareBeforeStage','gradientCompareAfterStage'].map($);
  const centers=stages.map(s=>[(s.scrollLeft+s.clientWidth/2)/s.scrollWidth,(s.scrollTop+s.clientHeight/2)/s.scrollHeight]);
  gradientCompare.zoom=Math.max(1,Math.min(8,value));fitGradientCompare();
  stages.forEach((s,i)=>{s.scrollLeft=centers[i][0]*s.scrollWidth-s.clientWidth/2;s.scrollTop=centers[i][1]*s.scrollHeight-s.clientHeight/2;});
}
function openGradientCompare(){
  const r=gradientState.result;if(!r)return;
  gradientCompare.zoom=1;
  $('gradientCompareTarget').src=assetURL(r.target_preview);
  $('gradientCompareOutput').src=assetURL(r.two_stop.predicted_preview);
  $('gradientCompareInfo').textContent='두 색 추천 조합 · '+predictionModeLabel(r)+' · '+correctionLabel(r)+' · 33개 표본 평균 ΔE76 '+r.two_stop.mean_delta_e76+' / 표본 최대 '+r.two_stop.max_delta_e76;
  $('gradientCompareDialog').showModal();fitGradientCompare();
  ['gradientCompareBeforeStage','gradientCompareAfterStage'].forEach(id=>{$(id).scrollLeft=0;$(id).scrollTop=0;});
}
function bindGradientCompare(){
  $('openGradientCompare').onclick=openGradientCompare;
  $('closeGradientCompare').onclick=()=>$('gradientCompareDialog').close();
  $('gradientCompareZoomIn').onclick=()=>zoomGradientCompare(gradientCompare.zoom*1.25);
  $('gradientCompareZoomOut').onclick=()=>zoomGradientCompare(gradientCompare.zoom/1.25);
  $('gradientCompareFit').onclick=()=>zoomGradientCompare(1);
  ['gradientCompareTarget','gradientCompareOutput'].forEach(id=>{$(id).onload=fitGradientCompare;$(id).ondragstart=e=>e.preventDefault();});
  ['gradientCompareBeforeStage','gradientCompareAfterStage'].forEach(id=>{
    const stage=$(id);
    stage.addEventListener('wheel',e=>{e.preventDefault();zoomGradientCompare(gradientCompare.zoom*(e.deltaY<0?1.12:1/1.12));},{passive:false});
    stage.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();stage.setPointerCapture(e.pointerId);gradientCompare.drag={stage,x:e.clientX,y:e.clientY,left:stage.scrollLeft,top:stage.scrollTop};stage.classList.add('dragging');};
    stage.onpointermove=e=>{const d=gradientCompare.drag;if(!d||d.stage!==stage)return;stage.scrollLeft=d.left+d.x-e.clientX;stage.scrollTop=d.top+d.y-e.clientY;};
    const release=()=>{gradientCompare.drag=null;stage.classList.remove('dragging');};
    stage.onpointerup=release;stage.onpointercancel=release;stage.onlostpointercapture=release;
    stage.onscroll=()=>{
      if(gradientCompare.syncing)return;gradientCompare.syncing=true;
      const other=$(id==='gradientCompareBeforeStage'?'gradientCompareAfterStage':'gradientCompareBeforeStage');
      other.scrollLeft=stage.scrollLeft;other.scrollTop=stage.scrollTop;
      requestAnimationFrame(()=>gradientCompare.syncing=false);
    };
  });
  $('gradientCompareDialog').addEventListener('close',()=>{gradientCompare.drag=null;});
  window.addEventListener('resize',fitGradientCompare);
}
