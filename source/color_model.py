"""Display-referred photo matching of source-profile-interpreted sRGB.
These are photograph comparisons, not measured press corrections.
"""
import io,json,pathlib
import numpy as np
from PIL import Image,ImageCms,ImageFilter,ImageOps

SRGB=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
XYZ=np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]])
WHITE=np.array([.95047,1.,1.08883])

def rgb_to_lab(rgb):
    v=np.asarray(rgb,dtype=np.float64)/255
    linear=np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)
    t=(linear@XYZ.T)/WHITE;d=6/29
    f=np.where(t>d**3,np.cbrt(t),t/(3*d*d)+4/29)
    return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),axis=-1)

def lab_to_rgb(lab):
    lab=np.asarray(lab,dtype=np.float64);fy=(lab[...,0]+16)/116
    f=np.stack((fy+lab[...,1]/500,fy,fy-lab[...,2]/200),axis=-1);d=6/29
    t=np.where(f>d,f**3,3*d*d*(f-4/29))
    linear=(t*WHITE)@np.linalg.inv(XYZ).T
    v=np.where(linear<=.0031308,linear*12.92,1.055*np.maximum(linear,0)**(1/2.4)-.055)
    return np.clip(v*255,0,255)

def read_srgb(file):
    from proof_rgb_image import read_image_srgb
    return read_image_srgb(file)

def save_srgb(im,destination):im.save(destination,icc_profile=SRGB.tobytes())

def kernel(distance,radius):
    r=np.minimum(np.asarray(distance)/radius,1.)
    return (1-r)**4*(4*r+1)

