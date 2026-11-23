"""Read-only V11.2 follow-up for native Windows or an explicitly chosen GS.

Example:
  <bundled python> portable_gray_icc_provenance.py --app <released app> \
      --fixtures <three input files directory> --out <external evidence dir>

This is an audit, not a product pass gate. A reproduced defect is an observation,
not a script failure. Read the JSON's per-check completion/error status. App and
input files are never edited. Bytecode is disabled before importing app modules.
"""
import os,sys,argparse,hashlib,json,traceback,platform,datetime,io
from pathlib import Path
os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--fixtures',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--gs',type=Path,help='Explicit native GS for a non-Windows run; omit for normal bundled Windows selection.')
    args=parser.parse_args();app=args.app.resolve();fixtures=args.fixtures.resolve();out=args.out.resolve()
    if out==app or app in out.parents:raise ValueError('Evidence output must be outside the app directory.')
    out.mkdir(parents=True,exist_ok=True)
    from PIL import Image,ImageCms
    import numpy as np
    sys.path.insert(0,str(app))
    import proof_rgb_image as raster
    import proof_pdf as pdf
    if args.gs:pdf.gs_command=lambda:[str(args.gs.resolve())]
    inputs=['gray16_icc_linear.png','unprofiled_cmyk_no_resource.pdf','unprofiled_cmyk_unused_gracol_resource.pdf']
    before={name:sha(fixtures/name) for name in inputs}
    source_before={name:sha(app/name) for name in ['proof_rgb_image.py','proof_pdf.py']}
    result={'audit_execution_completed':False,'product_all_pass':None,'meaning':'Reproduced issues are observations; this audit does not authorize a release.','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'environment':{'platform':platform.platform(),'python':sys.version,'executable':sys.executable,'pillow':Image.__version__,'littlecms':ImageCms.core.littlecms_version},'input_sha256':before,'source_sha256':source_before,'checks':{}}
    def lab(rgb):
        a=np.asarray(rgb,dtype=float)/255;a=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
        xyz=a@np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]]).T
        t=xyz/np.array([.95047,1,1.08883]);f=np.where(t>(6/29)**3,np.cbrt(t),t/(3*(6/29)**2)+4/29)
        return np.stack([116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])],axis=-1)
    try:
        path=fixtures/inputs[0]
        actual,info=raster.read_image_srgb(path)
        with Image.open(path) as original:
            profile=ImageCms.ImageCmsProfile(io.BytesIO(original.info['icc_profile']))
            raw=np.asarray(original,dtype=np.uint16).copy()
        native=Image.fromarray(raw)
        expected=ImageCms.profileToProfile(native,profile,ImageCms.createProfile('sRGB'),outputMode='RGB',renderingIntent=1,flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
        a=np.asarray(actual)[0].astype(int);b=np.asarray(expected)[0].astype(int)
        result['checks']['gray16']={'completed':True,'input_mode':native.mode,'input_values':raw[0].tolist(),'application_rgb':a.tolist(),'same_lcms_same_icc_native16_rgb':b.tolist(),'max_rgb_difference':int(np.abs(a-b).max()),'max_delta_e76':float(np.linalg.norm(lab(a)-lab(b),axis=1).max()),'early_quantization_difference_observed':bool(np.any(a!=b)),'application_metadata':info,'oracle':'Same Pillow/LCMS, ICC, rendering intent 1 and BPC; original I;16 input, with no application 8-bit normalization.'}
    except Exception as error:result['checks']['gray16']={'completed':False,'exception_type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()}
    try:
        cmyk=np.array([[0,255,0,0],[0,0,0,255],[100,20,0,40],[0,0,0,0],[255,255,255,255]],dtype=np.uint8)
        im=Image.frombytes('CMYK',(len(cmyk),1),cmyk.tobytes());srgb=ImageCms.createProfile('sRGB')
        expected=np.asarray(ImageCms.profileToProfile(im,str(app/'icc/CoatedFOGRA39.icc'),srgb,outputMode='RGB',renderingIntent=1,flags=ImageCms.Flags.BLACKPOINTCOMPENSATION))[0].tolist()
        rows={}
        for filename in inputs[1:]:
            directory=out/Path(filename).stem;pdf.render(fixtures/filename,directory,dpi=72)
            metadata=json.loads((directory/'preview_info.json').read_text(encoding='utf8'))
            pixels=np.asarray(Image.open(directory/'page_01_source.png'))[16,16::32].tolist()
            rows[filename]={'photo_rgb':pixels,'source_profile_assumed':metadata['source_profile_assumed'],'server_embedded_profile_expression':not metadata['source_profile_assumed'],'source_profile_description':metadata['source_profile_description'],'source_profile_note':metadata['source_profile_note'],'source_object_icc_profiles':metadata['source_object_icc_profiles'],'engine':metadata['engine'],'warnings':metadata['warnings']}
        a,b=[rows[x] for x in inputs[1:]]
        result['checks']['unused_icc_provenance']={'completed':True,'cases':rows,'expected_assumed_fogra_photo':expected,'both_pixels_match_fogra_assumption':all(row['photo_rgb']==expected for row in rows.values()),'assumption_flag_changes_with_only_unused_resource':a['source_profile_assumed']!=b['source_profile_assumed'],'note':'The UI also displays source_profile_description and source_profile_note; server_embedded_profile_expression is the server.py field expression, not a new HTTP call.'}
    except Exception as error:result['checks']['unused_icc_provenance']={'completed':False,'exception_type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()}
    result['inputs_unchanged']={name:sha(fixtures/name)==before[name] for name in inputs}
    result['sources_unchanged']={name:sha(app/name)==source_before[name] for name in source_before}
    result['audit_execution_completed']=True
    result['all_checks_completed']=all(check['completed'] for check in result['checks'].values())
    (out/'portable_gray_icc_provenance_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
