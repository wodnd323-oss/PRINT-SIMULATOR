"""One forward contract for photo estimates, inverse colors and gradients.

Photo mode: source-profile interpretation -> encoded sRGB -> photo model ONCE.
ICC mode: independent FOGRA39 standard proof, without photo correction.
CMYK recommendations in photo mode require the bundled GRACoL profile.
"""
import pathlib
import numpy as np
from PIL import Image, ImageCms
from color_model import PhotoModel, SRGB
BASE=pathlib.Path(__file__).resolve().parent
PIPELINE='source_srgb_photo_v11'

def image(points,mode='RGB'):
    if mode not in ('RGB','CMYK'):raise ValueError('입력 색상 형식은 RGB 또는 CMYK여야 합니다.')
    a=np.asarray(points,dtype=float)
    if a.ndim==0 or a.shape[-1]!=len(mode) or not np.isfinite(a).all() or np.any((a<0)|(a>255)):raise ValueError('색상 값의 개수와 0~255 범위를 확인해 주세요.')
    a=np.rint(a).astype(np.uint8).reshape(1,-1,len(mode))
    return Image.frombytes(mode,(a.shape[1],1),a.tobytes())

class Predictor:
    def __init__(self,document,strength=1.,mode='photo'):
        if mode not in ('photo','icc'):raise ValueError('Unknown prediction mode')
        if not np.isfinite(strength) or not 0<=strength<=1:raise ValueError('보정 강도는 0~1 사이여야 합니다.')
        self.mode=mode;self.strength=strength;self.model=PhotoModel(document)
        self.input_profile='GRACoL2013_CRPC6.icc' if mode=='photo' else 'CoatedFOGRA39.icc'
        self.profile=ImageCms.getOpenProfile(str(BASE/'icc'/self.input_profile))
        flags=ImageCms.Flags.BLACKPOINTCOMPENSATION
        self.to_ink=ImageCms.buildTransformFromOpenProfiles(SRGB,self.profile,'RGB','CMYK',renderingIntent=1,flags=flags)
        # Photo inputs use source normalization with BPC. Standard CMYK is
        # already separated ink: retain its finite printed black in the display
        # conversion, as LCMS does in the return leg of a soft-proof transform.
        return_flags=flags if mode=='photo' else 0
        self.to_rgb=ImageCms.buildTransformFromOpenProfiles(self.profile,SRGB,'CMYK','RGB',renderingIntent=1,flags=return_flags)
        self.rgb_proof=ImageCms.buildProofTransformFromOpenProfiles(SRGB,SRGB,self.profile,'RGB','RGB',renderingIntent=1,proofRenderingIntent=1,flags=flags|ImageCms.Flags.SOFTPROOFING) if mode=='icc' else None
    def forward(self,points,input_mode='RGB'):
        im=image(points,input_mode)
        ink=ImageCms.applyTransform(im,self.to_ink) if input_mode=='RGB' else im
        cmyk=np.asarray(ink).reshape(-1,4).astype(int)
        # RGB standard proof must match proof_rgb_image, including LCMS's proof
        # adaptation. An 8-bit CMYK round-trip is NOT the same transform.
        if input_mode=='RGB':
            baseline_image=im if self.mode=='photo' else ImageCms.applyTransform(im,self.rgb_proof)
        else:baseline_image=ImageCms.applyTransform(ink,self.to_rgb)
        baseline=np.asarray(baseline_image).reshape(-1,3)
        predicted=(np.rint(self.model.transform(baseline,self.strength)) if self.mode=='photo' else baseline).clip(0,255).astype(int)
        return predicted,baseline,cmyk

def gamut_flags(points):
    """LCMS ICC gamut alarm, separate from empirical fit residual or ink limit."""
    fogra=ImageCms.getOpenProfile(str(BASE/'icc/CoatedFOGRA39.icc'))
    flags=ImageCms.Flags.SOFTPROOFING|ImageCms.Flags.BLACKPOINTCOMPENSATION
    normal=ImageCms.buildProofTransformFromOpenProfiles(SRGB,SRGB,fogra,'RGB','RGB',renderingIntent=1,proofRenderingIntent=1,flags=flags)
    alarm=ImageCms.buildProofTransformFromOpenProfiles(SRGB,SRGB,fogra,'RGB','RGB',renderingIntent=1,proofRenderingIntent=1,flags=flags|ImageCms.Flags.GAMUTCHECK)
    im=image(points)
    return np.any(np.asarray(ImageCms.applyTransform(im,normal))!=np.asarray(ImageCms.applyTransform(im,alarm)),axis=2).reshape(-1)
