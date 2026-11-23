// Fresh review of the released V11.2 functions. DOM and I/O are controlled;
// production scripts are read verbatim, with only the automatic init call omitted.
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto'),assert=require('assert/strict');
const {File}=require('buffer');
const OUT=__dirname,APP=path.resolve(OUT,'../released_app');
const names=['web/viewer.js','web/gradient.js','web/gradient_compare.js','web/clipboard.js','web/app.js'];
const sources=Object.fromEntries(names.map(n=>[n,fs.readFileSync(path.join(APP,n),'utf8')]));
const report={review:'Published V11.2 UI state/contracts, independent controlled-response execution',environment:{node:process.version,platform:process.platform,browser_used:false},source_sha256:Object.fromEntries(names.map(n=>[n,crypto.createHash('sha256').update(fs.readFileSync(path.join(APP,n))).digest('hex')])),checks:[],findings:[]};
const clone=x=>JSON.parse(JSON.stringify(x));
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};}
function record(name,passed,evidence){report.checks.push({name,passed:!!passed,evidence});assert(passed,name);}
function finding(id,severity,title,evidence,source){report.findings.push({id,severity,title,evidence,source});}

function harness(){
  const nodes=new Map(),requests=[],jobs=[],downloads=[],fetches=[],saved=[];
  class Element{
    constructor(id=''){this.id=id;this.value='';this.textContent='';this.style={};this.dataset={};this.children=[];this.options=[];this.listeners={};this.open=false;this.hidden=false;this.disabled=false;this.checked=false;this.naturalWidth=200;this.naturalHeight=100;this.clientWidth=500;this.clientHeight=300;this.scrollLeft=0;this.scrollTop=0;this.scrollWidth=500;this.scrollHeight=300;this.rect={left:0,top:0,width:200,height:100};this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),contains:x=>this.classes.has(x),toggle:(x,on)=>{if(on===undefined)on=!this.classes.has(x);on?this.classes.add(x):this.classes.delete(x);}};}
    append(...items){items.forEach(x=>{if(x&&typeof x==='object')x.parentElement=this;this.children.push(x);});}
    prepend(...items){this.children.unshift(...items);}
    replaceChildren(...items){this.children=[];this.options=[];this.append(...items);}
    add(option){this.options.push(option);this.append(option);}
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
    async emit(name,event={}){event.currentTarget??=this;event.target??=this;event.preventDefault??=()=>{};if(this['on'+name])await this['on'+name](event);for(const fn of this.listeners[name]||[])await fn(event);}
    showModal(){this.open=true;} close(){this.open=false;for(const fn of this.listeners.close||[])fn({target:this});}
    setAttribute(k,v){this[k]=v;} getBoundingClientRect(){return this.rect;}
    querySelector(sel){return sel==='img'?this.children.find(x=>x instanceof Element):this.options.find(x=>x.dataset.custom);}
    closest(){return this.textField?this:null;} select(){} scrollIntoView(){} setPointerCapture(){}
    getContext(){return new Proxy({}, {get:()=>()=>{}});} click(){return this.onclick?.();}
  }
  const $=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
  const document={getElementById:$,createElement:tag=>new Element(tag),createTextNode:text=>text,querySelector:selector=>$(selector),querySelectorAll:selector=>selector==='dialog[open]'?[...nodes.values()].filter(n=>n.id.endsWith('Dialog')&&n.open):[],addEventListener(){},fullscreenElement:null};
  const window={innerHeight:900,HARDYS_TOKEN:'test-token',addEventListener(){},location:{reload(){}},open(){}};
  const ctx={document,window,Element,File,Blob,console,URL,JSON,Math,Number,String,Error,TypeError,Array,Date,Promise,Uint8Array,AbortController,setTimeout,clearTimeout,navigator:{},requestAnimationFrame:fn=>fn(),getComputedStyle:()=>({paddingLeft:'0',paddingRight:'0',paddingTop:'0',paddingBottom:'0'}),Option:function(text='',value=''){const x=new Element('option');x.textContent=text;x.value=value;return x;}};
  vm.createContext(ctx);
  for(const n of names)vm.runInContext(n==='web/app.js'?sources[n].replace(/\binit\(\);\s*$/,''):sources[n],ctx,{filename:n});
  vm.runInContext('globalThis.auditState=state;globalThis.auditGradient=gradientState;globalThis.auditClipboard=clipboardState;',ctx);
  const state=ctx.auditState,g=ctx.auditGradient;
  const cases=['A','B'].map(id=>({id,name:'case '+id,kind:'rgb',pages:[{source:'assets/'+id+'_source.png',relative:'assets/'+id+'_proof.png',TAC300:'assets/'+id+'_gamut.png'}]}));
  state.catalog={cases};state.current=cases[0];state.calibration={pipeline:'source_srgb_photo_v11',schema_version:11,anchors:[{id:'a',label:'a',group:'g',enabled:true,source_rgb:[18,121,141],target_rgb:[20,110,120]},{id:'b',label:'b',group:'g',enabled:true,source_rgb:[224,186,124],target_rgb:[210,180,120]}]};state.photo='assets/photoA.png';
  $('strength').value='100';$('strengthValue').textContent='100%';$('viewSelect').value='matched';$('viewSelect').options=[{},{},{},{}];$('inverseMode').value='photo';$('inverseTac').value='300';$('inverseHex').value='#123456';$('colorMode').value='photo';$('hexInput').value='#00B941';$('pickMode').checked=true;$('zoomSelect').value='fit';
  for(const side of ['before','after'])$(side+'Stage').append($(side+'Image'));
  for(const side of ['Target','Output'])$('gradientCompare'+side).parentElement=$('gradientCompare'+(side==='Target'?'Before':'After')+'Stage');
  const preview=(asset,strength=1)=>({matched:'exports/'+asset.replace(/\W/g,'_')+'_matched.png',range:'exports/range.png',statistics:{strength,near_reference_percent:10,transition_percent:20,unsupported_percent:70,reference_support:{chromatic_samples:1}},export_name:'output.png'});
  let autoPreview=true;
  ctx.request=(route,options={})=>{const d=deferred(),row={route,payload:options.payload===undefined?undefined:clone(options.payload),...d};requests.push(row);if(route==='/api/preview'&&autoPreview){const job='auto-'+requests.length;row.resolve({job});jobs.push({job,auto:preview(row.payload.asset,row.payload.strength)});}return row.promise;};
  ctx.waitJob=id=>{const existing=jobs.find(x=>x.job===id);if(existing?.auto)return Promise.resolve(existing.auto);const d=deferred();jobs.push({job:id,...d});return d.promise;};
  ctx.fetch=async url=>{fetches.push(url);return{ok:true,blob:async()=>new Blob([url])};};
  ctx.saveBlob=async(blob,name,mime)=>downloads.push({name,mime,content:await blob.text()});
  ctx.bind();
  return{ctx,$,nodes,state,g,requests,jobs,downloads,fetches,saved,preview,setAutoPreview:x=>{autoPreview=x;},Element};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function inverseResult(rgb=[18,52,86]){return{target_rgb:rgb,rgb_result:{input_rgb:rgb,predicted_rgb:rgb,cmyk:[10,20,30,40],delta_e76:0,total_ink_percent:100,reference_support:{chromatic_samples:1,near_samples:1}},cmyk_result:{input_rgb:rgb,predicted_rgb:rgb,cmyk:[10,20,30,40],delta_e76:0,total_ink_percent:100,reference_support:{chromatic_samples:1,near_samples:1}},assessment:'close',model_mode:'photo',strength:1,tac_limit:300,input_cmyk_profile:'GRACoL2013_CRPC6.icc',calibration_sha256:'snapshot'};}