class PhotoModel:
    def __init__(self,document):
        self.document=document;self.radius=float(document.get('radius',26));self.max_delta=float(document.get('max_delta',32))
        if not np.isfinite(self.radius) or self.radius<=0:raise ValueError('보정 반경은 0보다 큰 유한한 값이어야 합니다.')
        if not np.isfinite(self.max_delta) or not 0<=self.max_delta<=100:raise ValueError('최대 보정 색차는 0~100 사이여야 합니다.')
        if not isinstance(document.get('anchors',[]),list) or len(document.get('anchors',[]))>128:raise ValueError('기준점은 최대 128개입니다.')
        for anchor in document.get('anchors',[]):
            for key in ('source_rgb','target_rgb'):
                value=np.asarray(anchor.get(key),dtype=float)
                if value.shape!=(3,) or not np.isfinite(value).all() or np.any((value<0)|(value>255)):raise ValueError('기준점 RGB는 0~255의 유한한 세 값이어야 합니다.')
        self.anchors=[a for a in document.get('anchors',[]) if a.get('enabled',True)]
        if self.anchors:
            self.source=rgb_to_lab([a['source_rgb'] for a in self.anchors]);self.target=rgb_to_lab([a['target_rgb'] for a in self.anchors])
            distance=np.linalg.norm(self.source[:,None]-self.source[None,:],axis=-1)
            matrix=kernel(distance,self.radius)+np.eye(len(self.anchors))*.08
            self.weights=np.linalg.solve(matrix,self.target-self.source)
        else:self.source=np.empty((0,3));self.target=np.empty((0,3));self.weights=np.empty((0,3))

    def transform(self,rgb,strength=1.):
        rgb=np.asarray(rgb,dtype=np.float64)
        _validate_transform(rgb,strength)
        if not self.anchors or strength==0:return rgb.copy()
        lab=rgb_to_lab(rgb);distance=np.linalg.norm(lab[...,None,:]-self.source,axis=-1)
        delta=kernel(distance,self.radius)@self.weights
        norm=np.linalg.norm(delta,axis=-1,keepdims=True)
        delta*=np.minimum(1.,self.max_delta/np.maximum(norm,1e-8))
        # Keep whites and neutral grays outside the colored correction model.
        chroma=np.linalg.norm(lab[...,1:],axis=-1,keepdims=True)
        delta*=np.clip((chroma-8)/8,0,1)
        result=lab_to_rgb(lab+delta*float(strength))
        return np.where((distance.min(axis=-1)>=self.radius)[...,None],rgb,result)

    def nearest(self,rgb):
        if not self.anchors:return np.full(np.asarray(rgb).shape[:-1],999.)
        lab=rgb_to_lab(rgb)
        return np.linalg.norm(lab[...,None,:]-self.source,axis=-1).min(axis=-1)

    def make_lut(self,strength=1.,size=33):
        axis=np.linspace(0,255,size);b,g,r=np.meshgrid(axis,axis,axis,indexing='ij')
        grid=np.stack((r,g,b),axis=-1).reshape(-1,3)
        table=(self.transform(grid,strength)/255).reshape(-1).tolist()
        return ImageFilter.Color3DLUT(size,table,channels=3,target_mode='RGB')

    def apply(self,im,strength=1.):
        if strength==0 or not self.anchors:return im.copy()
        a=np.asarray(im.convert('RGB'));flat=a.reshape(-1,3);out=np.empty_like(flat)
        for start in range(0,len(flat),32768):
            out[start:start+32768]=np.clip(np.rint(self.transform(flat[start:start+32768],strength)),0,255).astype(np.uint8)
        return Image.fromarray(out.reshape(a.shape))

    def support(self,im):
        thumb=im.copy();thumb.thumbnail((650,650));a=np.asarray(thumb)
        lab=rgb_to_lab(a);nearest=self.nearest(a);colors=np.linalg.norm(lab[...,1:],axis=-1)>16;n=max(int(colors.sum()),1)
        return {'near_reference_percent':round(float(((nearest<=12)&colors).sum())*100/n,1),'transition_percent':round(float(((nearest>12)&(nearest<self.radius)&colors).sum())*100/n,1),'unsupported_percent':round(float(((nearest>=self.radius)&colors).sum())*100/n,1),'meaning':'Share of chromatic pixels near reference colors; not prediction accuracy.'}

    def support_overlay(self,im):
        axis=np.linspace(0,255,33);b,g,r=np.meshgrid(axis,axis,axis,indexing='ij');grid=np.stack((r,g,b),axis=-1).reshape(-1,3)
        lab=rgb_to_lab(grid);near=self.nearest(grid);colorful=np.linalg.norm(lab[:,1:],axis=-1)>16
        unsupported=(near>=self.radius)&colorful;transition=(near>12)&(near<self.radius)&colorful;table=grid.copy()
        table[unsupported]=table[unsupported]*.35+np.array([200,65,205])*.65
        table[transition]=table[transition]*.45+np.array([245,175,40])*.55
        return im.filter(ImageFilter.Color3DLUT(33,(table/255).reshape(-1).tolist(),channels=3))

def load_model(path):return PhotoModel(json.loads(pathlib.Path(path).read_text('utf-8')))

def _validate_transform(rgb,strength):
    if rgb.ndim==0 or rgb.shape[-1]!=3 or not np.isfinite(rgb).all() or np.any((rgb<0)|(rgb>255)):
        raise ValueError('RGB 입력은 0~255의 유한한 세 값이어야 합니다.')
    if not np.isfinite(strength) or not 0<=strength<=1:raise ValueError('보정 강도는 0~1 사이여야 합니다.')

# The global variant deliberately extrapolates beyond the observed hues.
# Identity regularization and neutral preservation are assumptions, not data.
BoundedPhotoModel=PhotoModel

