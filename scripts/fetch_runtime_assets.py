"""Fetch the official pinned spaCy wheel before installation, with SHA-256 verification."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,requests,os
ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl'
SHA256='293e9547a655b25499198ab15a525b05b9407a75f10255e405e8c3854329ab63'
SIZE=400658291

def main():
    folder=ROOT/'infrastructure/wheels';folder.mkdir(parents=True,exist_ok=True)
    target=folder/'en_core_web_lg-3.8.0-py3-none-any.whl'
    def digest(p):
        with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    if target.is_file() and target.stat().st_size==SIZE and digest(target)==SHA256:
        print('Pinned wheel already verified');return
    parts=folder/'spacy-download';parts.mkdir(exist_ok=True)
    chunk=8*1024*1024
    def fetch(start):
        end=min(start+chunk,SIZE)-1;part=parts/str(start)
        if part.is_file() and part.stat().st_size==end-start+1:return part
        with requests.get(URL,headers={'Range':f'bytes={start}-{end}'},stream=True,timeout=60) as r:
            r.raise_for_status()
            if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{SIZE}':
                raise RuntimeError('Server did not honor the exact requested byte range')
            temp=part.with_suffix('.partial')
            with temp.open('wb') as f:
                for block in r.iter_content(1024*1024):f.write(block)
            if temp.stat().st_size!=end-start+1:raise RuntimeError('Incomplete range')
            os.replace(temp,part)
            return part
    with ThreadPoolExecutor(max_workers=12) as pool:
        ordered=list(pool.map(fetch,range(0,SIZE,chunk)))
    assembled=target.with_suffix('.verified-partial')
    with assembled.open('wb') as output:
        for part in ordered:
            with part.open('rb') as f:
                while block:=f.read(4*1024*1024):output.write(block)
    if digest(assembled)!=SHA256:raise RuntimeError('Official wheel SHA-256 mismatch')
    os.replace(assembled,target)
    (folder/'provenance.json').write_text(json.dumps({'source':URL,'sha256':SHA256,'bytes':SIZE},indent=2))
    print('Verified official spaCy 3.8.0 wheel: '+SHA256)

if __name__=='__main__':main()
