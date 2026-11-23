"""ICC-aware PNG/JPEG import, print preview, and RGB gamut warning."""
import io,json,pathlib,sys,struct
import numpy as np
from PIL import Image,ImageCms,ImageOps,UnidentifiedImageError

BASE=pathlib.Path(__file__).resolve().parent

def srgb_profile():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))

BPC=ImageCms.Flags.BLACKPOINTCOMPENSATION

SRGB_CHRM=(.3127,.3290,.6400,.3300,.3000,.6000,.1500,.0600)
BRADFORD=np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])

def _png_header(filename):
    """Read only framing needed to detect unsupported native-precision input."""
    with open(filename,'rb') as stream:
        if stream.read(8)!=b'\x89PNG\r\n\x1a\n':return {}
        result={}
        while True:
            header=stream.read(8)
            if len(header)!=8:break
            length,kind=struct.unpack('>I4s',header)
            if kind==b'IDAT':break
            if kind==b'IHDR':
                data=stream.read(length)
                if len(data)==13:result.update(bit_depth=data[8],color_type=data[9])
            elif kind==b'cICP':
                result['cicp']=stream.read(length) if length<=16 else b'invalid'
                if length>16:stream.seek(length,1)
            else:stream.seek(length,1)
            stream.seek(4,1)
            if kind==b'IEND':break
        return result

def _rgb_matrix(chrm):
    values=np.asarray(chrm,dtype=float)
    if values.shape!=(8,) or not np.isfinite(values).all():raise ValueError('invalid cHRM')
    xy=values.reshape(4,2)
    if np.any(xy[:,0]<0) or np.any(xy[:,1]<=0) or np.any(xy.sum(axis=1)>1.00001):raise ValueError('invalid cHRM coordinates')
    xyz=np.column_stack((xy[:,0]/xy[:,1],np.ones(4),(1-xy.sum(axis=1))/xy[:,1]))
    primaries=xyz[1:].T
    if np.linalg.cond(primaries)>1e8:raise ValueError('degenerate cHRM')
    scales=np.linalg.solve(primaries,xyz[0])
    if np.any(scales<=0):raise ValueError('white outside primary triangle')
    return primaries*scales,xyz[0]

def _srgb_encode(linear):
    linear=np.clip(linear,0,1)
    return np.where(linear<=.0031308,12.92*linear,1.055*np.power(linear,1/2.4)-.055)

def _png_matrix_profile(gamma,matrix,white):
    """Build an ICC RGB matrix/TRC input profile, retaining wide-gamut data.

    The PCS colorants and chad tag use Bradford adaptation to ICC D50.
    Parametric curves retain normal gamma precisely; a tabulated curve covers
    extreme valid PNG gamma values that do not fit the ICC parameter range.
    """
    original=srgb_profile().tobytes();tags={}
    for index in range(int.from_bytes(original[128:132],'big')):
        entry=132+12*index;name=original[entry:entry+4]
        offset=int.from_bytes(original[entry+4:entry+8],'big');size=int.from_bytes(original[entry+8:entry+12],'big')
        if name!=b'chrm':tags[name]=original[offset:offset+size]
    d50=np.array([.9642,1.,.8249]);adaptation=np.linalg.solve(BRADFORD,np.diag((BRADFORD@d50)/(BRADFORD@white))@BRADFORD)
    pcs=adaptation@matrix
    fixed=lambda values:struct.pack('>'+str(len(values))+'i',*[round(float(v)*65536) for v in values])
    for channel,column in zip((b'rXYZ',b'gXYZ',b'bXYZ'),pcs.T):tags[channel]=b'XYZ '+bytes(4)+fixed(column)
    tags[b'chad']=b'sf32'+bytes(4)+fixed(adaptation.reshape(-1))
    if gamma is not None:
        exponent=1/gamma
        if 1/65536<=exponent<32768:payload=b'para'+bytes(4)+struct.pack('>HHI',0,0,round(exponent*65536))
        else:
            curve=np.rint((np.linspace(0,1,4096))**exponent*65535).astype('>u2')
            payload=b'curv'+bytes(4)+struct.pack('>I',len(curve))+curve.tobytes()
        for name in (b'rTRC',b'gTRC',b'bTRC'):tags[name]=payload
    description='PNG gamma/chromaticity input'.encode('utf-16-be')
    tags[b'desc']=b'mluc'+bytes(4)+struct.pack('>II',1,12)+b'enUS'+struct.pack('>II',len(description),28)+description
    offset=132+12*len(tags);entries=[];payloads=bytearray();shared={}
    for name,data in tags.items():
        if data not in shared:
            shared[data]=offset+len(payloads);payloads.extend(data);payloads.extend(bytes((-len(data))%4))
        entries.append(name+struct.pack('>II',shared[data],len(data)))
    header=bytearray(original[:128]);header[64:68]=struct.pack('>I',1);header[84:100]=bytes(16)
    result=header+struct.pack('>I',len(tags))+b''.join(entries)+payloads;result[:4]=struct.pack('>I',len(result))
    return ImageCms.ImageCmsProfile(io.BytesIO(result))

