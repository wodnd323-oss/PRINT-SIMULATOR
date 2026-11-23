"""HARDYS local print/photo comparison app. Binds to loopback only."""
import math,copy
import argparse,concurrent.futures,datetime,hashlib,http.server,json,mimetypes,os,pathlib,secrets,socket,sys,threading,time,traceback,urllib.parse,webbrowser
from PIL import Image,ImageCms
from pypdf import PdfReader
from color_model import PhotoModel,read_srgb,save_srgb,SRGB
BASE=pathlib.Path(__file__).resolve().parent
from startup_state import BUILD,REVISION,ROOT_ID,publish,publish_active
STARTUP_ID=None
for name in ['state','state/history','uploads','renders','exports','assets/user_photos']:(BASE/name).mkdir(parents=True,exist_ok=True)
MODEL_PATH=BASE/'state/calibration.json'
PIPELINE='source_srgb_photo_v11'
MIGRATION_NOTICE=None
TOKEN=secrets.token_urlsafe(24)
JOBS={};LOCK=threading.RLock();POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
MAX_UPLOAD=220*1024*1024

def load_json(path):return json.loads(path.read_text('utf8'))
def write_json(path,obj):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)
def validate_model(doc):
    if not isinstance(doc,dict) or doc.get('pipeline')!=PIPELINE or doc.get('schema_version')!=11:
        raise ValueError('이전 보정은 입력 처리 방식이 다릅니다. v11 기준을 사용하거나 새 원본에서 다시 표본을 선택해 주세요.')
    anchors=doc.get('anchors')
    if not isinstance(anchors,list) or len(anchors)>128:raise ValueError('기준점은 최대 128개입니다.')
    for a in anchors:
        if not isinstance(a,dict):raise ValueError('기준점 형식을 확인해 주세요.')
        for key in ('source_rgb','target_rgb'):
            color=a.get(key)
            if not isinstance(color,list) or len(color)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=255 for v in color):raise ValueError('기준점 RGB는 유한한 0~255 숫자 3개여야 합니다.')
    for key,default,lo,hi in [('radius',26,1,100),('max_delta',32,0,100)]:
        value=doc.get(key,default)
        if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError('보정 파라미터 범위를 확인해 주세요: '+key)
    return doc

def initialize_model():
    global MIGRATION_NOTICE
    default=validate_model(load_json(BASE/'default_calibration.json'))
    if MODEL_PATH.exists():
        try:validate_model(load_json(MODEL_PATH));return
        except (ValueError,TypeError,KeyError):
            stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            backup=BASE/'state/history'/('pre_v11_'+stamp+'.json')
            backup.write_bytes(MODEL_PATH.read_bytes())
            MIGRATION_NOTICE={'backup':backup.relative_to(BASE).as_posix(),'message':'이전 또는 손상된 보정을 '+backup.relative_to(BASE).as_posix()+' 에 보존하고 v11 기본 보정으로 시작했습니다.'}
            write_json(BASE/'state/migration_notice.json',MIGRATION_NOTICE)
    write_json(MODEL_PATH,default)

def model_doc():
    with LOCK:return validate_model(load_json(MODEL_PATH))

def render_records():
    records=[]
    for p in (BASE/'renders').glob('*/record.json'):
        try:
            record=load_json(p)
            if isinstance(record,dict) and record.get('pipeline')==PIPELINE and record.get('render_revision')==REVISION and isinstance(record.get('pages'),list) and record['pages'] and all(isinstance(page,dict) and 'source' in page for page in record['pages']):records.append(record)
        except (OSError,ValueError,TypeError,KeyError):continue
    return records

initialize_model()
def safe_asset(name):
    p=(BASE/name).resolve()
    if not p.is_relative_to(BASE) or p.parts[len(BASE.parts)] not in ['assets','renders','exports'] or not p.is_file():raise ValueError('이미지 경로가 올바르지 않습니다.')
    return p
