"""Bounded local media operations. No remote URLs or arbitrary shell expressions."""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageOps
from .config import settings

SUFFIXES = {'.mp4':'video','.mov':'video','.webm':'video','.mkv':'video','.avi':'video','.wav':'audio','.mp3':'audio','.flac':'audio','.ogg':'audio','.png':'image','.jpg':'image','.jpeg':'image','.webp':'image','.txt':'text'}
FILTERS = {'contrast_up':'eq=contrast=1.08','contrast_down':'eq=contrast=0.92','brightness_up':'eq=brightness=0.035','brightness_down':'eq=brightness=-0.035','saturation_up':'eq=saturation=1.12','saturation_down':'eq=saturation=0.88'}

class MediaError(ValueError):
    pass

def ffmpeg() -> str:
    configured=os.getenv('NEUROLOOP_FFMPEG')
    if configured and Path(configured).is_file(): return configured
    binary=shutil.which('ffmpeg')
    if binary: return binary
    folder=settings().root/'.runtimes/model/Lib/site-packages/imageio_ffmpeg/binaries'
    matches=list(folder.glob('ffmpeg*.exe'))
    if matches: return str(matches[0])
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc: raise MediaError('FFmpeg is not installed/configured') from exc

FILE_INPUT_OPTIONS = ['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,avi,wav,mp3,flac,ogg,aac,image2,image2pipe,png_pipe,jpeg_pipe,webp_pipe']

def guarded_inputs(args: list[str]) -> list[str]:
    """Reject remote sources and playlist demuxing, regardless of file extension."""
    guarded=[]; input_format=None
    for index,value in enumerate(args):
        if value=='-f' and index+1<len(args): input_format=args[index+1]
        if value=='-i':
            if index+1>=len(args): raise MediaError('Missing media input')
            source=args[index+1]
            if input_format=='lavfi':
                if not source.startswith(('testsrc2=', 'testsrc=', 'color=', 'sine=', 'anullsrc=')):
                    raise MediaError('Unsupported internal fixture generator')
            else:
                if '://' in source or not Path(source).is_file():
                    raise MediaError('Only existing local media files are accepted')
                guarded.extend(FILE_INPUT_OPTIONS)
            input_format=None
        guarded.append(value)
    return guarded

def execute(args: list[str], timeout: int=120) -> subprocess.CompletedProcess:
    result=subprocess.run([ffmpeg(),'-hide_banner','-loglevel','error','-nostdin',*guarded_inputs(args)],capture_output=True,timeout=timeout)
    if result.returncode:
        raise MediaError(result.stderr.decode('utf-8',errors='replace')[-2000:])
    return result

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''): h.update(part)
    return h.hexdigest()

def inspect_media(path: Path, kind: str) -> dict:
    if kind=='image':
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if im.width*im.height>40_000_000: raise MediaError('Image exceeds 40 megapixels')
            return {'width':im.width,'height':im.height,'format':im.format,'duration':None,'has_audio':False}
    if kind=='text':
        content=path.read_text(encoding='utf-8')
        if not content.strip() or len(content)>50000: raise MediaError('Text must contain 1–50,000 characters')
        return {'characters':len(content),'preview_text':content[:200],'duration':None,'has_audio':False}
    p=subprocess.run([ffmpeg(),'-hide_banner','-nostdin',*FILE_INPUT_OPTIONS,'-i',str(path),'-t','0','-f','null','-'],capture_output=True,timeout=30)
    text=p.stderr.decode('utf-8',errors='replace')
    if p.returncode: raise MediaError('Media container could not be safely decoded')
    match=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',text)
    if not match: raise MediaError('Cannot read a valid media duration')
    duration=int(match[1])*3600+int(match[2])*60+float(match[3])
    if not 0<duration<=settings().max_media_seconds: raise MediaError(f'Media must be at most {settings().max_media_seconds} seconds')
    dimensions=re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b',text)
    if kind=='video' and not dimensions: raise MediaError('File contains no decodable video stream')
    if dimensions and int(dimensions[1])*int(dimensions[2])>16_777_216: raise MediaError('Video exceeds the permitted decoded resolution')
    has_audio=bool(re.search(r'Stream .*Audio:',text))
    if kind=='audio' and not has_audio: raise MediaError('File contains no audio stream')
    return {'duration':duration,'width':int(dimensions[1]) if dimensions else None,'height':int(dimensions[2]) if dimensions else None,'has_audio':has_audio}

