"""Detached worker with per-launch startup status and error capture."""
import argparse,faulthandler,pathlib,sys,traceback
APP=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(APP))
from startup_state import publish,status_path
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--startup-id')
args,_=parser.parse_known_args()
startup_id=args.startup_id
if startup_id:status_path(startup_id)
(APP/'state').mkdir(exist_ok=True)
log_path=APP/'state'/('startup_'+startup_id+'.log' if startup_id else 'server.log')
with log_path.open('a',encoding='utf8',buffering=1) as log:
    sys.stdout=log;sys.stderr=log;faulthandler.enable(log,all_threads=True)
    try:
        publish(startup_id,'loading',message='실행 모듈을 불러오고 있습니다.')
        from bootstrap import prepare
        prepare(progress=lambda message:publish(startup_id,'loading',message=message))
        publish(startup_id,'starting',message='이미지 처리 프로그램의 연결을 준비하고 있습니다.')
        from server import main
        main()
    except Exception as exc:
        message=traceback.format_exc()
        log.write(message)
        publish(startup_id,'error',error=str(exc),traceback=message,message='실행 준비 중 오류가 발생했습니다.')
        (APP/'startup_error.log').write_text(message,encoding='utf8')
        sys.exit(1)