def source_spaces(reader):
    counts={'DeviceRGB':0,'DeviceCMYK':0,'Separation':0,'ICCBased':0};seen=set()
    def walk(value,depth=0):
        if depth>10:return
        try:
            if hasattr(value,'get_object'):value=value.get_object()
            ident=id(value)
            if isinstance(value,(dict,list)):
                if ident in seen:return
                seen.add(ident)
            if isinstance(value,dict):
                for k,v in value.items():
                    if str(k) not in ['/Parent','/Metadata','/Length']:walk(v,depth+1)
            elif isinstance(value,list):
                for v in value:walk(v,depth+1)
            else:
                name=str(value).lstrip('/')
                if name in counts:counts[name]+=1
        except Exception:pass
    for page in reader.pages:walk(page.get('/Resources',{}))
    return counts

def job_run(job_id,callback):
    with LOCK:JOBS[job_id]={'status':'running'}
    try:
        result=callback()
        with LOCK:JOBS[job_id]={'status':'done','result':result}
    except Exception as error:
        (BASE/'state/last_error.txt').write_text(traceback.format_exc(),encoding='utf8')
        with LOCK:JOBS[job_id]={'status':'error','error':str(error)}
def job(callback):
    identifier=secrets.token_hex(8)
    with LOCK:JOBS[identifier]={'status':'queued'}
    POOL.submit(job_run,identifier,callback)
    return {'job':identifier}

def import_pdf(data,name):
    if not data.startswith(b'%PDF-'):raise ValueError('PDF 파일을 선택해 주세요.')
    digest=hashlib.sha256(data).hexdigest();directory=BASE/'renders'/digest[:20];directory.mkdir(exist_ok=True)
    pdf=BASE/'uploads'/(digest+'.pdf')
    if not pdf.exists():pdf.write_bytes(data)
    reader=PdfReader(pdf)
    if reader.is_encrypted and not reader.decrypt(''):raise ValueError('암호가 있는 PDF는 먼저 암호를 해제해 주세요.')
    if len(reader.pages)>50:raise ValueError('한 번에 50페이지 이하의 PDF를 선택해 주세요.')
    if not(directory/'preview_info.json').exists() or load_json(directory/'preview_info.json').get('pipeline')!=PIPELINE or load_json(directory/'preview_info.json').get('render_revision')!=REVISION:
        from proof_pdf import render
        render(pdf,directory,dpi=120)
    info=load_json(directory/'preview_info.json')
    prefix=directory.relative_to(BASE).as_posix()
    pages=[{mode:f'{prefix}/page_{n:02d}_{mode}.png' for mode in ['relative','paper','TAC300','source']} for n in range(1,info['pages']+1)]
    record={'id':'pdf_'+digest[:16],'name':name,'source':name,'source_sha256':digest,'kind':'pdf','page_count':info['pages'],'pages':pages,'profile':info['profile'],'embedded_profile':not info['source_profile_assumed'],'source_profile_description':info['source_profile_description'],'pipeline':PIPELINE,'render_revision':REVISION,'source_profile_note':info['source_profile_note'],'warnings':info.get('warnings',[]),'color_spaces':source_spaces(reader),'input_unchanged':info['input_unchanged']}
    write_json(directory/'record.json',record)
    return record

def import_rgb(data,name):
    digest=hashlib.sha256(data).hexdigest();p=BASE/'uploads'/(digest+pathlib.Path(name).suffix.lower());p.write_bytes(data)
    out=BASE/'renders'/('rgb_'+digest[:16])
    from proof_rgb_image import proof_image
    proof_image(p,out)
    prefix=out.relative_to(BASE).as_posix();info=load_json(out/'gamut_info.json')
    record={'id':'rgb_'+digest[:16],'name':name,'source':name,'kind':'rgb','pipeline':PIPELINE,'render_revision':REVISION,'source_sha256':digest,'page_count':1,'pages':[{'relative':f'{prefix}/RGB_softproof.png','paper':f'{prefix}/RGB_softproof.png','TAC300':f'{prefix}/RGB_gamut_warning.png','rgb':f'{prefix}/RGB_reference.png','source':f'{prefix}/RGB_reference.png'}],'profile':'CoatedFOGRA39.icc','gamut_info':info}
    write_json(out/'record.json',record);return record

