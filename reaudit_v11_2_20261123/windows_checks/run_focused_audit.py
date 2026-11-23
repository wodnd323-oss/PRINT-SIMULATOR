"""Run the new V11.2 review cases with its bundled Windows Python.

Exit 0 means the review ran successfully. It never means the application has
no findings. Product source, profiles and calibration must remain unchanged.
"""
import sys
sys.dont_write_bytecode = True
import hashlib, json, os, pathlib, platform, shutil, subprocess, time

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
APP=ROOT/'released_app'
OUT=HERE/'results'
OUT.mkdir(parents=True,exist_ok=True)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def product_snapshot():
    return {p.relative_to(APP).as_posix():sha(p) for p in APP.rglob('*') if p.is_file()}

def write_report(report):
    (OUT/'focused_windows_audit_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

report={'scope':'Focused review of published V11.2 using bundled Python and Node; no browser or user PC access. Findings are evidence, not a failed execution gate.',
        'release_sha256':'b0f3fecb39a029c7b3da129a2f3bdec4b9b0cf26a2d98a3556b0e15a802b307b',
        'environment':{'python':sys.version,'executable':sys.executable,'platform':platform.platform()},
        'steps':[],'review_execution_completed':False,'product_certified':False}
started=time.monotonic()
before={}
try:
    if os.name!='nt':raise RuntimeError('Use the bundled Windows interpreter for this runner.')
    expected=(APP/'runtime/python/python.exe').resolve()
    if pathlib.Path(sys.executable).resolve()!=expected:raise RuntimeError('Runner is not using the verified distribution bundled Python.')
    node=shutil.which('node')
    if not node:raise RuntimeError('Node is required for controlled actual-JS execution; no browser is required.')
    import numpy
    from PIL import Image,ImageCms
    report['environment'].update(numpy=numpy.__version__,pillow=Image.__version__,lcms=ImageCms.core.littlecms_version,node=subprocess.check_output([node,'--version'],text=True).strip())
    before=product_snapshot()
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    preparation=subprocess.run([sys.executable,str(HERE/'prepare_fixtures.py')],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    (OUT/'prepare_fixtures.stdout.txt').write_text(preparation.stdout,encoding='utf-8')
    (OUT/'prepare_fixtures.stderr.txt').write_text(preparation.stderr,encoding='utf-8')
    report['fixture_preparation_returncode']=preparation.returncode
    if preparation.returncode!=0:raise RuntimeError('Pinned review fixtures could not be reconstructed and verified.')
    commands=[
        ('ui_state',[node,str(ROOT/'ui_contracts/audit_ui_state.cjs')]),
        ('inverse_geometry',[sys.executable,str(ROOT/'inverse_geometry/run_inverse_geometry_audit.py')]),
        ('tac_boundary',[sys.executable,str(ROOT/'inverse_geometry/run_tac_boundary_repro.py')]),
        ('gray_icc_provenance',[sys.executable,str(ROOT/'proof_inputs/portable_gray_icc_provenance.py'),'--app',str(APP),'--fixtures',str(ROOT/'proof_inputs/inputs'),'--out',str(OUT/'gray_icc_provenance')]),
    ]
    result_files={
        'ui_state':(ROOT/'ui_contracts/ui_state_results.json','completed'),
        'inverse_geometry':(ROOT/'inverse_geometry/inverse_geometry_results.json',None),
        'tac_boundary':(ROOT/'inverse_geometry/tac_boundary_results.json','audit_completed'),
        'gray_icc_provenance':(OUT/'gray_icc_provenance/portable_gray_icc_provenance_results.json','all_checks_completed'),
    }
    for name,command in commands:
        start=time.monotonic()
        try:
            completed=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
            (OUT/(name+'.stdout.txt')).write_text(completed.stdout,encoding='utf-8')
            (OUT/(name+'.stderr.txt')).write_text(completed.stderr,encoding='utf-8')
            step={'name':name,'returncode':completed.returncode,'execution_completed':completed.returncode==0,'elapsed_seconds':round(time.monotonic()-start,3),'command':command}
            result_path,completion_key=result_files[name]
            if result_path.exists():
                result=json.loads(result_path.read_text(encoding='utf-8'))
                case_completed=result.get(completion_key) is True if completion_key else 'elapsed_seconds' in result
                step['result_json']=str(result_path)
                step['case_execution_completed']=case_completed
                step['execution_completed'] &= case_completed
            else:
                step['execution_completed']=False
                step['missing_result_json']=str(result_path)
        except Exception as error:
            step={'name':name,'execution_completed':False,'error':repr(error),'command':command}
        report['steps'].append(step);write_report(report)
        print(json.dumps(step,ensure_ascii=False),flush=True)
    report['review_execution_completed']=all(step['execution_completed'] for step in report['steps'])
except Exception as error:
    report['runner_error']=repr(error)
finally:
    if before:
        after=product_snapshot()
        report['product_files_before']=len(before)
        report['product_changes']=[name for name in sorted(set(before)|set(after)) if before.get(name)!=after.get(name)]
        report['product_unchanged']=not report['product_changes']
        report['review_execution_completed'] &= report['product_unchanged']
    report['elapsed_seconds']=round(time.monotonic()-started,3)
    write_report(report)
    print(json.dumps({'review_execution_completed':report['review_execution_completed'],'product_certified':False,'report':str(OUT/'focused_windows_audit_results.json')},ensure_ascii=False),flush=True)
sys.exit(0 if report['review_execution_completed'] else 1)