def _png_color_input(im,metadata,warnings):
    """Interpret PNG gAMA/cHRM without clipping RGB to the sRGB gamut.

    PNG3 sections4.3,11.3.2,13.13: gAMA is the encoding exponent.
    iCCP and sRGB take precedence; the caller invokes this only without them.
    RGB receives a matrix/TRC ICC profile; neutral gray is normalized directly
    with native precision. RGB matrix profiles have a zero black point.
    """
    if 'gamma' not in metadata and 'chromaticity' not in metadata:return None
    assumed=False;gamma=metadata.get('gamma');chrm=metadata.get('chromaticity')
    if gamma is not None and (not isinstance(gamma,(float,int)) or not np.isfinite(gamma) or gamma<=0):
        warnings.append('잘못된 PNG gAMA를 무시하고 sRGB 톤 응답을 가정했습니다.');gamma=None;assumed=True
    gray=im.mode in ('1','L','LA','I','I;16','I;16B','I;16L')
    if gamma is None:
        assumed=True
        if 'gamma' not in metadata:warnings.append('PNG gAMA 없음: sRGB 톤 응답을 가정했습니다.')
    srgb_matrix,srgb_white=_rgb_matrix(SRGB_CHRM)
    if chrm is not None:
        try:matrix,white=_rgb_matrix(chrm)
        except (ValueError,TypeError,np.linalg.LinAlgError):
            warnings.append('잘못된 PNG cHRM을 무시하고 sRGB 원색·백색점을 가정했습니다.');matrix,white=srgb_matrix,srgb_white;assumed=True
    else:
        matrix,white=srgb_matrix,srgb_white
        if not gray:warnings.append('PNG cHRM 없음: sRGB 원색·백색점을 가정했습니다.');assumed=True
    label='PNG '+('gAMA='+format(gamma,'.6g') if gamma is not None else 'sRGB 톤 가정')+(' · cHRM' if chrm is not None else ' · 중성 회색' if gray else ' · sRGB 원색 가정')
    if not gray:return None,_png_matrix_profile(gamma,matrix,white),label,assumed
    if im.mode.startswith('I;16') or im.mode=='I':raw=np.asarray(im);maximum=65535
    else:raw=np.asarray(im.convert('L'));maximum=255
    raw=raw.reshape(-1,1)
    output=np.empty((len(raw),3),dtype=np.uint8)
    # Bound float working buffers even for an image near the input pixel limit.
    for start in range(0,len(raw),262144):
        samples=np.clip(raw[start:start+262144].astype(np.float64)/maximum,0,1)
        linear=np.power(samples,1/gamma) if gamma is not None else np.where(samples<=.04045,samples/12.92,((samples+.055)/1.055)**2.4)
        linear=np.repeat(linear,3,axis=1)
        output[start:start+len(samples)]=np.rint(_srgb_encode(linear)*255).astype(np.uint8)
    result=Image.fromarray(output.reshape(im.height,im.width,3))
    return result,srgb_profile(),label,assumed

