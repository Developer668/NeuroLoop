"""Install the reviewed Windows CPU media tools in this project only.
Resume bounded byte ranges, verify the vendor's full archive SHA256 before running.
No model downloads, GPU inference or system PATH changes.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib, json, shutil, subprocess, time
import httpx
ROOT=Path(__file__).resolve().parents[1]
URL='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
SHA='fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9'
SIZE=111253802
OUT=ROOT/'.tools/ffmpeg'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/'release.zip'
    offset=archive.stat().st_size if archive.exists() else 0
    if offset>SIZE:raise RuntimeError('Archive larger than reviewed release')
    step=4*1024*1024
    parts=[(start,min(start+step-1,SIZE-1)) for start in range(offset,SIZE,step)]
    def get(part):
        start,end=part;p=OUT/f'range-{start}-{end}.part'
        if p.exists() and p.stat().st_size==end-start+1:return p
        deadline=time.monotonic()+180
        with httpx.stream('GET',URL,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'},follow_redirects=True,timeout=30) as r:
            if r.status_code!=206 or r.headers.get('content-range')!=f'bytes {start}-{end}/{SIZE}':raise RuntimeError('Unexpected range response')
            n=0
            with p.open('wb') as f:
                for chunk in r.iter_raw(256*1024):
                    n+=len(chunk)
                    if n>end-start+1 or time.monotonic()>deadline:raise RuntimeError('Range exceeded size/time budget')
                    f.write(chunk)
            if n!=end-start+1:raise RuntimeError('Incomplete range')
        print('Verified range length',start,end,flush=True)
        return p
    with ThreadPoolExecutor(max_workers=8) as pool:paths=list(pool.map(get,parts))
    with archive.open('ab') as dest:
        for p in paths:
            with p.open('rb') as source:shutil.copyfileobj(source,dest)
    actual=hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual!=SHA:raise RuntimeError('Full SHA256 differs from reviewed vendor checksum; binaries not executed')
    with zipfile_open(archive) as z:
        for info in z.infolist():
            name=Path(info.filename).name
            if name.lower() in {'ffmpeg.exe','ffprobe.exe','license','license.txt','readme.txt'}:
                if info.file_size>250*1024*1024:raise RuntimeError('Unexpected archive entry size')
                with z.open(info) as src,(OUT/name).open('wb') as dst:shutil.copyfileobj(src,dst)
    receipt={'source':URL,'release':'9.0.1','archive_sha256':SHA,'bytes':SIZE,'binary_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.exe')}}
    (ROOT/'docs/FFMPEG_RECEIPT.json').write_text(json.dumps(receipt,indent=2))
    for p in OUT.glob('*.exe'):print(subprocess.run([str(p),'-version'],capture_output=True,text=True,check=True,timeout=10).stdout.splitlines()[0])
    for p in paths:p.unlink()
    archive.unlink()
    print('Installed and checksum verified; only project-local files changed.',flush=True)

def zipfile_open(path):
    from zipfile import ZipFile
    return ZipFile(path)

if __name__=='__main__':main()
