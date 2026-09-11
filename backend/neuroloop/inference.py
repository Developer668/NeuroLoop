"""Local inference boundary. Uses downloaded, frozen weights and structured media events.

Only the dedicated worker calls this module. The API process never loads a GPU model.
There is no generated Python execution and no model-server shell command.
"""
from __future__ import annotations
import copy, gc, hashlib, json, os, shutil, sys, time, subprocess
import platform
from dataclasses import replace
from pathlib import Path
from .persistence import atomic_json, atomic_numpy, publish_artifact_manifest, ARTIFACT_MANIFEST_NAME
from .config import settings
from .media import execute, static_presentation
from .readout import summarize, validate_response

_model=None
_model_profile=None

PROFILE_VERSION = 'inference-profile/v2'
_PROFILE_DIRECTORIES = (
    'data/geometry',
    'models/audio/w2v-bert-2.0',
    'models/brain_readouts/kragel2015/source',
    'models/emotion/tsam',
    'models/preprocessing/faster-whisper-small',
    'models/text/llama-3.2-3b-unsloth-q4',
    'models/vision/dinov2-large',
    'tribev2-balanced-qv-local/quantized_video',
    'infrastructure/vendor/tribev2',
    'infrastructure/vendor/moviepy',
)
_PROFILE_FILES = (
    'models/load_local_tribe.py',
    'tribev2-balanced-qv-local/load_quantized_tribev2.py',
    'tribev2-balanced-qv-local/config.yaml',
    'tribev2-balanced-qv-local/best.ckpt',
    'scripts/evaluation_entry.py',
    'infrastructure/runtime/model.lock',
    'infrastructure/runtime/model-macos.lock',
    'backend/neuroloop/inference.py',
    'backend/neuroloop/tsam.py',
    'backend/neuroloop/kragel.py',
    'backend/neuroloop/response.py',
    'backend/neuroloop/readout.py',
    'backend/neuroloop/schemas.py',
    'backend/neuroloop/media.py',
    'backend/neuroloop/checkpoints.py',
    'backend/neuroloop/config.py',
    'backend/neuroloop/device.py',
    'backend/neuroloop/hardware.py',
)
_PROFILE_IGNORED_PARTS = {'.cache', '__pycache__'}
_PROFILE_IGNORED_NAMES = {'.DS_Store'}
_profile_digest_cache = {}
_profile_snapshot_cache = None


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def _stat_record(path: Path) -> dict:
    stat = path.stat()
    return {
        'device': int(stat.st_dev),
        'inode': int(stat.st_ino),
        'size': int(stat.st_size),
        'mtime_ns': int(stat.st_mtime_ns),
        'ctime_ns': int(stat.st_ctime_ns),
        'mode': int(stat.st_mode),
    }


def _collect_profile_inputs(root: Path) -> tuple[dict[str, Path], dict[str, dict]]:
    """Discover evaluator files without reading their contents."""
    candidates = {}
    layout = {}
    for relative in (*_PROFILE_FILES, *_PROFILE_DIRECTORIES):
        path = root / relative
        if path.is_file():
            candidates[relative] = path
            layout[relative] = {'kind': 'file', 'files': [relative]}
            continue
        if not path.is_dir():
            layout[relative] = {'kind': 'missing', 'files': []}
            continue
        names = []
        for child in sorted(path.rglob('*'), key=lambda item: item.as_posix()):
            if not child.is_file() or child.name in _PROFILE_IGNORED_NAMES:
                continue
            if any(part in _PROFILE_IGNORED_PARTS for part in child.relative_to(path).parts):
                continue
            name = child.relative_to(root).as_posix()
            candidates[name] = child
            names.append(name)
        layout[relative] = {'kind': 'directory', 'files': names}
    return candidates, layout


def _package_versions() -> dict[str, str]:
    import importlib.metadata
    packages = {}
    for package in ['torch', 'torchvision', 'transformers', 'numpy', 'pandas', 'pillow', 'moviepy', 'neuralset', 'neuraltrain', 'bitsandbytes', 'accelerate', 'faster-whisper', 'spacy', 'en-core-web-lg']:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = 'missing'
    return packages


def _runtime_platform() -> dict[str, str]:
    return {
        'system': platform.system(),
        'machine': platform.machine(),
        'python': platform.python_version(),
        'implementation': platform.python_implementation(),
    }