class GlobalPhotoModel(BoundedPhotoModel):
    def __init__(self,document):
        super().__init__(document)
        self.chroma_matrix=np.eye(2);self.tone_coefficients=np.zeros(4)
        self.residual_weights=np.zeros_like(self.weights)
        if not self.anchors:return
        source=self.source;target=self.target;ab=source[:,1:];target_ab=target[:,1:]
        angles=np.arctan2(ab[:,1],ab[:,0]);bins=np.floor((angles+np.pi)/(np.pi/3)).astype(int).clip(0,5)
        counts=np.bincount(bins,minlength=6);w=1/counts[bins];w*=len(w)/w.sum()
        # A single regularized rotation/scale has fewer unsupported degrees of
        # freedom than a full hue-skew matrix fitted to only two color families.
        z=ab[:,0]+1j*ab[:,1];zt=target_ab[:,0]+1j*target_ab[:,1]
        energy=float(np.sum(w*np.abs(z)**2));ridge=.12*max(energy,1)
        coefficient=(np.sum(w*np.conj(z)*zt)+ridge)/(energy+ridge)
        scale=np.clip(abs(coefficient),.5,1.1);angle=np.clip(np.angle(coefficient),-np.pi/9,np.pi/9)
        real=scale*np.cos(angle);imag=scale*np.sin(angle)
        self.chroma_matrix=np.array([[real,imag],[-imag,real]])
        features=self._features(source);envelope=self._envelope(source)
        delta=(target[:,0]-source[:,0])/np.maximum(envelope,.25)
        tone_features=features[:,:2]
        self.tone_coefficients[:2]=np.linalg.solve(tone_features.T@(tone_features*w[:,None])+np.eye(2)*2,tone_features.T@(delta*w))
        distances=np.linalg.norm(source[:,None]-source[None,:],axis=-1)
        k=kernel(distances,self.radius)+np.eye(len(source))*.08
        self.residual_weights=np.linalg.solve(k,target-self.global_lab(source))

    @staticmethod
    def _features(lab):
        return np.stack((np.ones(lab.shape[:-1]),(lab[...,0]-50)/40,lab[...,1]/40,lab[...,2]/40),axis=-1)

    @staticmethod
    def _envelope(lab):
        chroma=np.linalg.norm(lab[...,1:],axis=-1)
        return np.maximum(0,np.sin(np.pi*np.clip(lab[...,0],0,100)/100))*np.clip((chroma-8)/12,0,1)

    def global_lab(self,lab):
        result=np.array(lab,dtype=float,copy=True)
        result[...,1:]=lab[...,1:]@self.chroma_matrix
        tone=np.clip(self._features(lab)@self.tone_coefficients,-24,18)*self._envelope(lab)
        result[...,0]=np.clip(lab[...,0]+tone,0,100)
        return result

    def transform(self,rgb,strength=1.):
        rgb=np.asarray(rgb,dtype=np.float64)
        _validate_transform(rgb,strength)
        if not self.anchors or strength==0:return rgb.copy()
        lab=rgb_to_lab(rgb);adjusted=self.global_lab(lab)
        distances=np.linalg.norm(lab[...,None,:]-self.source,axis=-1)
        residual=kernel(distances,self.radius)@self.residual_weights
        adjusted+=residual*np.clip((np.linalg.norm(lab[...,1:],axis=-1,keepdims=True)-8)/8,0,1)
        delta=adjusted-lab
        # Smoothly activate the entire correction at the neutral boundary.
        # A hard C*=8 switch introduced contours in weakly colored gradients.
        chroma=np.linalg.norm(lab[...,1:],axis=-1,keepdims=True)
        gate=np.clip((chroma-8)/8,0,1)
        delta*=gate*gate*(3-2*gate)
        norm=np.linalg.norm(delta,axis=-1,keepdims=True)
        delta*=np.minimum(1.,self.max_delta/np.maximum(norm,1e-8))
        return lab_to_rgb(lab+delta*float(strength))

    def fit_information(self):
        return {'method':'global_extrapolation_plus_local_residual','global_chroma_model':'regularized uniform hue rotation and chroma scale','global_tone_model':'regularized lightness trend; no unobserved hue-specific exposure','chroma_matrix':self.chroma_matrix.tolist(),'tone_coefficients':self.tone_coefficients.tolist(),'assumptions':['Global chroma and tone trend extends to unobserved hues.','Neutral grays and white remain neutral.','No physical printer measurements; reference-photo fit only.']}

PhotoModel=GlobalPhotoModel