function gradientResult(){const rec=(n,color)=>({stops:Array.from({length:n},(_,i)=>({position_percent:i*100/(n-1),input_rgb:color,target_rgb:color,predicted_rgb:color,delta_e76:0})),mean_delta_e76:n===3?1:10,max_delta_e76:n===3?2:20,max_ink_percent:150,input_preview:'exports/'+n+'_input.png',predicted_preview:'exports/'+n+'_predicted.png',reference_support:{total_samples:33,neutral_samples:0,chromatic_samples:33,near_samples:n===3?33:0,transition_samples:0,extrapolated_samples:n===3?0:33,near_percent:n===3?100:0,transition_percent:0,extrapolated_percent:n===3?0:100,neutral_chroma_max:16,near_delta_e76_max:12,extrapolated_delta_e76_min:26}});return{analysis:{selection:'line',direction:'p1 to p2',style:'selected line',css_angle:null,source_points:[[11,15],[180,60]],source_points_normalized:[[11/199,15/99],[180/199,60/99]],source_image_size:[200,100],source_line_css_angle:104.9,preview_css_angle:90,spatial_residual_delta_e76:0},two_stop:rec(2,[10,20,30]),three_stop:rec(3,[50,60,70]),target_preview:'assets/target.png',model_mode:'photo',strength:1,tac_limit:300,input_cmyk_profile:'GRACoL2013_CRPC6.icc',icc_gamut_warning_percent:0,note:'fixture'};}

