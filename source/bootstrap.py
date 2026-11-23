"""App-local bootstrap; deliberately independent of system Python and PATH."""
import json,os,pathlib,platform,sys,traceback
APP=pathlib.Path(__file__).resolve().parent
if str(APP) not in sys.path:sys.path.insert(0,str(APP))

def prepare(progress=None):
    os.chdir(APP)
    gs=APP/'runtime/ghostscript'
    os.environ['GS_LIB']=';'.join(str(p) for p in [gs/'lib',gs/'Resource/Init',gs/'Resource/Font'])
    os.environ['GS_FONTPATH']=str(gs/'Resource/Font')
    if progress:progress('이미지 라이브러리를 확인하고 있습니다.')
    from PIL import Image,ImageCms
    if progress:progress('색상 계산 라이브러리를 확인하고 있습니다.')
    import numpy as np
    if progress:progress('PDF 라이브러리를 확인하고 있습니다.')
    import pypdf
    if progress:progress('인쇄 ICC와 PDF 처리기를 확인하고 있습니다.')
    if not(gs/'bin/gswin64c.exe').is_file():raise RuntimeError('The bundled PDF engine is missing. Extract the complete ZIP again.')
    if not(APP/'icc/CoatedFOGRA39.icc').is_file():raise RuntimeError('The print profile is missing. Extract the complete ZIP again.')
    np.linalg.solve(np.eye(2),np.ones(2))
    for profile in ['CoatedFOGRA39.icc','GRACoL2013_CRPC6.icc']:ImageCms.getOpenProfile(str(APP/'icc'/profile))
    return {'status':'ok','python':sys.executable,'version':platform.python_version(),'Pillow':Image.__version__,'numpy':np.__version__,'pypdf':pypdf.__version__,'modules':{'PIL':Image.__file__,'numpy':np.__file__,'pypdf':pypdf.__file__},'ghostscript':str(gs/'bin/gswin64c.exe')}

if __name__=='__main__':
    try:
        report=prepare()
        if '--self-test' in sys.argv:print(json.dumps(report,ensure_ascii=True),flush=True)
        else:
            print('HARDYS Print Simulator - portable runtime ready.',flush=True)
            print('Keep this window open while using the simulator.',flush=True)
            from server import main
            main()
    except Exception:
        message=traceback.format_exc();(APP/'startup_error.log').write_text(message,encoding='utf8')
        print(message,flush=True)
        print('Startup failed. See startup_error.log in this folder.',flush=True)
        sys.exit(1)
