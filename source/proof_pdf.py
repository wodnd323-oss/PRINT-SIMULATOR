"""HARDYS offline FOGRA39 PDF preview. Never writes to the input PDF."""
import argparse,pathlib,subprocess,hashlib,json,shutil,sys,html,base64,webbrowser
from PIL import Image,ImageCms
from pypdf import PdfReader
BASE=pathlib.Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def find_gs():
 bundled=BASE/'runtime/ghostscript/bin/gswin64c.exe'
 if bundled.is_file():return str(bundled)
 p=shutil.which('gswin64c') or shutil.which('gs')
 if p:return p
 for root in ('C:/Program Files/gs','C:/Program Files (x86)/gs'):
  matches=sorted(pathlib.Path(root).glob('*/bin/gswin*c.exe'))
  if matches:return str(matches[-1])
 raise RuntimeError('Ghostscript is required. Install the official Windows version from ghostscript.com.')
def build_result_view(out,info):
 photo=BASE/'photos/printed_case_crop.png'
 photo_uri='data:image/png;base64,'+base64.b64encode(photo.read_bytes()).decode() if photo.exists() else ''
 page_options=''.join(f'<option value="{n}">{n} 페이지</option>' for n in range(1,info['pages']+1))
 document='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HARDYS 신규 PDF 프루핑</title>