def preview(payload):
    asset=str(payload['asset'])
    # Never apply the new empirical model to legacy proofs or already predicted exports.
    records=load_json(BASE/'catalog.json')['cases']+render_records()
    allowed={page['source'] for item in records for page in item['pages'] if 'source' in page}
    if asset not in allowed:raise ValueError('원본 프로파일 입력이 없는 이전 미리보기입니다. 원본 PDF/이미지를 다시 열어 주세요.')
    p=safe_asset(asset);strength=float(payload.get('strength',1))
    if not math.isfinite(strength) or not 0<=strength<=1:raise ValueError('반영 강도는 0~1 사이의 유한한 숫자여야 합니다.')
    doc=model_doc();key=hashlib.sha256((PIPELINE+'|'+REVISION+'|'+json.dumps(doc,sort_keys=True)+asset+str(p.stat().st_mtime_ns)+str(strength)).encode()).hexdigest()[:20]
    out=BASE/'exports'/key;out.mkdir(exist_ok=True);im,_=read_srgb(p);model=PhotoModel(doc)
    matched=out/'matched.png';overlay=out/'reference_range.png'
    if not matched.exists():save_srgb(model.apply(im,strength),matched)
    if not overlay.exists():save_srgb(model.support_overlay(im),overlay)
    from reference_support import reference_support
    support_image=im.copy();support_image.thumbnail((650,650));support=reference_support(model,support_image)
    report={'near_reference_percent':support['near_percent'],'transition_percent':support['transition_percent'],'unsupported_percent':support['extrapolated_percent'],'reference_support':support,'meaning':support['meaning']}
    report.update({'model_name':doc.get('name'),'strength':strength,'input_asset':asset,'anchors':len(model.anchors),'photo_match_only':True,'global_extrapolation':True,'fit':model.fit_information()})
    write_json(out/'comparison_info.json',report)
    return {'matched':matched.relative_to(BASE).as_posix(),'range':overlay.relative_to(BASE).as_posix(),'statistics':report,'export_name':f'HARDYS_global_estimate_{round(strength*100)}.png'}

def color_sample(payload):
    import math,numpy as np
    from prediction import Predictor,gamut_flags
    from reference_support import reference_support
    mode=payload.get('model_mode','photo');strength=float(payload.get('strength',1))
    if not math.isfinite(strength) or not 0<=strength<=1:raise ValueError('Invalid strength')
    if mode=='icc':strength=0.
    kind='cmyk' if 'cmyk' in payload else 'rgb';point=payload[kind];cap=100 if kind=='cmyk' else 255
    if not isinstance(point,list) or len(point)!=(4 if kind=='cmyk' else 3) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=cap for v in point):raise ValueError('색상 값 범위를 확인해 주세요.')
    document=model_doc();calibration_sha256=hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest()
    expected=payload.get('calibration_sha256')
    if expected is not None and expected!=calibration_sha256:raise ValueError('보정 기준이 변경됐습니다. 목표색을 다시 역산한 뒤 확인해 주세요.')
    predictor=Predictor(document,strength,mode)
    points=np.rint(np.array([point])*255/100) if kind=='cmyk' else np.rint([point])
    matched,basic,ink=predictor.forward(points,kind.upper())
    rgb=basic[0].tolist() if kind=='cmyk' else points[0].astype(int).tolist()
    near=float(predictor.model.nearest(basic)[0])
    return {'input_rgb':rgb,'baseline_rgb':basic[0].tolist(),'matched_rgb':matched[0].tolist(),'cmyk':np.round(ink[0]*100/255,2).tolist(),'near_reference':near<=12,'distance_from_reference':round(near,2),'outside_cmyk_gamut':bool(gamut_flags([rgb])[0]) if kind=='rgb' else None,'strength':strength,'model_mode':mode,'input_cmyk_profile':predictor.input_profile,'global_extrapolation':mode=='photo','reference_support':reference_support(predictor.model,basic) if mode=='photo' else None,'calibration_sha256':calibration_sha256}