def thumbnail(path: Path, kind: str, destination: Path) -> bool:
    try:
        if kind=='image':
            with Image.open(path) as im:
                im=ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((800,600)); im.save(destination,'JPEG',quality=88)
            return True
        if kind=='video':
            execute(['-y','-i',str(path),'-frames:v','1','-vf','scale=800:-2',str(destination)],30)
            return True
    except (OSError,MediaError,subprocess.TimeoutExpired):
        return False
    return False

def static_presentation(path: Path, destination: Path, seconds: int) -> Path:
    execute(['-y','-loop','1','-i',str(path),'-t',str(seconds),'-vf','scale=640:-2:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2','-r','12','-an','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p',str(destination)])
    return destination

def render_filter(source: Path,destination: Path,operator: str) -> Path:
    if operator not in FILTERS: raise MediaError('Unsupported controlled operator')
    execute(['-y','-i',str(source),'-vf',FILTERS[operator],'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-pix_fmt','yuv420p',str(destination)])
    return destination

def compose(source: Path,destination: Path,spec: dict) -> Path:
    sizes={'landscape':(1280,720),'portrait':(720,1280),'square':(960,960)}
    width,height=sizes[spec.get('aspect','landscape')]
    duration=int(spec['duration']); start=float(spec['headline_start'])
    if not 0<=start<duration-0.25: raise MediaError('Headline must appear before the creative ends')
    font_candidates=[Path('C:/Windows/Fonts/georgia.ttf'),Path('/System/Library/Fonts/Supplemental/Georgia.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf')]
    font=next((p for p in font_candidates if p.exists()),None)
    if font is None: raise MediaError('A local render font must be configured')
    # Fixed filenames and cwd avoid FFmpeg filter escaping/injection from input text.
    tmp=destination.parent/(destination.stem+'_composition'); tmp.mkdir(exist_ok=True)
    (tmp/'headline.txt').write_text(spec['headline'],encoding='utf-8')
    (tmp/'subline.txt').write_text(spec.get('subline',''),encoding='utf-8')
    shutil.copyfile(font,tmp/'font.ttf')
    video_filter=(f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x171515,'
        f'drawbox=x=0:y=ih*0.66:w=iw:h=ih*0.34:color=black@0.62:t=fill:enable=gte(t\\,{start}),'
        f'drawtext=fontfile=font.ttf:textfile=headline.txt:expansion=none:fontsize={int(width*.045)}:fontcolor=0xf5eee4:x=w*0.06:y=h*0.74:enable=gte(t\\,{start}),'
        f'drawtext=fontfile=font.ttf:textfile=subline.txt:expansion=none:fontsize={int(width*.019)}:fontcolor=0xd9cbbb:x=w*0.06:y=h*0.86:enable=gte(t\\,{start})')
    suffix=source.suffix.lower()
    input_args=['-loop','1'] if suffix in {'.png','.jpg','.jpeg','.webp'} else ['-stream_loop','-1']
    result=subprocess.run([ffmpeg(),'-hide_banner','-loglevel','error','-nostdin','-y',*input_args,*FILE_INPUT_OPTIONS,'-i',str(source.resolve()),'-t',str(duration),'-vf',video_filter,'-r','24','-an','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p',str(destination.resolve())],cwd=tmp,capture_output=True,timeout=180)
    if result.returncode: raise MediaError(result.stderr.decode(errors='replace')[-2000:])
    return destination
