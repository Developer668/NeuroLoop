"""Local inference boundary. Uses downloaded, frozen weights and structured media events.

Only the dedicated worker calls this module. The API process never loads a GPU model.
There is no generated Python execution and no model-server shell command.
"""
from __future__ import annotations
import gc, hashlib, json, os, sys, time, subprocess
import platform
from pathlib import Path
from functools import lru_cache
from .persistence import atomic_json, atomic_numpy
from .config import settings
from .media import execute, static_presentation
from .readout import summarize, validate_response

_model=None


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()

@lru_cache(maxsize=1)
def profile_id() -> str:
    root=settings().root
    files=[root/'models/load_local_tribe.py',root/'tribev2-balanced-qv-local/load_quantized_tribev2.py',root/'tribev2-balanced-qv-local/config.yaml',root/'tribev2-balanced-qv-local/quantized_video/quantization.json',root/'tribev2-balanced-qv-local/best.ckpt',Path(__file__),root/'backend/neuroloop/tsam.py',root/'backend/neuroloop/kragel.py',root/'backend/neuroloop/response.py',root/'backend/neuroloop/schemas.py']
    files += sorted((root/'data/geometry').glob('*.gii.gz'))
    files += sorted((root/'models/brain_readouts/kragel2015/source').glob('*.hdr'))
    files += sorted((root/'models/brain_readouts/kragel2015/source').glob('*.img'))
    h=hashlib.sha256()
    for p in files:
        if p.exists(): h.update(p.read_bytes())
    import importlib.metadata
    for package in ['torch','torchvision','transformers','numpy','pandas','pillow','moviepy','neuralset','neuraltrain','bitsandbytes','accelerate','faster-whisper','spacy','en-core-web-lg']:
        try: version=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: version='missing'
        h.update((package+'=='+version).encode())
    h.update(('platform='+platform.system()+'-'+platform.machine()).encode())
    return 'tribe-local-int8-nf4-'+h.hexdigest()[:16]

def _transcribe(path: Path) -> list[dict]:
    from faster_whisper import WhisperModel
    folder=settings().root/'models/preprocessing/faster-whisper-small'
    if not (folder/'model.bin').is_file():
        raise RuntimeError('Local speech transcription is not configured. Install the approved speech-preprocessing model or supply timed words. Speech must not be silently omitted.')
    asr=WhisperModel(str(folder),device='cpu',compute_type='int8',cpu_threads=6,local_files_only=True)
    segments,info=asr.transcribe(str(path),beam_size=5,word_timestamps=True,vad_filter=True,condition_on_previous_text=False)
    if info.language!='en':
        raise ValueError('This initial language pipeline supports English. Other languages require an explicitly validated profile.')
    words=[]
    for segment in segments:
        for w in segment.words or []:
            if w.end>w.start and w.word.strip(): words.append({'text':w.word.strip(),'start':w.start,'end':w.end})
    del asr; gc.collect()
    return words

