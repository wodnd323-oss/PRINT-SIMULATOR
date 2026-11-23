"""Small standard-library-only startup protocol shared by launcher and worker."""
import hashlib,json,os,pathlib,re,tempfile,time
APP=pathlib.Path(__file__).resolve().parent
STATE=APP/'state'
BUILD=11
REVISION="11.1"
ROOT_ID=hashlib.sha256(str(APP).casefold().encode()).hexdigest()[:20]

def atomic_json(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    handle,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
        for attempt in range(8):
            try:os.replace(name,path);break
            except PermissionError:
                if attempt==7:raise
                time.sleep(.025)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass

def status_path(startup_id):
    if not re.fullmatch('[0-9a-f]{32}',startup_id or ''):
        raise ValueError('Invalid startup identifier')
    return STATE/('startup_'+startup_id+'.json')

def publish(startup_id,phase,**details):
    record={'app':'HARDYS_PrintSimulator_Global','version':BUILD,'revision':REVISION,'root_id':ROOT_ID,
            'pid':os.getpid(),'startup_id':startup_id,'phase':phase,'updated':time.time(),**details}
    if startup_id:atomic_json(status_path(startup_id),record)
    return record

def read_status(startup_id):
    try:return json.loads(status_path(startup_id).read_text('utf8'))
    except (OSError,ValueError):return {}

def publish_active(record):
    atomic_json(STATE/'active_instance.json',record)