def _build_profile_snapshot(root: Path) -> dict:
    candidates, layout = _collect_profile_inputs(root)
    stats = {}
    digests = {}
    for relative, path in candidates.items():
        record = _stat_record(path)
        cache_key = str(path)
        cached = _profile_digest_cache.get(cache_key)
        if cached and cached[0] == record:
            digest = cached[1]
        else:
            digest = _digest(path)
            if digest is None:
                raise RuntimeError(f'Evaluator input changed while being profiled: {relative}')
            if _stat_record(path) != record:
                raise RuntimeError(f'Evaluator input changed while being profiled: {relative}')
            _profile_digest_cache[cache_key] = (record, digest)
        stats[relative] = record
        digests[relative] = digest

    files = {}
    for relative in (*_PROFILE_FILES, *_PROFILE_DIRECTORIES):
        entry = layout[relative]
        files[relative] = None if entry['kind'] == 'missing' else {
            name: digests[name] for name in entry['files'] if name in digests
        }
    manifest = {
        'version': PROFILE_VERSION,
        'files': files,
        'packages': _package_versions(),
        'platform': _runtime_platform(),
    }
    return {
        'root': str(root),
        'layout': layout,
        'stats': stats,
        'manifest': manifest,
    }


def _snapshot_matches(snapshot: dict, root: Path) -> bool:
    if not isinstance(snapshot, dict) or snapshot.get('root') != str(root):
        return False
    candidates, layout = _collect_profile_inputs(root)
    if snapshot.get('layout') != layout:
        return False
    stats = snapshot.get('stats')
    if not isinstance(stats, dict) or set(stats) != set(candidates):
        return False
    try:
        if any(_stat_record(path) != stats[relative] for relative, path in candidates.items()):
            return False
    except OSError:
        return False
    manifest = snapshot.get('manifest')
    return isinstance(manifest, dict) and manifest.get('packages') == _package_versions() and manifest.get('platform') == _runtime_platform()


def profile_snapshot(previous: dict | None = None) -> dict:
    """Return a stat-validated content hash snapshot.

    Large files are streamed once per process and reused only while their file
    identity, size, timestamps, mode, directory layout, and runtime versions
    remain unchanged. A replacement or mutation invalidates the old digest.
    """
    global _profile_snapshot_cache
    root = settings().root.resolve()
    for candidate in (previous, _profile_snapshot_cache):
        if candidate is not None and _snapshot_matches(candidate, root):
            _profile_snapshot_cache = copy.deepcopy(candidate)
            return copy.deepcopy(_profile_snapshot_cache)
    snapshot = _build_profile_snapshot(root)
    _profile_snapshot_cache = snapshot
    return copy.deepcopy(snapshot)


def profile_manifest() -> dict:
    """Return the immutable inputs and runtime versions behind one evaluator."""
    return profile_snapshot()['manifest']


def profile_id(manifest: dict | None = None) -> str:
    """Return a content-addressed evaluator identity.

    The snapshot is stat-validated and its file digests are reused while the
    evaluator inputs remain unchanged, so large weights are not re-read for
    every cache lookup.
    """
    if manifest is None:
        manifest = profile_manifest()
    elif 'manifest' in manifest and 'stats' in manifest:
        manifest = profile_snapshot(manifest)['manifest']
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return 'tribe-local-int8-nf4-' + hashlib.sha256(encoded).hexdigest()[:16]


def _profile_hash(snapshot: dict, relative: str) -> str | None:
    manifest = snapshot.get('manifest', snapshot)
    for value in manifest.get('files', {}).values():
        if isinstance(value, dict) and relative in value:
            return value[relative]
    return None

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

def _release_model(model, torch, device: str) -> None:
    """Release stage-local model storage before a secondary readout loads."""
    global _model
    if _model is model:
        _model = None
    del model
    gc.collect()
    if device == 'mps':
        empty_cache = getattr(getattr(torch, 'mps', None), 'empty_cache', None)
        if callable(empty_cache):
            empty_cache()


