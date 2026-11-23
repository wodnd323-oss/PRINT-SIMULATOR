"""Deterministically rebuild V11.2 from the verified V11.1 distribution.

Unchanged ZIP compressed payloads are copied verbatim. New/changed files use
ZIP_STORED, so Linux and Windows produce the same bytes without depending on
the host zlib version. Originals and user state are never modified.
"""
from pathlib import Path, PurePosixPath
import argparse
import binascii
import hashlib
import json
import shutil
import struct
import tempfile
import zipfile

DOS_DATE=((2026-1980)<<9)|(11<<5)|23
ROOT=Path(__file__).resolve().parent.parent

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def safe_relative(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe path: '+name)
    return p.as_posix()

class RawZipWriter:
    def __init__(self,path):
        self.path=Path(path);self.fp=self.path.open('wb');self.rows=[]
    def add(self,name,data=None,source=None,info=None):
        name=safe_relative(name);encoded=name.encode('utf8');offset=self.fp.tell()
        if data is None:
            method=info.compress_type;crc=info.CRC;size=info.file_size;csize=info.compress_size
            source.seek(info.header_offset)
            header=source.read(30)
            fields=struct.unpack('<IHHHHHIIIHH',header)
            if fields[0]!=0x04034b50:raise ValueError('Invalid source local header')
            source.seek(fields[9]+fields[10],1)
        else:
            method=0;size=csize=len(data);crc=binascii.crc32(data)&0xffffffff
        if max(size,csize,offset)>=0xffffffff:raise ValueError('ZIP64 is not needed or supported for this release')
        self.fp.write(struct.pack('<IHHHHHIIIHH',0x04034b50,20,0x800,method,0,DOS_DATE,crc,csize,size,len(encoded),0))
        self.fp.write(encoded)
        if data is not None:self.fp.write(data)
        else:
            remaining=csize
            while remaining:
                part=source.read(min(1024*1024,remaining))
                if not part:raise ValueError('Truncated source ZIP payload')
                self.fp.write(part);remaining-=len(part)
        self.rows.append((encoded,method,crc,csize,size,offset))
    def close(self):
        start=self.fp.tell()
        for name,method,crc,csize,size,offset in self.rows:
            self.fp.write(struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,0x0314,20,0x800,method,0,DOS_DATE,crc,csize,size,len(name),0,0,0,0,0o100644<<16,offset))
            self.fp.write(name)
        length=self.fp.tell()-start;n=len(self.rows)
        if n>=65535:raise ValueError('Too many ZIP entries')
        self.fp.write(struct.pack('<IHHHHIIH',0x06054b50,0,0,n,n,length,start,0));self.fp.close()

