"""Start the private local worker and wait for that exact worker to be ready."""
import argparse,http.client,json,os,pathlib,subprocess,sys,time,traceback,urllib.parse,uuid,webbrowser
APP=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(APP))
from startup_state import BUILD,REVISION,ROOT_ID,STATE,atomic_json,publish_active,read_status

def local_url(value):
    try:
        parsed=urllib.parse.urlsplit(str(value).strip().lstrip('\ufeff'))
        if (parsed.scheme=='http' and parsed.hostname=='127.0.0.1'
            and parsed.port and 0<parsed.port<65536 and parsed.path in ('','/')
            and not(parsed.username or parsed.password or parsed.query or parsed.fragment)):
            return 'http://127.0.0.1:'+str(parsed.port)
    except ValueError:pass
    return None

def urls():
    candidates=[]
    try:candidates.append(json.loads((STATE/'active_instance.json').read_text('utf8')).get('url'))
    except (OSError,ValueError):pass
    try:candidates.append((STATE/'current_url.txt').read_text('utf8'))
    except OSError:pass
    candidates.append('http://127.0.0.1:8766')
    for value in dict.fromkeys(candidates):
        url=local_url(value)
        if url:yield url

def probe(url,startup_id=None):
    url=local_url(url)
    if not url:return None
    parsed=urllib.parse.urlsplit(url);connection=http.client.HTTPConnection('127.0.0.1',parsed.port,timeout=.8)
    try:
        connection.request('GET','/health',headers={'Connection':'close'})
        response=connection.getresponse();info=json.loads(response.read(16384))
        if (response.status==200 and info.get('app')=='HARDYS_PrintSimulator_Global'
            and info.get('root_id')==ROOT_ID and isinstance(info.get('version'),int)
            and info['version']>=BUILD and info.get('revision')==REVISION and (startup_id is None or info.get('startup_id')==startup_id)):
            return info
    except (OSError,ValueError,http.client.HTTPException):pass
    finally:connection.close()
    return None

def active():
    for url in urls():
        if probe(url):return url
    return None

def tail(path):
    try:return pathlib.Path(path).read_text('utf8',errors='replace')[-12000:]
    except OSError:return ''

def wait_ready(process,startup_id,log_path,timeout=90):
    deadline=time.monotonic()+timeout;last_notice=0;status={}
    while time.monotonic()<deadline:
        status=read_status(startup_id)
        if status.get('phase')=='error':
            raise RuntimeError('처리 프로그램 시작 실패:\n'+status.get('error','')+'\n'+status.get('traceback',''))
        if status.get('phase')=='ready':
            url=local_url(status.get('url'))
            if url and probe(url,startup_id):
                publish_active(status)
                (STATE/'current_url.txt').write_text(url,encoding='utf8')
                return url
        if process.poll() is not None:
            raise RuntimeError('처리 프로그램이 종료되었습니다.\n'+tail(log_path))
        now=time.monotonic()
        if now-last_notice>=5:
            print(status.get('message') or '처리 프로그램을 시작하고 있습니다. 잠시 기다려 주세요.',flush=True)
            last_notice=now
        time.sleep(.15)
    phase=status.get('message') or status.get('phase') or '시작 응답 없음'
    raise RuntimeError('시작이 완료되지 않았습니다. 마지막 단계: '+phase+'\n'
                       +'자세한 기록: '+str(log_path)+'\n'+tail(log_path))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-open',action='store_true');args=parser.parse_args()
    STATE.mkdir(exist_ok=True)
    url=active()
    if not url:
        executable=APP/'runtime/python/pythonw.exe'
        if not executable.is_file():raise RuntimeError('실행환경이 없습니다. 전체 설치 ZIP을 하위 폴더까지 모두 풀어 주세요.')
        startup_id=uuid.uuid4().hex;log_path=STATE/('startup_'+startup_id+'.log')
        atomic_json(STATE/'last_launch.json',{'startup_id':startup_id,'log':str(log_path),'version':BUILD})
        print('HARDYS 실행 준비 중입니다. 처음 실행에는 시간이 걸릴 수 있습니다.',flush=True)
        with log_path.open('ab',buffering=0) as log:
            process=subprocess.Popen([str(executable),'-I','-X','utf8',str(APP/'background_server.py'),
                                      '--no-open','--port','0','--startup-id',startup_id],
                                     cwd=APP,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                     creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP)
        url=wait_ready(process,startup_id,log_path)
    print('HARDYS_READY '+url,flush=True)
    if not args.no_open:webbrowser.open(url)

if __name__=='__main__':
    try:main()
    except Exception:
        message=traceback.format_exc()
        try:(APP/'startup_error.log').write_text(message,encoding='utf8')
        except OSError:pass
        print(message,flush=True);sys.exit(1)