def load_source(filename):
    """Preserve opaque source channels/ICC; flatten alpha only by stated convention."""
    try:
        with Image.open(filename) as original:
            if original.format not in ('JPEG','PNG'):raise ValueError('PNG 또는 JPG 이미지 파일을 선택해 주세요.')
            if original.width*original.height>80000000:raise ValueError('이미지가 너무 큽니다. 8천만 픽셀 이하로 줄여 주세요.')
            original_mode=original.mode;icc=original.info.get('icc_profile');format_name=original.format
            metadata=dict(original.info);header=_png_header(filename) if format_name=='PNG' else {}
            im=ImageOps.exif_transpose(original);im.load()
    except UnidentifiedImageError as exc:raise ValueError('PNG 또는 JPG 이미지를 읽을 수 없습니다.') from exc
    warnings=[];source=None;metadata_used='ICC'
    if 'cicp' in header:
        if header['cicp']!=bytes([1,13,0,1]):raise ValueError('이 PNG의 cICP/HDR 색공간은 지원하지 않습니다. 색상 관리 프로그램에서 sRGB PNG로 변환해 주세요.')
        # Recognized full-range sRGB CICP is the highest-priority color tag.
        source=srgb_profile();metadata_used='PNG cICP sRGB'
    if header.get('bit_depth')==16 and header.get('color_type')==2 and 'transparency' in metadata:
        raise ValueError('16비트 RGB PNG의 tRNS 투명색을 정확히 읽을 수 없습니다. 색상 관리 프로그램에서 RGBA PNG로 변환해 주세요.')
    if header.get('bit_depth')==16 and header.get('color_type') in (2,4,6):
        warnings.append('16비트 다중 채널 PNG는 이미지 디코더에서 8비트로 줄여 처리합니다. 정밀 색상 비교는 색상 관리 프로그램에서 8비트 sRGB 사본으로 변환한 뒤 확인하세요.')
    if icc and source is None:
        try:source=ImageCms.getOpenProfile(io.BytesIO(icc))
        except (ImageCms.PyCMSError,OSError,TypeError,ValueError):warnings.append('내장 ICC를 읽을 수 없어 다른 색상 정보 또는 기본값을 사용했습니다.')
    space=source.profile.xcolor_space.strip() if source else None
    gray=original_mode in ('1','L','LA','I','I;16','I;16B','I;16L')
    expected='CMYK' if im.mode=='CMYK' else 'GRAY' if gray else 'RGB'
    valid=space==expected or (gray and space=='RGB')
    assumed=not valid
    converted=None
    if not valid:
        if source:warnings.append('내장 ICC와 이미지 채널이 일치하지 않아 다른 색상 정보 또는 기본값을 사용했습니다.')
        source=None
        if format_name=='PNG' and metadata.get('srgb') in (0,1,2,3):
            source=srgb_profile();assumed=False;metadata_used='PNG sRGB'
        elif format_name=='PNG' and im.mode!='CMYK':
            result=_png_color_input(im,metadata,warnings)
            if result is not None:converted,source,description,assumed=result;metadata_used='PNG gAMA/cHRM'
        if source is None:
            source=ImageCms.getOpenProfile(str(BASE/'icc/CoatedFOGRA39.icc')) if im.mode=='CMYK' else srgb_profile()
            warnings.append('프로파일 가정: '+('Coated FOGRA39' if im.mode=='CMYK' else 'sRGB'));metadata_used='assumed'
        space=source.profile.xcolor_space.strip()
    if metadata_used!='PNG gAMA/cHRM':description=ImageCms.getProfileDescription(source).strip()
    if format_name=='PNG' and 'srgb' in metadata and metadata.get('srgb') not in (0,1,2,3):warnings.append('잘못된 PNG sRGB 표식을 무시했습니다.')
    alpha=None;flattened=False
    if im.mode!='CMYK':
        if (im.mode.startswith('I;16') or im.mode=='I') and 'transparency' in metadata:
            # PNG3 11.3.1: test the full native sample before reducing depth.
            alpha=Image.fromarray(np.where(np.asarray(im)==metadata['transparency'],0,255).astype(np.uint8))
        elif im.mode in ('RGBA','LA','PA') or 'transparency' in im.info:alpha=im.convert('RGBA').getchannel('A')
        if im.mode.startswith('I;16') or im.mode=='I':
            im=Image.fromarray(np.rint(np.clip(np.asarray(im,dtype=float),0,65535)/257).astype(np.uint8))
        im=converted if converted is not None else im.convert('L') if space=='GRAY' else im.convert('RGBA').convert('RGB')
        if alpha is not None and alpha.getextrema()!=(255,255):
            # Explicit display-referred, encoded-sRGB white composite (not linear-light).
            im=ImageCms.profileToProfile(im,source,srgb_profile(),outputMode='RGB',renderingIntent=1,flags=BPC)
            im=Image.composite(im,Image.new('RGB',im.size,'white'),alpha)
            source=srgb_profile();flattened=True
            warnings.append('투명 이미지는 색 변환 후 encoded sRGB에서 흰색에 합성한 미리보기로 검사합니다. 원본 색공간에서의 인쇄 합성이나 넓은 색역 보존을 재현하지 않습니다.')
    info={'input_mode':original_mode,'working_mode':im.mode,'source_profile':description,'embedded_icc':bool(icc),'color_metadata_used':metadata_used,'profile_assumed':assumed,'untagged_sRGB_assumption':metadata_used=='assumed' and im.mode!='CMYK','input_warnings':warnings,'rendering_intent':'relative colorimetric + black point compensation','standard_input':'encoded sRGB white-composited preview' if flattened else 'original profile and channels (gray metadata may be normalized to neutral sRGB)','alpha_composite':'encoded sRGB on white after color conversion' if flattened else None}
    return im,source,info

def read_image_srgb(filename):
    im,source,info=load_source(filename)
    rgb=ImageCms.profileToProfile(im,source,srgb_profile(),outputMode='RGB',renderingIntent=1,flags=BPC)
    rgb.info['icc_profile']=srgb_profile().tobytes()
    return rgb,info