def original_entries(z):
    entries={}
    roots=set()
    for info in z.infolist():
        if info.is_dir():continue
        path=PurePosixPath(safe_relative(info.filename))
        if len(path.parts)<2:raise ValueError('Expected one enclosing install directory')
        roots.add(path.parts[0]);relative=PurePosixPath(*path.parts[1:]).as_posix()
        if relative in entries:raise ValueError('Duplicate source file')
        entries[relative]=info
    if len(roots)!=1:raise ValueError('Expected exactly one original install directory')
    return entries

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'packaging/release_v11_2.json')
    parser.add_argument('--base-install',type=Path)
    parser.add_argument('--base-update',type=Path,default=ROOT/'distribution/HARDYS_PrintSimulator_v11_1_Update.zip')
    parser.add_argument('--source-root',type=Path,default=ROOT/'source')
    parser.add_argument('--out',type=Path,default=ROOT/'release')
    args=parser.parse_args();config=json.loads(args.config.read_text('utf8'))
    args.out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hardys-release-') as temp:
        if args.base_install is None:
            base=Path(temp)/'base_install.zip'
            parts=sorted((ROOT/'distribution/parts').glob('installer.*'))
            if not parts:raise ValueError('Missing verified V11.1 installer parts')
            with base.open('wb') as dest:
                for part in parts:
                    with part.open('rb') as src:shutil.copyfileobj(src,dest)
        else:base=args.base_install
        if digest(base)!=config['base_install_sha256']:raise ValueError('Original full ZIP hash mismatch')
        if digest(args.base_update)!=config['base_update_sha256']:raise ValueError('Original patch ZIP hash mismatch')
        overlays={safe_relative(rel):(args.source_root/rel).read_bytes() for rel in config['overlay_paths']}
        expected_overlays=config['overlay_sha256']
        if set(expected_overlays)!=set(overlays):raise ValueError('Overlay hash inventory mismatch')
        for rel,data in overlays.items():
            if hashlib.sha256(data).hexdigest()!=expected_overlays[rel]:raise ValueError('Overlay bytes changed: '+rel)
        if 'RELEASE_MANIFEST.json' in overlays:raise ValueError('The release manifest is generated, never overlaid')
        for rel in overlays:
            if PurePosixPath(rel).parts[0] in ('state','uploads','renders','exports','runtime'):
                raise ValueError('User state and runtime are not overlay targets: '+rel)
        with zipfile.ZipFile(base) as old,base.open('rb') as raw:
            entries=original_entries(old)
            names=sorted((set(entries)|set(overlays))-{'RELEASE_MANIFEST.json'})
            rows=[]
            for rel in names:
                data=overlays[rel] if rel in overlays else old.read(entries[rel])
                rows.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            manifest={'version':11,'revision':'11.2','date':'2026-11-23','origin':'Verified V11.1 distribution with purpose-review fixes','origin_zip_sha256':config['base_install_sha256'],'photo_model_unchanged':True,'files':rows}
            manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
            full=args.out/config['full_filename'];writer=RawZipWriter(full)
            prefix='HARDYS_PrintSimulator_v11_2/'
            for rel in sorted(names+['RELEASE_MANIFEST.json']):
                if rel=='RELEASE_MANIFEST.json':writer.add(prefix+rel,data=manifest_bytes)
                elif rel in overlays:writer.add(prefix+rel,data=overlays[rel])
                else:writer.add(prefix+rel,source=raw,info=entries[rel])
            writer.close()
            with zipfile.ZipFile(args.base_update) as old_patch:
                patch_names={i.filename[len('UPDATE_FILES/'):] for i in old_patch.infolist() if not i.is_dir() and i.filename.startswith('UPDATE_FILES/')}
            patch_names=(patch_names|set(overlays)|{'RELEASE_MANIFEST.json'})
            patch=args.out/config['update_filename'];writer=RawZipWriter(patch)
            readme=(
                'HARDYS 인쇄색 시뮬레이터 V11.2 업데이트 (2026-11-23)\r\n\r\n'
                '대상: 기존 V11 또는 V11.1 설치본. 신규 설치는 Full_Install.zip을 사용하세요.\r\n'
                '1. 프로그램을 종료하고 기존 설치 폴더 전체를 백업합니다.\r\n'
                '2. 이 ZIP을 모두 풀고 UPDATE_FILES 안의 내용을 START.cmd가 있는 기존 폴더에 덮어씁니다.\r\n'
                '3. START.cmd로 다시 실행하고 화면의 V11.2를 확인합니다.\r\n'
                'state/calibration.json 등 사용자 보정·업로드 파일은 이 패치에 포함하지 않습니다.\r\n'
                '변경 내용: HARDYS_V11_2_UPDATE_NOTES.txt 또는 도움말의 V11.2 변경 내용.\r\n'
                '최신 검증은 verification_results/update_v11_2 및 GitHub 릴리스의 Windows 검증 JSON을 참고하세요.\r\n'
            ).encode('utf-8-sig')
            writer.add('UPDATE_README.txt',data=readme)
            for rel in sorted(patch_names):
                if rel=='RELEASE_MANIFEST.json':writer.add('UPDATE_FILES/'+rel,data=manifest_bytes)
                elif rel in overlays:writer.add('UPDATE_FILES/'+rel,data=overlays[rel])
                else:writer.add('UPDATE_FILES/'+rel,source=raw,info=entries[rel])
            writer.close()
        # Validate every full file against the generated manifest, and every
        # patch file against its full-install counterpart before delivery.
        with zipfile.ZipFile(full) as z,zipfile.ZipFile(patch) as p:
            if z.testzip() or p.testzip():raise ValueError('ZIP CRC verification failed')
            if len(z.infolist())!=len(rows)+1:raise ValueError('Unexpected full-install entries')
            for row in rows:
                data=z.read(prefix+row['path'])
                if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Full file verification failed: '+row['path'])
            for rel in patch_names:
                if p.read('UPDATE_FILES/'+rel)!=z.read(prefix+rel):raise ValueError('Patch/full mismatch: '+rel)
        checksums=''.join(digest(p)+'  '+p.name+'\n' for p in (full,patch))
        (args.out/'SHA256SUMS').write_text(checksums,encoding='utf8',newline='\n')
        receipt={'revision':'11.2','original_full_sha256':config['base_install_sha256'],'original_patch_sha256':config['base_update_sha256'],'full_manifest_files':len(rows),'full_zip_files':len(rows)+1,'patch_content_files':len(patch_names),'overlay_files':len(overlays),'verified_all_full_files':True,'verified_patch_matches_full':True,'artifacts':[{'name':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in (full,patch)]}
        (args.out/'BUILD_VERIFICATION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
        print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