<style>body{margin:0;background:#eee;color:#222;font:15px/1.6 "Malgun Gothic",Arial}header{background:#222;color:#fff;padding:15px 24px}main{padding:20px}h1{font-size:21px;margin:0}select,input,button{font:inherit;padding:6px;margin:5px}section{background:white;padding:12px;border:1px solid #ccc}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.stage{height:66vh;background:#808080;text-align:center;overflow:auto;padding:12px}.stage img{max-width:100%;max-height:100%;vertical-align:middle}p{margin:8px 0}.note{background:white;padding:12px;margin-bottom:12px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>
<header><h1>HARDYS · 新규 PDF FOGRA39 프루핑</h1></header><main><p><b>@@SOURCE@@</b></p><div class="note">프로파일: @@PROFILE@@ · 원본 PDF는 변경하지 않았습니다.<br>모니터 미측정 상태의 인쇄 시뮬레이션이며 실물 일치를 보장하지 않습니다. 미리보기 PNG에는 이미 프루핑이 적용되어 있습니다.</div>
<label>페이지 <select id="page">@@PAGES@@</select></label><label>보기 <select id="mode"><option value="relative">표준 색상 · 상대 비색계</option><option value="paper">용지·검정 시뮬레이션</option><option value="TAC300">총 잉크량 300% 초과</option></select></label><button id="zoom">실제 픽셀 / 화면 맞춤</button>
<div class="grid"><section><b>선택한 PDF의 인쇄 예상색</b><div class="stage"><img id="proof" alt="PDF 인쇄 예상색"></div><p id="desc"></p></section><section><b id="photoTitle">참고용 사진 · 기존 7번 케이스</b><div class="stage"><img id="photo" src="@@PHOTO@@" alt="실물 참고 사진"></div><label>비교할 실물 사진 선택 <input type="file" id="photoInput" accept="image/png,image/jpeg"></label><p>사진은 조명·노출·화이트밸런스가 포함된 참고자료입니다. 사진을 선택해도 업로드하지 않습니다.</p></section></div>
<script>const $=x=>document.getElementById(x);let fit=true;function refresh(){let n=$('page').value.padStart(2,'0'),mode=$('mode').value;$('proof').src='page_'+n+'_'+mode+'.png';$('desc').textContent=mode==='TAC300'?'마젠타: 총 잉크량 300% 초과. 작업선·등록색도 포함되며 색역 경고와 다릅니다.':mode==='paper'?'절대 비색계, BPC 끔. 용지 흰색과 인쇄 검정의 대비 감소를 시뮬레이션합니다.':'원본→CMYK: 상대 비색계+BPC. CMYK→화면: 상대 비색계, BPC 끔. 인쇄 검정의 대비를 유지합니다.'} $('page').onchange=refresh;$('mode').onchange=refresh;$('zoom').onclick=()=>{fit=!fit;$('proof').style.maxWidth=fit?'100%':'none';$('proof').style.maxHeight=fit?'100%':'none'};$('photoInput').onchange=e=>{let f=e.target.files[0];if(!f)return;if(!/\\.(png|jpe?g)$/i.test(f.name)){alert('PNG 또는 JPEG 사진을 선택하세요.');return}let r=new FileReader();r.onload=()=>{$('photo').src=r.result;$('photoTitle').textContent=f.name};r.readAsDataURL(f)};refresh();</script></main></html>'''
 document=document.replace('新규','신규').replace('@@SOURCE@@',html.escape(info['source'])).replace('@@PROFILE@@',html.escape(info['profile_description'])).replace('@@PAGES@@',page_options).replace('@@PHOTO@@',photo_uri)
 (out/'RESULT.html').write_text(document,encoding='utf8')
def gs_command():
 dll=BASE/'runtime/ghostscript/bin/gsdll64.dll'
 return [sys.executable,str(BASE/'gs_bridge.py')] if dll.exists() else [find_gs()]

def same_cmyk_input_characterization(source,target):
 """Conservatively identify equivalent CMYK inputs for ink preservation.

 Ignore descriptive ICC headers and inverse separation tables, as the raster
 path does. Version, class, flags, media attributes, default intent and PCS
 illuminant must still match; forward color tables must match byte for byte.
 """
 from proof_rgb_image import same_cmyk_characterization
 a=source.tobytes();b=target.tobytes()
 return a[16:20]==b'CMYK' and all(a[x:y]==b[x:y] for x,y in ((8,24),(36,40),(44,48),(56,80))) and same_cmyk_characterization(source,target)

def object_icc_profiles(reader,proof_profile=None):
 """Describe embedded object profiles without changing rendering or defaults."""
 found={};seen=set();warnings=[]
 def visit(value):
  obj=value.get_object() if hasattr(value,'get_object') else value
  key=id(obj)
  if key in seen:return
  seen.add(key)
  if isinstance(obj,(list,tuple)):
   if len(obj)>=2 and obj[0]=='/ICCBased':
    try:
     import io
     data=obj[1].get_object().get_data();sha=hashlib.sha256(data).hexdigest()
     profile=ImageCms.ImageCmsProfile(io.BytesIO(data))
     found[sha]={'description':ImageCms.getProfileDescription(profile).strip(),'color_space':data[16:20].decode('ascii',errors='replace').strip(),'sha256':sha}
     if proof_profile is not None:
      found[sha]['same_proof_cmyk_characterization']=same_cmyk_input_characterization(profile,proof_profile)
    except Exception:
     warnings.append('객체 ICC 프로파일 설명을 읽지 못했습니다. 변환 로그를 확인하세요.')
    return
   for child in obj:visit(child)
  elif isinstance(obj,dict):
   for name,child in obj.items():
    if name not in ('/Parent','/P','/Contents','/Metadata','/OutputIntents','/DestOutputProfile'):visit(child)
 for page in reader.pages:visit(page.get('/Resources',{}))
 return list(found.values()),list(dict.fromkeys(warnings))

def render(pdf,out=None,profile=None,dpi=120):
 import numpy as np
 pdf=pathlib.Path(pdf).resolve();before=digest(pdf)
 out=pathlib.Path(out or BASE/'new_previews'/pdf.stem).resolve();out.mkdir(parents=True,exist_ok=True)
 profile=pathlib.Path(profile or BASE/'icc/CoatedFOGRA39.icc').resolve()
 if not isinstance(dpi,int) or not 36<=dpi<=300:raise ValueError('DPI must be 36–300')
 reader=PdfReader(pdf)
 if reader.is_encrypted and not reader.decrypt(''):raise ValueError('암호가 있는 PDF는 먼저 암호를 해제해 주세요.')
 pages=len(reader.pages)
 if not 1<=pages<=50:raise ValueError('PDF는 1~50페이지여야 합니다.')
 for page in reader.pages:
  if float(page.mediabox.width)*float(page.mediabox.height)*(dpi/72)**2>80000000:
   raise ValueError('PDF 페이지가 너무 큽니다. 페이지 크기 또는 해상도를 줄여 주세요.')
 p=ImageCms.getOpenProfile(str(profile));srgb=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
 # The source/separation leg uses BPC below. Preserve proof ink black on
 # this final display leg, matching LCMS's linked softproof contract.
 flags=0
 rel=ImageCms.buildTransformFromOpenProfiles(p,srgb,'CMYK','RGB',renderingIntent=1,flags=flags)
 absolute=ImageCms.buildTransformFromOpenProfiles(p,srgb,'CMYK','RGB',renderingIntent=3)
 srgb_path=out/'sRGB.icc';srgb_path.write_bytes(srgb.tobytes())
 defaults={'CMYK':profile,'RGB':srgb_path,'Gray':BASE/'runtime/ghostscript/iccprofiles/default_gray.icc'}
 embedded=None;embedded_description=None;object_profiles,warnings=object_icc_profiles(reader,p)
 for ref in reader.trailer['/Root'].get('/OutputIntents',[]):
  oi=ref.get_object();stream=oi.get('/DestOutputProfile')
  if stream:
   data=stream.get_object().get_data();space=data[16:20].decode('ascii',errors='replace').strip()
   if space not in ('CMYK','RGB','GRAY'):
    warnings.append('Unsupported OutputIntent color space: '+space);continue
   embedded=out/'source_output_intent.icc';embedded.write_bytes(data)
   embedded_description=ImageCms.getProfileDescription(ImageCms.getOpenProfile(str(embedded))).strip()
   defaults['Gray' if space=='GRAY' else space]=embedded
   break
 # Only the standard DeviceCMYK default may be canonicalized. Keep the direct
 # source/photo rendering and every explicit object ICC untouched. Rewriting
 # an entire OutputIntent or forcing OverrideICC would corrupt mixed-profile
 # documents. Equal forward characterization means the same inks already
 # belong to the proof device, even if descriptive ICC headers differ.
 proof_defaults=dict(defaults);cmyk_default_normalized=False
 if embedded is not None and defaults['CMYK']==embedded:
  source_profile=ImageCms.getOpenProfile(str(embedded))
  if digest(embedded)!=digest(profile) and same_cmyk_input_characterization(source_profile,p):
   proof_defaults['CMYK']=profile;cmyk_default_normalized=True
 for item in object_profiles:
  if item.get('same_proof_cmyk_characterization') and item['sha256']!=digest(profile):
   warnings.append('선택한 프루프와 색 특성이 같은 객체별 CMYK ICC의 파일 표현이 다릅니다. 객체 ICC는 그대로 해석하므로 표준 PDF 프루프가 동일 CMYK 래스터의 채널 보존 결과와 다를 수 있습니다. 인쇄소 RIP에서 확인하세요.')
 command=gs_command();records=[]
 common=['-dSAFER','-dBATCH','-dNOPAUSE',f'-r{dpi}','-dTextAlphaBits=4','-dGraphicsAlphaBits=4','-dOverrideICC=false','-dRenderIntent=1','-dBlackPtComp=1']
 for n in range(1,pages+1):
  page_args=[f'-dFirstPage={n}',f'-dLastPage={n}']
  def run(device,destination,output_profile,extra=(),input_defaults=None):
   default_args=[f'-sDefault{kind}Profile={path.resolve()}' for kind,path in (input_defaults or defaults).items()]
   args=[*command,*common,*default_args,*page_args,f'-sDEVICE={device}',*extra,f'-sOutputICCProfile={output_profile.resolve()}',f'-sOutputFile={destination.resolve()}',str(pdf)]
   result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   (out/(destination.stem+'_render.log')).write_bytes(result.stdout)
   if result.returncode or not destination.exists():raise RuntimeError(result.stdout.decode('utf8',errors='replace'))
  # Empirical input goes directly from document colors to sRGB. No CMYK proof step.
  source=out/f'page_{n:02d}_source.png'
  run('png16m',source,srgb_path)
  with Image.open(source) as im:im.save(source,icc_profile=srgb.tobytes())
  records.append(source.name)
  target=out/f'page_{n:02d}_CMYK.tif'
  run('tiff32nc',target,profile,['-sCompression=lzw','-dSimulateOverprint=true'],proof_defaults)
  with Image.open(target) as im:
   im.load()
   if im.mode!='CMYK':raise ValueError(f'Expected CMYK, got {im.mode}')
   for mode,t in [('relative',rel),('paper',absolute)]:
    dest=out/f'page_{n:02d}_{mode}.png';ImageCms.applyTransform(im,t).save(dest,icc_profile=srgb.tobytes());records.append(dest.name)
   a=np.asarray(im);total=a.astype(np.float64).sum(axis=2)*100/255
   stat={'max_TAC_percent':round(float(total.max()),2),'pixels_over_300_percent':round(float((total>300).mean()*100),3),'pixels_over_330_percent':round(float((total>330).mean()*100),3),'scope':'TAC after conversion to selected proof profile; not original PDF channel totals and not ICC gamut checking.'}
   (out/f'page_{n:02d}_ink.json').write_text(json.dumps(stat,indent=2),encoding='utf8')
   aa=np.array(ImageCms.applyTransform(im,rel));aa[total>300]=[255,0,255]
   Image.fromarray(aa).save(out/f'page_{n:02d}_TAC300.png',icc_profile=srgb.tobytes())
  target.unlink()
 if digest(pdf)!=before:raise RuntimeError('Input hash changed')
 object_names=' / '.join(item['description'] for item in object_profiles)
 default_names={kind:ImageCms.getProfileDescription(ImageCms.getOpenProfile(str(path))).strip() for kind,path in defaults.items()}
 rgb_label='sRGB' if defaults['RGB']==srgb_path else default_names['RGB']
 gray_label='번들 ICC' if defaults['Gray']==BASE/'runtime/ghostscript/iccprofiles/default_gray.icc' else default_names['Gray']
 description=('객체 ICC: '+object_names+' · ' if object_names else '')+'기본값: RGB '+rgb_label+' · CMYK '+default_names['CMYK']+' · Gray '+gray_label
 note=('객체 내장 ICC를 우선 해석. ' if object_names else '')+('내장 Output Intent 적용. ' if embedded else 'Output Intent 없음. ')
 note+='태그 없는 DeviceCMYK / DeviceRGB / DeviceGray 기본값: '+default_names['CMYK']+' / '+default_names['RGB']+' / '+default_names['Gray']+'. sRGB 직접 변환.'
 if cmyk_default_normalized:note+=' 표준 프루프에서는 색 특성이 같은 DeviceCMYK 기본 ICC를 선택한 프루프 ICC로 통일하여 CMYK 채널을 보존합니다. 사진 경로와 객체별 ICC는 변경하지 않았습니다.'
 info={'source':pdf.name,'source_sha256':before,'profile':profile.name,'profile_description':ImageCms.getProfileDescription(p).strip(),'profile_sha256':digest(profile),'source_profile_note':note,'source_profile_description':description,'source_profile_assumed':embedded is None and not object_profiles,'source_object_icc_profiles':object_profiles,'source_default_profiles':default_names,'source_icc_sha256':digest(embedded) if embedded else None,'dpi':dpi,'pages':pages,'engine':'Ghostscript 9.50 bundled DLL in isolated process' if len(command)>1 else command[0],'relative':'source -> FOGRA relative colorimetric + BPC; FOGRA -> sRGB relative colorimetric, BPC off to retain simulated ink black','paper':'source -> FOGRA relative + BPC; FOGRA -> sRGB absolute colorimetric, BPC off','source_rendering':'direct source -> sRGB, relative colorimetric + BPC','overprint':'Standard CMYK proof simulates overprint. Direct RGB source does not reproduce physical overprint; inspect complex spots/transparency in printer RIP.','files':records,'input_unchanged':True,'pipeline':'source_srgb_photo_v11','warnings':warnings}
 info['cmyk_preservation']={'device_cmyk_default_normalized':cmyk_default_normalized,'scope':'standard proof DeviceCMYK default only; source/photo rendering and explicit object ICC unchanged','standard_default_cmyk_sha256':digest(proof_defaults['CMYK']),'pdf_rewritten':False,'object_profiles_rewritten':False}
 info['render_revision']='11.2'
 (out/'preview_info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf8');build_result_view(out,info)
 return out
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('pdf',nargs='?');ap.add_argument('--out');ap.add_argument('--profile');ap.add_argument('--dpi',type=int,default=120);ap.add_argument('--open',action='store_true');a=ap.parse_args()
 interactive=not a.pdf
 if not a.pdf:
  from native_dialogs import choose_file
  a.pdf=choose_file('HARDYS - 프루핑할 PDF를 선택하세요')
  if not a.pdf:sys.exit(0)
 try:
  d=render(a.pdf,a.out,a.profile,a.dpi)
  if interactive or a.open:
   from native_dialogs import notify
   webbrowser.open((d/'RESULT.html').resolve().as_uri())
   notify('HARDYS',f'PDF 변환이 완료되어 결과 화면을 열었습니다.\n\n자동으로 열리지 않으면 다음 파일을 여세요:\n{d / "RESULT.html"}')
 except Exception as e:
  if interactive or a.open:
   from native_dialogs import notify
   notify('HARDYS',str(e),error=True)
  else:raise