async function main(){
  // 1. Pick response after changing the source page: exact addAnchor handler.
  {
    const h=harness(),p=h.ctx.pick({currentTarget:h.$('beforeImage'),clientX:20,clientY:10},'source');
    const sourceRequest=h.requests.at(-1);await h.ctx.selectCase('B');
    sourceRequest.resolve({rgb:[7,8,9],xy:[20,10]});await p;
    h.state.targetPick={rgb:[70,80,90],xy:[100,50]};h.ctx.saveCalibration=async()=>h.saved.push(clone(h.state.calibration));
    await h.$('addAnchor').onclick();const added=h.saved[0].anchors.at(-1);
    const evidence={requested_asset:sourceRequest.payload.asset,now_selected_asset:h.state.current.pages[0].source,saved_anchor:added};
    record('reproduced_pick_after_source_navigation',added.reference_asset!==sourceRequest.payload.asset&&JSON.stringify(added.source_rgb)==='[7,8,9]',evidence);
    finding('UI-01','high','A late source pick can be saved with the newly selected source file as its provenance',evidence,['web/app.js:64-70','web/app.js:100-104','web/app.js:233-237']);
  }
  // 2. Two picks in one image complete out of order.
  {
    const h=harness(),a=h.ctx.pick({currentTarget:h.$('beforeImage'),clientX:10,clientY:10},'source'),b=h.ctx.pick({currentTarget:h.$('beforeImage'),clientX:150,clientY:60},'source');
    h.requests[1].resolve({rgb:[150,60,1],xy:[150,60]});await b;h.requests[0].resolve({rgb:[10,10,1],xy:[10,10]});await a;
    record('reproduced_out_of_order_pick',h.state.sourcePick.xy[0]===10,{last_click:[150,60],shown_pick:clone(h.state.sourcePick)});
  }
  // 3. A superseded save response rolls back the UI model and feeds the next save.
  {
    const h=harness();h.ctx.paintAnchors();const rows=h.$('anchorRows').children;
    const a=rows[0].children[0].children[0],b=rows[1].children[0].children[0];
    a.checked=false;const first=a.onchange();b.checked=false;const second=b.onchange();
    const calls=h.requests.filter(r=>r.route==='/api/calibration');const newest=clone(calls[1].payload);
    calls[1].resolve({calibration:clone(calls[1].payload)});await second;
    calls[0].resolve({calibration:clone(calls[0].payload)});await first;
    const displayed=clone(h.state.calibration);const third=h.ctx.saveCalibration(),thirdCall=h.requests.filter(r=>r.route==='/api/calibration').at(-1);
    const evidence={first_request_enabled:calls[0].payload.anchors.map(x=>x.enabled),last_user_request_enabled:newest.anchors.map(x=>x.enabled),ui_after_reordered_responses:displayed.anchors.map(x=>x.enabled),next_save_enabled:thirdCall.payload.anchors.map(x=>x.enabled)};
    thirdCall.resolve({calibration:clone(thirdCall.payload)});await third;
    record('reproduced_calibration_save_response_rollback',displayed.anchors[1].enabled===true&&newest.anchors[1].enabled===false,evidence);
    finding('UI-02','medium','Out-of-order calibration save replies restore older toggles and carry them into the next save',evidence,['web/app.js:87-98']);
  }
  // 4. Rejected addAnchor leaves the unsaved anchor in state and clears picks.
  {
    const h=harness();h.state.calibration.anchors=Array.from({length:128},(_,i)=>({...clone(h.state.calibration.anchors[0]),id:'a'+i}));
    h.state.sourcePick={rgb:[11,22,33],xy:[4,5]};h.state.targetPick={rgb:[21,32,43],xy:[14,15]};h.$('anchorLabel').value='rejected anchor';
    const pending=h.$('addAnchor').onclick();const save=h.requests.find(r=>r.route==='/api/calibration');save.reject(new Error('기준점은 최대 128개입니다.'));await pending;
    const evidence={submitted_count:save.payload.anchors.length,local_count_after_rejection:h.state.calibration.anchors.length,source_pick:h.state.sourcePick,target_pick:h.state.targetPick,label:h.$('anchorLabel').value,error:h.$('error').textContent};
    record('reproduced_rejected_anchor_retained',evidence.local_count_after_rejection===129&&evidence.source_pick===null,evidence);
    finding('UI-03','medium','A rejected 129th anchor stays in client state and blocks subsequent calibration saves',evidence,['web/app.js:97-99','web/app.js:233-237','server.py:25']);
  }
  // Two image color clicks can queue before the first pick starts inverse work.
  // The second pick changes the target field but runInverse is already locked,
  // so the first target's answer is displayed under the second target's input.
  {
    const h=harness();h.g.asset='assets/target.png';h.g.image={naturalWidth:200,naturalHeight:100};h.$('targetImageTool').value='color';
    const canvas=h.$('targetImageCanvas');
    const first=canvas.onpointerdown({clientX:10,clientY:10}),second=canvas.onpointerdown({clientX:150,clientY:60});
    const firstPick=h.requests[0],secondPick=h.requests[1];
    firstPick.resolve({rgb:[10,20,30],xy:[10,10]});await tick();
    const inverseCall=h.requests.find(x=>x.route==='/api/inverse');
    secondPick.resolve({rgb:[210,220,230],xy:[150,60]});await second;
    inverseCall.resolve({job:'picked-color'});await tick();h.jobs.find(x=>x.job==='picked-color').resolve(inverseResult([10,20,30]));await first;
    const evidence={first_click:[10,10],last_click:[150,60],inverse_request_rgb:inverseCall.payload.rgb,current_target_hex:h.$('inverseHex').value,visible_result_target:h.state.inverse.target_rgb,inverse_result_hidden:h.$('inverseResult').hidden};
    record('reproduced_target_image_pick_inverse_mismatch',evidence.current_target_hex==='#d2dce6'&&JSON.stringify(evidence.visible_result_target)==='[10,20,30]'&&!evidence.inverse_result_hidden,evidence);
    finding('UI-04','high','Two image-color picks can leave a visible inverse result for a different target than the current input',evidence,['web/gradient.js:142-146','web/app.js:190-207']);
  }
  // 5. Main preview guards both late successes and late errors.
  {
    const h=harness();h.setAutoPreview(false);const a=h.ctx.refreshPreview();h.requests[0].resolve({job:'old'});await tick();
    h.state.page=0;h.state.current=h.state.catalog.cases[1];const b=h.ctx.refreshPreview();h.requests[1].resolve({job:'new'});await tick();
    h.jobs.find(x=>x.job==='new').resolve(h.preview('B'));await b;h.jobs.find(x=>x.job==='old').resolve(h.preview('A'));await a;
    record('main_preview_late_success_ignored',h.state.preview.matched===h.preview('B').matched,{shown:h.$('afterImage').src,busy:h.state.busy});
    const old=h.ctx.refreshPreview();h.requests.at(-1).resolve({job:'old-fail'});await tick();const next=h.ctx.refreshPreview();h.requests.at(-1).resolve({job:'latest'});await tick();
    h.jobs.find(x=>x.job==='latest').resolve(h.preview('latest'));await next;h.jobs.find(x=>x.job==='old-fail').reject(new Error('late failure'));await old;
    record('main_preview_late_error_ignored',h.state.preview.matched===h.preview('latest').matched&&h.$('error').hidden===true);
  }
  // 6. Actual calibration invalidation blocks pending inverse and gradient results.
  {
    const h=harness(),pending=h.ctx.runInverse();const req=h.requests.at(-1);req.resolve({job:'inv'});await tick();h.ctx.invalidatePredictions();h.jobs.find(x=>x.job==='inv').resolve(inverseResult());await pending;
    record('inverse_calibration_invalidation',h.state.inverse===null&&h.$('inverseResult').hidden===true&&!h.$('calculateInverse').disabled);
    h.g.asset='assets/target.png';h.g.image={naturalWidth:200,naturalHeight:100};h.$('targetImageTool').value='line';h.g.line=[[11,15],[180,60]];
    const p=h.ctx.runGradient();h.requests.at(-1).resolve({job:'grad'});await tick();h.ctx.invalidatePredictions();h.jobs.find(x=>x.job==='grad').resolve(gradientResult());await p;
    record('gradient_calibration_invalidation',h.g.result===null&&h.$('gradientResult').hidden===true&&!h.g.running);
  }
  // 7. Variant support, preview, large comparison, PNG and TXT stay aligned.
  {
    const h=harness();h.g.result=gradientResult();h.g.selectedVariant='two_stop';h.$('gradientCompareDialog').open=true;h.ctx.renderGradientResult();
    h.ctx.selectGradientVariant('three_stop');await h.$('saveGradientPng').onclick();await h.$('saveGradientTxt').onclick();
    const evidence={input:h.$('gradientInputPreview').src,output:h.$('gradientOutputPreview').src,compare:h.$('gradientCompareOutput').src,support:h.$('gradientSupport').textContent,compare_support:h.$('gradientCompareInfo').textContent,png:h.downloads[0],txt:h.downloads[1].content};
    record('selected_three_variant_export_and_support',evidence.png.name.includes('_3_')&&evidence.png.content.includes('3_input')&&evidence.input.includes('3_input')&&evidence.output.includes('3_predicted')&&evidence.compare.includes('3_predicted')&&evidence.support.includes('가까움 100%')&&evidence.compare_support.includes('가까움 100%')&&evidence.txt.includes('[현재 선택] 3색'),evidence);
    record('line_text_retains_selection_and_angle_scope',evidence.txt.includes('(11, 15)')&&evidence.txt.includes('(180, 60)')&&evidence.txt.includes('전체 영역의 그라데이션 각도를 추정하지 않습니다')&&evidence.txt.includes('200 × 100'));
  }
  // 8. Pixels selected at different display zooms use the same image coordinates.
  {
    const h=harness(),im=h.$('beforeImage');im.naturalWidth=1000;im.naturalHeight=500;im.rect={left:20,top:30,width:500,height:250};
    const first=h.ctx.pick({currentTarget:im,clientX:145,clientY:80},'source');const c1=h.requests.at(-1);c1.resolve({rgb:[1,2,3],xy:[250,100]});await first;
    im.rect={left:-80,top:-20,width:2000,height:1000};const second=h.ctx.pick({currentTarget:im,clientX:420,clientY:180},'source');const c2=h.requests.at(-1);c2.resolve({rgb:[1,2,3],xy:[250,100]});await second;
    record('source_pick_coordinates_at_different_zoom',c1.payload.x===250&&c1.payload.y===100&&c2.payload.x===250&&c2.payload.y===100,{first:c1.payload,second:c2.payload});
    const canvas=h.$('targetImageCanvas');canvas.rect={left:100,top:20,width:400,height:200};h.g.image={naturalWidth:2000,naturalHeight:1000};
    record('gradient_target_coordinate_scale',JSON.stringify(h.ctx.gradientPosition({clientX:200,clientY:70}))==='[500,250]');
  }
  // 9. Clipboard PNG preserves bytes; route is rechecked after clipboard wait.
  {
    const h=harness(),raw=Uint8Array.from([137,80,78,71,0,1,2,3,255]),file=await h.ctx.clipboardPrepareFile(new Blob([raw],{type:'image/png'}));
    record('clipboard_png_bytes_unchanged',Buffer.from(await file.arrayBuffer()).equals(Buffer.from(raw))&&file.type==='image/png');
    const wait=deferred();const p=h.ctx.pasteClipboardImage('main',()=>wait.promise);h.$('inverseDialog').open=true;wait.resolve(new Blob([raw],{type:'image/png'}));await p;
    record('clipboard_changed_destination_rejected',h.requests.length===0&&h.$('pasteImageMessage').textContent.includes('화면이 바뀌었습니다'),{message:h.$('pasteImageMessage').textContent});
  }
  report.completed=true;
}
main().catch(e=>{report.completed=false;report.failure=e.stack;process.exitCode=1;}).finally(()=>{fs.writeFileSync(path.join(OUT,'ui_state_results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({completed:report.completed,checks:report.checks.length,findings:report.findings.map(x=>({id:x.id,severity:x.severity,title:x.title})),failure:report.failure}));});