def evaluate(path: Path,kind: str,details: dict,config: dict,output: Path,on_progress=lambda stage:None) -> dict:
    """Reclaim all encoder allocations between candidates via an owned child.

    The enclosing run's Windows job and timeout also own this child and FFmpeg.
    Only a successful child may publish evidence to the controller.
    """
    root=settings().root.resolve();path=path.resolve();output=output.resolve()
    if not path.is_relative_to(root/'data') or not path.is_file():
        raise ValueError('Input is not a managed media asset')
    if not output.is_relative_to(root/'data'):
        raise ValueError('Invalid result directory')
    output.mkdir(parents=True,exist_ok=True)
    payload=output/'evaluation-request.json'
    atomic_json(payload,{'path':str(path),'kind':kind,'details':details,'config':config,'output':str(output)})
    process=None
    try:
        with (output/'process.log').open('w',encoding='utf-8') as errors:
            process=subprocess.Popen([sys.executable,str(root/'scripts/evaluation_entry.py'),str(payload)],cwd=root,
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            for line in process.stdout:
                if line.startswith('NEUROLOOP_STAGE:'):
                    on_progress(json.loads(line[len('NEUROLOOP_STAGE:'):]))
            code=process.wait()
        if code:
            failure=output/'process-error.json'
            reason=json.loads(failure.read_text(encoding='utf-8'))['error'] if failure.is_file() else f'Evaluation process exited with code {code}; inspect process.log'
            raise RuntimeError(reason)
        return json.loads((output/'evidence.json').read_text(encoding='utf-8'))
    finally:
        if process is not None and process.poll() is None:
            process.kill();process.wait()
        if process is not None and process.stdout is not None:process.stdout.close()
        payload.unlink(missing_ok=True)

def _evaluate_in_process(path: Path,kind: str,details: dict,config: dict,output: Path,on_progress=lambda stage:None) -> dict:
    global _model
    from .hardware import require_inference_headroom
    preflight=require_inference_headroom()
    import numpy as np
    import pandas as pd
    import torch
    from .device import resolve_device
    from neuralset.events.utils import standardize_events
    from neuralset.events.transforms import AddText,AddSentenceToWords,AddContextToWords,RemoveMissing
    root=settings().root.resolve(); path=path.resolve()
    if not path.is_relative_to(root/'data') or not path.is_file(): raise ValueError('Input is not a managed media asset')
    if not output.resolve().is_relative_to(root/'data'): raise ValueError('Invalid result directory')
    output.mkdir(parents=True,exist_ok=True)
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'; os.environ['TOKENIZERS_PARALLELISM']='false'
    device=resolve_device()
    if device == 'cuda':
        # Bound allocator pressure on a laptop sharing its GPU with the desktop.
        # This is not a remedy for a kernel/driver fault; OOM remains a reported failure.
        torch.cuda.set_per_process_memory_fraction(0.75)
        torch.cuda.reset_peak_memory_stats()
    torch.set_num_threads(6)
    started=time.monotonic(); duration=float(details.get('duration') or config.get('presentation_seconds',8))
    words=list(config.get('transcript') or details.get('transcript') or []); transcript_source='provided timed words' if words else 'none'
    adaptation=None; original_kind=kind
    if kind=='image':
        if not config.get('allow_static_presentation'): raise ValueError('Static-image TRIBE presentation requires explicit experimental-mode permission')
        on_progress('Rendering standardized image presentation')
        path=static_presentation(path,output/'presentation.mp4',int(duration)); kind='video'
        adaptation='Repeated-frame presentation; not a validated thumbnail-preference measurement.'
    if kind=='text':
        if not words: raise ValueError('Text analysis requires a timed-word transcript. The service will not invent reading speed or send private text to external TTS.')
        duration=max(float(w['end']) for w in words)
        adaptation='Provided timed-text presentation; not a measurement of an individual reader.'
    rows=[]; common={'timeline':'asset','subject':'default'}
    if kind=='video': rows.append({'type':'Video','filepath':str(path),'start':0.0,'duration':duration,**common})
    if kind=='audio' or (kind=='video' and details.get('has_audio') and original_kind!='image'):
        audio=output/'audio-16k.wav'; on_progress('Decoding audio')
        execute(['-y','-i',str(path),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(audio)])
        rows.append({'type':'Audio','filepath':str(audio),'start':0.0,'duration':duration,**common})
        if not words and not config.get('no_speech'):
            on_progress('Transcribing spoken words locally')
            words=_transcribe(audio); transcript_source='faster-whisper-small/local-CPU-int8'
    for word in words:
        start=float(word['start']); end=float(word['end'])
        if not 0<=start<end<=duration+0.1: raise ValueError('Timed word is outside the source duration')
        rows.append({'type':'Word','text':word['text'],'start':start,'duration':end-start,'language':'english','sequence_id':0,**common})
    if not rows: raise ValueError('No valid stimulus events were produced')
    events=standardize_events(pd.DataFrame(rows))
    if words:
        import spacy
        if not spacy.util.is_package('en_core_web_lg'):
            raise RuntimeError('Pinned English preprocessing model is missing. Install the model runtime lock before inference; runtime downloads are prohibited.')
        on_progress('Preparing timed language events locally')
        for transform in [AddText(),AddSentenceToWords(max_unmatched_ratio=0.05),AddContextToWords(sentence_only=False,max_context_len=1024,split_field=''),RemoveMissing()]: events=transform(events)
        events=standardize_events(events)
    if _model is None:
        on_progress('Loading frozen TRIBE and local feature encoders')
        if str(root) not in sys.path: sys.path.insert(0,str(root))
        from models.load_local_tribe import load_local_tribe
        _model=load_local_tribe(device)
        _model.data.batch_size=1; _model.data.num_workers=0
    on_progress('Predicting cortical responses')
    predictions,segments=_model.predict(events=events,verbose=False)
    validate_response(predictions)
    predictions=predictions.astype(np.float32)
    atomic_numpy(output/'prediction.npy',predictions)
    times=[float(x.start) for x in segments]
    atomic_json(output/'segments.json',[{'start':float(x.start),'duration':float(x.duration)} for x in segments])
    tribe_profile = profile_id()
    geometry_files = sorted((root/'data/geometry').glob('*.gii.gz'))
    geometry_manifest = {path.name: _digest(path) for path in geometry_files}
    geometry_hash = hashlib.sha256(json.dumps(geometry_manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    evidence=summarize(predictions,times)
    evidence.update({'evaluator':'TRIBE v2','profile':tribe_profile,'kind':'model_predicted_cortical_response','device':device,'segment_durations':[float(x.duration) for x in segments],'source_duration':duration,'modalities':sorted(events.type.unique().tolist()),'transcript_source':transcript_source,'transcript_words':len(words),'input_adaptation':adaptation,'seconds':time.monotonic()-started,'peak_cuda_bytes':torch.cuda.max_memory_allocated() if device == 'cuda' else None,'time_note':'Official segment timestamps retained. TRIBE handles the hemodynamic offset; no extra time shift is applied.','quantization':'Original TRIBE brain checkpoint; locally quantized INT8 video and NF4 base text encoders.','limitations':['Predicted average cortical response, not an individual brain scan.','Not purchase intent, CTR, thoughts, or a calibrated emotion probability.','Quantized end-to-end neuroscience accuracy has not been established.'],'provenance':{'contract_version':'response-provenance/v1','model':{'name':'TRIBE v2','version':tribe_profile},'checkpoint':{'sha256':_digest(root/'tribev2-balanced-qv-local/best.ckpt'),'version':'best.ckpt'},'preprocessing':{'version':'TRIBE official event timeline; profile-bound','sha256':tribe_profile},'geometry':{'version':'fsaverage5-left-right-v1','sha256':geometry_hash,'files':geometry_manifest},'projection':{'version':'not_applicable/tribe-cortical-output-v1','sha256':None,'meaning':'TRIBE cortical output is not a volume projection'},'time_axis':{'version':'normalized-interval-axis/v1','source_duration':duration,'segments':[{'start':float(x.start),'duration':float(x.duration)} for x in segments]}},'emotion_decoder':{'status':'experimental' if config.get('include_kragel') else 'not_requested','reason':'Kragel pattern expression is model-to-model experimental evidence, not calibrated human emotion.'}})
    evidence['hardware_preflight']=preflight
    if config.get('include_tsam'):
        if not config.get('tsam_research_acknowledged'):
            raise ValueError('TSAM research-use acknowledgement is required')
        if original_kind=='video' and details.get('has_audio'):
            on_progress('Running independent TSAM audiovisual readout on CPU')
            try:
                from .tsam import predict_video
                evidence['tsam']=predict_video(path,duration,output)
            except Exception as exc:
                evidence['tsam']={'status':'failed','reason':str(exc)[:500]}
        else:
            evidence['tsam']={'status':'not_applicable','reason':'Requires an original video with audio.'}
    if config.get('include_kragel'):
        on_progress('Computing experimental Kragel emotion-pattern expression')
        try:
            from .kragel import decode
            evidence['kragel']=decode(predictions,times,[float(x.duration) for x in segments],duration)
        except Exception as exc:
            evidence['kragel']={'status':'failed','reason':str(exc)[:500]}
    if any(value.get('status') == 'experimental' for value in (evidence.get('tsam'), evidence.get('kragel')) if isinstance(value, dict)):
        from .response import ensemble
        evidence['response_ensemble']=ensemble(evidence)
    evidence['seconds']=time.monotonic()-started
    atomic_json(output/'evidence.json',evidence)
    return evidence