def _cleanup_evaluation_intermediates(output: Path, payload: Path | None = None) -> None:
    """Remove evaluator-owned scratch files without touching published evidence."""
    for name in ('audio-16k.wav', 'presentation.mp4'):
        (output / name).unlink(missing_ok=True)
    shutil.rmtree(output / 'tsam', ignore_errors=True)
    if payload is not None:
        payload.unlink(missing_ok=True)

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
    from .execution_guard import require_execution_enabled
    require_execution_enabled()
    output.mkdir(parents=True,exist_ok=True)
    if (output / ARTIFACT_MANIFEST_NAME).is_file():
        raise RuntimeError('Finalized evaluation artifacts are immutable; reuse the validated cache entry')
    payload=output/'evaluation-request.json'
    atomic_json(payload,{'path':str(path),'kind':kind,'details':details,'config':config,'output':str(output)})
    process=None
    try:
        with (output/'process.log').open('w',encoding='utf-8') as errors:
            entrypoint = Path(__file__).resolve().parents[2] / 'scripts/evaluation_entry.py'
            process=subprocess.Popen([sys.executable,str(entrypoint),str(payload)],cwd=root,
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
        _cleanup_evaluation_intermediates(output, payload)

def _evaluate_in_process(path: Path,kind: str,details: dict,config: dict,output: Path,on_progress=lambda stage:None) -> dict:
    global _model, _model_profile
    from .execution_guard import require_execution_enabled
    require_execution_enabled()
    import numpy as np
    import pandas as pd
    import torch
    from .device import resolve_device
    from .modality import plan_for_input
    from neuralset.events.utils import standardize_events
    from neuralset.events.transforms import AddText,AddSentenceToWords,AddContextToWords,RemoveMissing
    root=settings().root.resolve(); path=path.resolve()
    if not path.is_relative_to(root/'data') or not path.is_file(): raise ValueError('Input is not a managed media asset')
    if not output.resolve().is_relative_to(root/'data'): raise ValueError('Invalid result directory')
    output.mkdir(parents=True,exist_ok=True)
    if (output / ARTIFACT_MANIFEST_NAME).is_file():
        raise RuntimeError('Finalized evaluation artifacts are immutable; reuse the validated cache entry')
    finalized_snapshot = profile_snapshot(config.get('_profile_snapshot'))
    finalized_profile = profile_id(finalized_snapshot)
    expected_profile = config.get('_expected_profile')
    if expected_profile and expected_profile != finalized_profile:
        raise RuntimeError('Evaluator profile changed before model residency; refusing mixed-profile evaluation')
    checkpoint_hash = _profile_hash(finalized_snapshot, 'tribev2-balanced-qv-local/best.ckpt')
    geometry_files = sorted((root/'data/geometry').glob('*.gii.gz'))
    geometry_manifest = {
        item.name: _profile_hash(finalized_snapshot, 'data/geometry/' + item.name)
        for item in geometry_files
    }
    geometry_hash = hashlib.sha256(json.dumps(geometry_manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    from .hardware import require_inference_headroom
    preflight=require_inference_headroom()
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
    plan=plan_for_input(original_kind,has_audio=bool(details.get('has_audio')),has_timed_text=bool(words),allow_static_presentation=bool(config.get('allow_static_presentation')))
    if transcript_source.startswith('faster-whisper'):
        plan=replace(plan,text_source='local_asr')
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
    if not _snapshot_matches(finalized_snapshot, root):
        raise RuntimeError('Evaluator profile changed before model residency; refusing mixed-profile evaluation')
    if _model is not None and _model_profile != finalized_profile:
        raise RuntimeError('Evaluator profile changed while a model is resident; refusing mixed-profile evaluation')
    if _model is None:
        on_progress('Loading frozen TRIBE and local feature encoders')
        if str(root) not in sys.path: sys.path.insert(0,str(root))
        from models.load_local_tribe import load_local_tribe
        _model=load_local_tribe(device, features_to_use=plan.tribe_features)
        if not _snapshot_matches(finalized_snapshot, root):
            _model = None
            _model_profile = None
            raise RuntimeError('Evaluator profile changed during model residency; refusing mixed-profile evaluation')
        _model_profile = finalized_profile
        _model.data.batch_size=1; _model.data.num_workers=0
    on_progress('Predicting cortical responses')
    model=_model
    with torch.inference_mode():
        predictions,segments=model.predict(events=events,verbose=False)
    validate_response(predictions)
    predictions=np.asarray(predictions,dtype=np.float32)
    atomic_numpy(output/'prediction.npy',predictions)
    times=[float(x.start) for x in segments]
    atomic_json(output/'segments.json',[{'start':float(x.start),'duration':float(x.duration)} for x in segments])
    evidence=summarize(predictions,times)
    evidence.update({'evaluator':'TRIBE v2','profile':tribe_profile,'kind':'model_predicted_cortical_response','device':device,'segment_durations':[float(x.duration) for x in segments],'source_duration':duration,'modalities':sorted(events.type.unique().tolist()),'transcript_source':transcript_source,'transcript_words':len(words),'input_adaptation':adaptation or plan.input_adaptation,'model_selection':plan.as_dict(),'seconds':time.monotonic()-started,'peak_cuda_bytes':torch.cuda.max_memory_allocated() if device == 'cuda' else None,'time_note':'Official segment timestamps retained. TRIBE handles the hemodynamic offset; no extra time shift is applied.','quantization':'Original TRIBE brain checkpoint; locally quantized INT8 video and NF4 base text encoders.','limitations':['Predicted average cortical response, not an individual brain scan.','Not purchase intent, CTR, thoughts, or a calibrated emotion probability.','Quantized end-to-end neuroscience accuracy has not been established.','Reader feeling and reader-specific brain activity are not measured by a text stimulus alone.'],'provenance':{'contract_version':'response-provenance/v1','model':{'name':'TRIBE v2','version':tribe_profile},'checkpoint':{'sha256':_digest(root/'tribev2-balanced-qv-local/best.ckpt'),'version':'best.ckpt'},'preprocessing':{'version':'TRIBE official event timeline; profile-bound','sha256':tribe_profile},'geometry':{'version':'fsaverage5-left-right-v1','sha256':geometry_hash,'files':geometry_manifest},'projection':{'version':'not_applicable/tribe-cortical-output-v1','sha256':None,'meaning':'TRIBE cortical output is not a volume projection'},'time_axis':{'version':'normalized-interval-axis/v1','source_duration':duration,'segments':[{'start':float(x.start),'duration':float(x.duration)} for x in segments]}},'emotion_decoder':{'status':'experimental' if config.get('include_kragel') else 'not_requested','reason':'Kragel pattern expression is model-to-model experimental evidence, not calibrated human emotion.'}})
    _release_model(model,torch,device)
    del model, events, rows, common
    evidence.update({
        'evaluator': 'TRIBE v2',
        'profile': finalized_profile,
        'kind': 'model_predicted_cortical_response',
        'device': device,
        'segment_durations': [float(x.duration) for x in segments],
        'source_duration': duration,
        'modalities': sorted(events.type.unique().tolist()),
        'transcript_source': transcript_source,
        'transcript_words': len(words),
        'input_adaptation': adaptation or plan.input_adaptation,
        'model_selection': plan.as_dict(),
        'seconds': time.monotonic() - started,
        'peak_cuda_bytes': torch.cuda.max_memory_allocated() if device == 'cuda' else None,
        'time_note': 'Official segment timestamps retained. TRIBE handles the hemodynamic offset; no extra time shift is applied.',
        'quantization': 'Original TRIBE brain checkpoint; locally quantized INT8 video and NF4 base text encoders.',
        'limitations': [
            'Predicted average cortical response, not an individual brain scan.',
            'Not purchase intent, CTR, thoughts, or a calibrated emotion probability.',
            'Quantized end-to-end neuroscience accuracy has not been established.',
            'Reader feeling and reader-specific brain activity are not measured by a text stimulus alone.',
        ],
        'provenance': {
            'contract_version': 'response-provenance/v1',
            'model': {'name': 'TRIBE v2', 'version': finalized_profile},
            'checkpoint': {'sha256': checkpoint_hash, 'version': 'best.ckpt'},
            'preprocessing': {'version': 'TRIBE official event timeline; profile-bound', 'sha256': finalized_profile},
            'geometry': {'version': 'fsaverage5-left-right-v1', 'sha256': geometry_hash, 'files': geometry_manifest},
            'projection': {'version': 'not_applicable/tribe-cortical-output-v1', 'sha256': None, 'meaning': 'TRIBE cortical output is not a volume projection'},
            'time_axis': {'version': 'normalized-interval-axis/v1', 'source_duration': duration, 'segments': [{'start': float(x.start), 'duration': float(x.duration)} for x in segments]},
        },
        'emotion_decoder': {
            'status': 'experimental' if config.get('include_kragel') else 'not_requested',
            'reason': 'Kragel pattern expression is model-to-model experimental evidence, not calibrated human emotion.',
        },
    })
    _release_model(model, torch, device)
    del model, events, rows, common
    evidence['hardware_preflight']=preflight
    if config.get('include_tsam'):
        if not config.get('tsam_research_acknowledged'):
            raise ValueError('TSAM research-use acknowledgement is required')
        if original_kind=='video' and details.get('has_audio'):
            on_progress('Running independent TSAM audiovisual readout on CPU')
            try:
                from .tsam import predict_video
                tsam_checkpoint = _profile_hash(finalized_snapshot, 'models/emotion/tsam/weights/tsam_weights.tar')
                evidence['tsam']=predict_video(path,duration,output,checkpoint_hash=tsam_checkpoint)
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
    artifact_context = config.get('_artifact_context')
    if isinstance(artifact_context, dict):
        publish_artifact_manifest(output, cache_key=artifact_context['cache_key'], profile=finalized_profile,
                                  asset_sha256=artifact_context['asset_sha256'], profile_manifest=finalized_snapshot['manifest'])
    return evidence