class Handler(http.server.BaseHTTPRequestHandler):
    server_version='HARDYSLocal/2.0'
    def log_message(self,format,*args):pass
    def send_bytes(self,data,mime='application/json; charset=utf-8',code=200,extra=None):
        self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def send_json(self,obj,code=200):self.send_bytes(json.dumps(obj,ensure_ascii=False).encode(),code=code)
    def discard_upload(self):
        # Consume a bounded stale-session body before replying, avoiding TCP reset
        # while a browser is still transmitting a file.
        try:
            remaining=int(self.headers.get('Content-Length','0'))
            if not 0<remaining<=MAX_UPLOAD:return
            previous=self.connection.gettimeout();self.connection.settimeout(2)
            try:
                while remaining:
                    block=self.rfile.read(min(65536,remaining))
                    if not block:break
                    remaining-=len(block)
            finally:self.connection.settimeout(previous)
        except Exception:pass
    def valid_host(self):
        host=self.headers.get('Host','')
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        return host.lower() in allowed
    def do_GET(self):
        if not self.valid_host():return self.send_json({'error':'로컬 주소로 접속해 주세요.'},403)
        try:
            url=urllib.parse.urlsplit(self.path);route=url.path
            if route=='/health':return self.send_json({'app':'HARDYS_PrintSimulator_Global','version':BUILD,'revision':REVISION,'root_id':ROOT_ID,'pid':os.getpid(),'startup_id':STARTUP_ID})
            if route=='/api/session':return self.send_json({'token':TOKEN,'root_id':ROOT_ID,'version':BUILD})
            if route=='/api/state':
                catalog=load_json(BASE/'catalog.json');catalog['cases'] += render_records()
                return self.send_json({'catalog':catalog,'calibration':model_doc(),'migration_notice':MIGRATION_NOTICE})
            if route=='/api/job':
                key=urllib.parse.parse_qs(url.query).get('id',[''])[0]
                with LOCK:result=JOBS.get(key,{'status':'error','error':'작업을 찾을 수 없습니다.'})
                return self.send_json(result)
            if route=='/api/model':return self.send_json(model_doc())
            if route in ['/','/index.html']:
                data=(BASE/'web/index.html').read_text('utf8').replace('__TOKEN__',TOKEN).replace('__ROOT_ID__',ROOT_ID)
                return self.send_bytes(data.encode(),'text/html; charset=utf-8')
            relative=urllib.parse.unquote(route).lstrip('/');p=(BASE/relative).resolve()
            if not p.is_relative_to(BASE) or not relative.startswith(('web/','assets/','renders/','exports/')) or not p.is_file():return self.send_json({'error':'파일을 찾을 수 없습니다.'},404)
            return self.send_bytes(p.read_bytes(),mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:self.send_json({'error':str(e)},400)
    def do_POST(self):
        if not self.valid_host():return self.send_json({'error':'로컬 주소로 접속해 주세요.'},403)
        try:
            if self.headers.get('X-Hardys-Token')!=TOKEN:
                self.discard_upload()
                return self.send_json({'error':'연결 정보가 갱신되었습니다. 다시 연결해 주세요.','code':'SESSION_EXPIRED'},403)
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':return self.send_json({'error':'요청 출처가 올바르지 않습니다.'},403)
            length=int(self.headers.get('Content-Length','0'))
            if length<0:return self.send_json({'error':'잘못된 요청 크기입니다.'},400)
            if length>MAX_UPLOAD:return self.send_json({'error':'220MB 이하 파일을 선택해 주세요.'},413)
            data=self.rfile.read(length);url=urllib.parse.urlsplit(self.path);route=url.path;query=urllib.parse.parse_qs(url.query)
            name=pathlib.Path(query.get('name',['선택한 파일'])[0]).name
            if route=='/api/pdf':return self.send_json(job(lambda:import_pdf(data,name)))
            if route=='/api/rgb':return self.send_json(job(lambda:import_rgb(data,name)))
            if route=='/api/photo':
                from proof_rgb_image import read_image_srgb
                digest=hashlib.sha256(data).hexdigest();p=BASE/'uploads'/(digest+'.photo');p.write_bytes(data);im,info=read_image_srgb(p)
                im.thumbnail((3000,3000));dest=BASE/'assets/user_photos'/(digest[:20]+'.png');save_srgb(im,dest)
                return self.send_json({'photo':dest.relative_to(BASE).as_posix(),'info':info,'name':name})
            payload=json.loads(data or b'{}')
            if route=='/api/shutdown':
                self.send_json({'stopping':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if route=='/api/color':return self.send_json(color_sample(payload))
            if route=='/api/inverse':
                from inverse_color import inverse_color
                document=model_doc()
                return self.send_json(job(lambda:inverse_color(payload,document)))
            if route=='/api/inverse-gradient':
                from inverse_gradient import inverse_gradient
                filename=safe_asset(str(payload['asset']));document=model_doc()
                return self.send_json(job(lambda:inverse_gradient(filename,payload,document)))
            if route=='/api/preview':return self.send_json(job(lambda:preview(payload)))
            if route=='/api/pick':
                im,_=read_srgb(safe_asset(payload['asset']));x=int(payload['x']);y=int(payload['y'])
                if not(0<=x<im.width and 0<=y<im.height):raise ValueError('이미지 안쪽을 선택해 주세요.')
                import numpy as np
                pixels=np.asarray(im.crop((max(0,x-3),max(0,y-3),min(im.width,x+4),min(im.height,y+4)))).reshape(-1,3)
                return self.send_json({'rgb':np.rint(np.median(pixels,axis=0)).astype(int).tolist(),'xy':[x,y]})
            if route in ['/api/calibration','/api/reset']:
                doc=load_json(BASE/'default_calibration.json') if route.endswith('reset') else payload
                doc=copy.deepcopy(validate_model(doc));PhotoModel(doc)
                with LOCK:
                    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f');write_json(BASE/'state/history'/(stamp+'.json'),model_doc());write_json(MODEL_PATH,doc)
                return self.send_json({'saved':True,'calibration':doc})
            self.send_json({'error':'알 수 없는 요청입니다.'},404)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as e:self.send_json({'error':str(e)},400)

def main():
    global STARTUP_ID
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8766);ap.add_argument('--no-open',action='store_true');ap.add_argument('--startup-id');args=ap.parse_args()
    STARTUP_ID=args.startup_id
    try:server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        from http.client import HTTPConnection
        url=f'http://127.0.0.1:{args.port}'
        try:
            connection=HTTPConnection('127.0.0.1',args.port,timeout=2)
            try:
                connection.request('GET','/health');response=connection.getresponse();health=json.loads(response.read())
            finally:connection.close()
            if health.get('app')=='HARDYS_PrintSimulator_Global' and health.get('root_id')==ROOT_ID and health.get('version',0)>=BUILD and health.get('revision')==REVISION:
                if not args.no_open:webbrowser.open(url)
                print('ALREADY_RUNNING '+url,flush=True);return
        except Exception:pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True;url=f'http://127.0.0.1:{server.server_address[1]}'
    (BASE/'state/current_url.txt').write_text(url,encoding='utf8');print('LOCAL_URL '+url,flush=True)
    ready=publish(STARTUP_ID,'ready',url=url,message='비교 준비가 완료되었습니다.')
    publish_active(ready)
    if not args.no_open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=True)

if __name__=='__main__':main()