def same_cmyk_characterization(source,target):
    # LCMS can optimize/rewrite an inverse B2A table while retaining the same
    # printed CMYK characterization. Compare device-to-PCS data before use.
    def signature(profile):
        data=profile.tobytes();tags={}
        for index in range(int.from_bytes(data[128:132],'big')):
            entry=132+12*index;name=data[entry:entry+4]
            if name not in (b'A2B0',b'A2B1',b'A2B2',b'D2B0',b'D2B1',b'D2B2',b'D2B3',b'wtpt',b'bkpt',b'chad'):continue
            offset=int.from_bytes(data[entry+4:entry+8],'big');length=int.from_bytes(data[entry+8:entry+12],'big')
            tags[name]=data[offset:offset+length]
        return data[16:24],tags
    a=signature(source);b=signature(target)
    return a==b and any(name.startswith((b'A2B',b'D2B')) for name in a[1])

def proof_image(filename,out=None):
    f=pathlib.Path(filename).resolve()
    d=pathlib.Path(out or BASE/'new_previews'/f.stem);d.mkdir(parents=True,exist_ok=True)
    im,source,report=load_source(f)
    target=ImageCms.getOpenProfile(str(BASE/'icc/CoatedFOGRA39.icc'));srgb=srgb_profile()
    same_cmyk=im.mode=='CMYK' and same_cmyk_characterization(source,target)
    flags=ImageCms.Flags.SOFTPROOFING|ImageCms.Flags.BLACKPOINTCOMPENSATION
    ref=ImageCms.profileToProfile(im,source,srgb,outputMode='RGB',renderingIntent=1,flags=BPC)
    if im.mode=='CMYK':
        # CMYK already describes ink channels. Do not convert via RGB and re-separate it.
        if same_cmyk:
            # The display leg retains the simulated ink black. BPC belongs on
            # source-to-proof separation, not on proof-to-screen display.
            transform=ImageCms.buildTransformFromOpenProfiles(source,srgb,'CMYK','RGB',renderingIntent=1,flags=0)
        else:
            transform=ImageCms.buildProofTransformFromOpenProfiles(source,srgb,target,'CMYK','RGB',renderingIntent=1,proofRenderingIntent=1,flags=flags)
        normal=ImageCms.applyTransform(im,transform)
        mask=np.zeros((im.height,im.width),dtype=bool);gamut_applicable=False
    else:
        transform=ImageCms.buildProofTransformFromOpenProfiles(source,srgb,target,im.mode,'RGB',renderingIntent=1,proofRenderingIntent=1,flags=flags)
        alarm_transform=ImageCms.buildProofTransformFromOpenProfiles(source,srgb,target,im.mode,'RGB',renderingIntent=1,proofRenderingIntent=1,flags=flags|ImageCms.Flags.GAMUTCHECK)
        normal=ImageCms.applyTransform(im,transform);alarm=ImageCms.applyTransform(im,alarm_transform)
        mask=np.any(np.asarray(normal)!=np.asarray(alarm),axis=2);gamut_applicable=True
    marked=np.asarray(normal).copy();marked[mask]=[255,0,255]
    normal.save(d/'RGB_softproof.png',icc_profile=srgb.tobytes())
    Image.fromarray(marked).save(d/'RGB_gamut_warning.png',icc_profile=srgb.tobytes())
    ref.save(d/'RGB_reference.png',icc_profile=srgb.tobytes())
    report.update({'source':f.name,'render_revision':'11.1','proof_profile':'Coated FOGRA39 (ISO 12647-2:2004)',
                   'proof_rendering':'source -> FOGRA relative + BPC; FOGRA -> sRGB relative, BPC off to retain simulated ink black',
                   'gamut_check_applicable':gamut_applicable,
                   'gamut_alarm_percent':round(float(mask.mean()*100),3) if gamut_applicable else None,
                   'warning':'자주색은 RGB 원본의 인쇄 색역 초과 추정입니다. CMYK 입력에서는 변환 전 RGB 색역을 판정하지 않습니다. 원본 파일은 변경하지 않습니다.'})
    (d/'gamut_info.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False));return d

if __name__=='__main__':
    f=sys.argv[1] if len(sys.argv)>1 else None
    if not f:
        from native_dialogs import choose_file,notify
        interactive=True;f=choose_file('HARDYS - PNG/JPG 이미지를 선택하세요','rgb')
    if f:
        try:
            d=proof_image(f)
            if 'interactive' in locals():notify('HARDYS',str(d))
        except Exception as exc:
            if 'interactive' in locals():notify('HARDYS',str(exc),error=True)
            else:raise
