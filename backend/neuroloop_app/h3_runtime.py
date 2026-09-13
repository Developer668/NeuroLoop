"""FP8 H3 runtime extracted from the successfully exercised media studio.

Imports and downloads happen only inside create_runtime on first use.
Unsloth support retains its upstream AGPL license in h3_support/.
"""
from types import SimpleNamespace

def create_runtime():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('MiniMax H3 FP8 requires the configured CUDA GPU host')
    if torch.cuda.get_device_properties(0).total_memory < 80 * 1024**3:
        raise RuntimeError('This H3 profile requires at least 80 GiB VRAM; validate a smaller profile before changing this limit')

    from diffusers import ModularPipeline, ComponentsManager, MiniMaxH3Transformer3DModel

    from diffusers.utils.export_utils import encode_video

    from accelerate import init_empty_weights

    from huggingface_hub import hf_hub_download

    from torchao.quantization import quantize_, Float8DynamicActivationFloat8WeightConfig

    from torchao.quantization.granularity import PerRow

    from torchao.quantization.quantize_.common.kernel_preference import KernelPreference

    from pathlib import Path

    from PIL import Image

    import io

    import time

    import json

    import threading

    import gc

    import subprocess

    import imageio_ffmpeg

    H3_MODEL = 'MiniMaxAI/MiniMax-H3'

    H3_REVISION = '42ed227ee7df40d41602854ae760620d6eb651fe'

    H3_FP8_REVISION = '37794083e8693f7b328061d831c104e6351eef5d'

    from .h3_support.diffusion_prequant import _prequant_safe_globals as h3_safe_types, _pin_kernel_preference as h3_pin_kernel
    from .h3_support.video_minimax_h3_adaln import apply_h3_adaln_curve

    torch.serialization.add_safe_globals(h3_safe_types())

    torch.set_num_threads(8)

    class OnDemandModel:
        """Load once when a user job asks for the model, never at notebook startup."""

        def __init__(self, loader):
            self.loader = loader
            self.value = None
            self.error = None
            self.lock = threading.Lock()

        def result(self):
            with self.lock:
                if self.value is None:
                    try:
                        self.value = self.loader()
                        self.error = None
                    except Exception as exc:
                        self.error = exc
                        raise
                return self.value

        def done(self):
            return self.value is not None

        def exception(self):
            return self.error

        def unload(self):
            with self.lock:
                self.value = None
                self.error = None

    h3_progress = {'phase': 'Idle - models load when you generate', 'error': None}

    h3_lock = threading.Lock()

    def load_h3_fp8():
        try:
            h3_progress['phase'] = 'Downloading FP8 transformer'
            path = hf_hub_download('unsloth/MiniMax-H3-FP8', 'MiniMax-H3-FP8.pt', revision=H3_FP8_REVISION)
            checkpoint = torch.load(path, weights_only=True, map_location='cpu', mmap=True)
            meta = checkpoint['metadata']
            if meta.get('scheme') != 'fp8' or meta.get('base_model_id') != H3_MODEL:
                raise ValueError('Checkpoint model/precision mismatch')
            if 'fl2va' not in str(meta.get('base_checkpoint', '')).lower() or meta.get('fp8_granularity') != 'per_row':
                raise ValueError('Expected FL2VA per-row FP8 checkpoint')
            if meta.get('diffusion_convrot'):
                raise ValueError('Unexpected activation rotation')
            state = checkpoint['state_dict']
            for name, weight in state.items():
                act = getattr(weight, 'act_quant_kwargs', None)
                if act is not None and (not getattr(act, 'hp_value_lb', None)):
                    raise ValueError(f'Missing activation floor: {name}')
            h3_pin_kernel(state)
            config = MiniMaxH3Transformer3DModel.load_config(H3_MODEL, subfolder='transformer', revision=H3_REVISION)
            with init_empty_weights():
                transformer = MiniMaxH3Transformer3DModel.from_config(config)
            if not apply_h3_adaln_curve(transformer, meta):
                raise ValueError('Expected pruned H3 transformer')
            transformer.load_state_dict(state, strict=True, assign=True)
            transformer.requires_grad_(False).eval().to('cuda')
            del checkpoint, state
            gc.collect()
            h3_progress['phase'] = 'Loading shared encoder and VAEs'
            pipeline = ModularPipeline.from_pretrained(H3_MODEL, revision=H3_REVISION, workflow='fl2va')
            pipeline.update_components(transformer=transformer)
            pipeline.load_components(names=['text_encoder', 'tokenizer', 'processor', 'vae', 'scheduler', 'audio_scheduler', 'audio_vae'], dtype=torch.bfloat16, low_cpu_mem_usage=True)
            encoder = pipeline.text_encoder
            encoder.requires_grad_(False).eval()
            config_fp8 = Float8DynamicActivationFloat8WeightConfig(granularity=PerRow(), activation_value_lb=1e-12, kernel_preference=KernelPreference.TORCH)
            for index, layer in enumerate(encoder.model.language_model.layers):
                h3_progress['phase'] = f'Converting text encoder to FP8: layer {index + 1}/64'
                quantize_(layer, config_fp8, filter_fn=lambda m, n: isinstance(m, torch.nn.Linear) and m.weight.dtype == torch.bfloat16 and (m.in_features % 16 == 0) and (m.out_features % 16 == 0))
                gc.collect()
            h3_progress['phase'] = 'Placing FP8 pipeline on GPU'
            move_h3_module(encoder, 'cuda')
            pipeline.vae.to('cuda')
            pipeline.vae.enable_tiling()
            pipeline.audio_vae.to('cuda')
            h3_progress.update(phase='Ready (FP8)', error=None, transformer_fp8_layers=sum((type(m.weight).__name__ == 'Float8Tensor' for m in transformer.modules() if isinstance(m, torch.nn.Linear))), text_fp8_layers=sum((type(m.weight).__name__ == 'Float8Tensor' for m in encoder.modules() if isinstance(m, torch.nn.Linear))))
            return pipeline
        except Exception as exc:
            h3_progress.update(phase='FP8 setup failed', error=f'{type(exc).__name__}: {exc}')
            raise

    h3_load_future = OnDemandModel(load_h3_fp8)

    from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3ImageReference, MiniMaxH3VideoReference, MiniMaxH3AudioReference

    import hashlib

    import av

    def load_h3_references():
        try:
            base = h3_load_future.result()
            h3_progress['phase'] = 'Downloading FP8 omni-reference transformer'
            path = hf_hub_download('unsloth/MiniMax-H3-FP8', 'MiniMax-H3-Ref2VA-FP8.pt', revision=H3_FP8_REVISION)
            checkpoint = torch.load(path, weights_only=True, map_location='cpu', mmap=True)
            meta = checkpoint['metadata']
            if meta.get('scheme') != 'fp8' or meta.get('base_model_id') != H3_MODEL or 'ref2va' not in str(meta.get('base_checkpoint', '')).lower():
                raise ValueError('Wrong FP8 checkpoint for omni-reference generation')
            if meta.get('fp8_granularity') != 'per_row' or meta.get('diffusion_convrot'):
                raise ValueError('Unsupported FP8 scaling or rotation')
            for weight in checkpoint['state_dict'].values():
                act = getattr(weight, 'act_quant_kwargs', None)
                if act is not None and (not getattr(act, 'hp_value_lb', None)):
                    raise ValueError('Missing FP8 activation floor')
            h3_pin_kernel(checkpoint['state_dict'])
            config = MiniMaxH3Transformer3DModel.load_config(H3_MODEL, subfolder='transformer_ref', revision=H3_REVISION)
            with init_empty_weights():
                transformer = MiniMaxH3Transformer3DModel.from_config(config)
            if not apply_h3_adaln_curve(transformer, meta):
                raise ValueError('Expected the pruned reference transformer')
            transformer.load_state_dict(checkpoint['state_dict'], strict=True, assign=True)
            del checkpoint
            gc.collect()
            h3_progress['phase'] = 'Activating FP8 omni-reference mode'
            move_h3_module(base.transformer, 'cpu')
            torch.cuda.empty_cache()
            transformer.requires_grad_(False).eval().to('cuda')
            reference_pipeline = ModularPipeline.from_pretrained(H3_MODEL, revision=H3_REVISION, workflow='ref2va')
            shared = {name: component for name, component in base.components.items() if name != 'transformer'}
            reference_pipeline.update_components(**shared, transformer_ref=transformer, reference_image_short_edge=768)
            h3_progress.update(phase='Ready (FP8 omni-reference)', error=None)
            return reference_pipeline
        except Exception as exc:
            h3_progress.update(phase='Omni-reference setup failed', error=f'{type(exc).__name__}: {exc}')
            raise

    h3_ref_future = OnDemandModel(load_h3_references)

    def move_h3_module(module, device):
        target = torch.device(device)
        for child in module.modules():
            for name, parameter in list(child._parameters.items()):
                if parameter is None or parameter.device == target:
                    continue
                if hasattr(parameter, '_apply_fn_to_data'):
                    moved = parameter._apply_fn_to_data(lambda tensor: tensor.to(target))
                else:
                    moved = parameter.to(target)
                child._parameters[name] = torch.nn.Parameter(moved, requires_grad=parameter.requires_grad)
            for name, buffer in list(child._buffers.items()):
                if buffer is not None and buffer.device != target:
                    child._buffers[name] = buffer.to(target)
        return module

    def decode_references(paths):
        image_ext = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        video_ext = {'.mp4', '.mov', '.webm', '.mkv'}
        audio_ext = {'.wav', '.mp3', '.m4a', '.flac', '.ogg'}
        kinds = []
        for path in paths:
            suffix = Path(path).suffix.lower()
            kind = 'image' if suffix in image_ext else 'video' if suffix in video_ext else 'audio' if suffix in audio_ext else None
            if kind is None:
                raise ValueError(f'Unsupported reference: {Path(path).name}')
            kinds.append(kind)
        counts = {kind: kinds.count(kind) for kind in ['image', 'video', 'audio']}
        if len(paths) > 12 or counts['image'] > 9 or counts['video'] > 3 or (counts['audio'] > 3):
            raise ValueError('Use at most 9 images, 3 videos, 3 audio clips, and 12 files in total.')
        if counts['audio'] and (not (counts['image'] or counts['video'])):
            raise ValueError('Audio references also need at least one image or video.')
        refs = []
        summary = []
        counters = {'image': 0, 'video': 0, 'audio': 0}
        total_video_seconds = 0.0
        for path, kind in zip(paths, kinds):
            path = Path(path)
            duration = None
            if kind == 'image':
                ref = MiniMaxH3ImageReference.from_file(path)
            else:
                with av.open(str(path)) as container:
                    if container.duration is None:
                        raise ValueError(f'Cannot determine clip duration: {path.name}')
                    duration = container.duration / 1000000.0
                if not 1.99 <= duration <= 15.05:
                    raise ValueError(f'{path.name}: reference clips must be 2-15 seconds; got {duration:.2f}.')
                if kind == 'video':
                    total_video_seconds += duration
                    if total_video_seconds > 15.05:
                        raise ValueError('Reference videos must total at most 15 seconds.')
                    normalized = path.with_name(path.stem + '-reference-768.mp4')
                    if not normalized.exists():
                        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', str(path), '-vf', 'scale=768:768:force_original_aspect_ratio=decrease:force_divisible_by=2,fps=24', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-c:a', 'aac', str(normalized)], check=True, capture_output=True)
                    ref = MiniMaxH3VideoReference.from_file(normalized)
                else:
                    ref = MiniMaxH3AudioReference.from_file(path)
            refs.append(ref)
            counters[kind] += 1
            prefix = {'image': 'Picture', 'video': 'Video', 'audio': 'Audio'}[kind]
            summary.append({'label': f'{prefix} {counters[kind]}', 'file': path.name, 'type': kind, 'seconds': duration})
        return (refs, summary)

    def release_studio_gpu():
        """Call while holding h3_lock; keeps CPU weights for the next interactive job."""
        seen = set()
        for future in (h3_load_future, h3_ref_future):
            if not future.done() or future.exception() is not None:
                continue
            for component in future.result().components.values():
                if isinstance(component, torch.nn.Module) and id(component) not in seen:
                    move_h3_module(component, 'cpu')
                    seen.add(id(component))
        gc.collect()
        torch.cuda.empty_cache()

    h3_workflow_pipelines = {}

    def generate_h3(prompt, width=1024, height=672, frames=345, steps=4, seed=11, reference_paths=None, output_dir=None, cancelled=lambda: False):
        if not prompt.strip() or width % 32 or height % 32:
            raise ValueError('Enter a prompt and dimensions divisible by 32.')
        with h3_lock:
            started = time.monotonic()
            h3_progress.update(phase='Generating your clip', error=None)
            try:
                paths = list(reference_paths or [])
                references, reference_summary = decode_references(paths)
                base = h3_load_future.result()
                reference_pipeline = h3_ref_future.result() if references else None
                kwargs = {}
                if references:
                    move_h3_module(base.transformer, 'cpu')
                    torch.cuda.empty_cache()
                    move_h3_module(reference_pipeline.transformer_ref, 'cuda')
                    pipeline = reference_pipeline
                    kwargs['references'] = references
                    active_transformer = pipeline.transformer_ref
                else:
                    if h3_ref_future.done():
                        move_h3_module(h3_ref_future.result().transformer_ref, 'cpu')
                    torch.cuda.empty_cache()
                    move_h3_module(base.transformer, 'cuda')
                    if 't2va' not in h3_workflow_pipelines:
                        text = ModularPipeline.from_pretrained(H3_MODEL, revision=H3_REVISION, workflow='t2va')
                        text.update_components(**base.components)
                        h3_workflow_pipelines['t2va'] = text
                    pipeline = h3_workflow_pipelines['t2va']
                    active_transformer = base.transformer
                pipeline.vae.to('cuda')
                pipeline.audio_vae.to('cuda')
                move_h3_module(pipeline.text_encoder, 'cuda')
                from accelerate.hooks import AlignDevicesHook, add_hook_to_module
                if not hasattr(pipeline.text_encoder, '_hf_hook'):
                    add_hook_to_module(pipeline.text_encoder, AlignDevicesHook(execution_device=torch.device('cuda'), io_same_device=True))
                memory_hook = None
                if width * height > 1032192 or len(references) >= 3:

                    def release_conditioner(module, args):
                        if next(pipeline.text_encoder.parameters()).device.type == 'cuda':
                            move_h3_module(pipeline.text_encoder, 'cpu')
                            torch.cuda.empty_cache()
                    memory_hook = active_transformer.register_forward_pre_hook(release_conditioner)
                h3_progress['phase'] = 'Generating video'
                inference_started = time.monotonic()
                def check_step(module, args):
                    if cancelled():
                        from .notebook import ModelCancelled
                        raise ModelCancelled('H3 cancelled')
                cancel_hook = active_transformer.register_forward_pre_hook(check_step)
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    result = pipeline(prompt=prompt, width=width, height=height, num_frames=frames, num_inference_steps=steps, generator=torch.Generator().manual_seed(seed), output=['videos', 'audio', 'sampling_rate'], **kwargs)
                if memory_hook is not None:
                    memory_hook.remove()
                inference_seconds = time.monotonic() - inference_started
                h3_progress['phase'] = 'Encoding MP4'
                target = Path(output_dir) / f'cat-fp8-{time.time_ns()}.mp4'
                encode_video(result['videos'][0], fps=24, output_path=str(target), audio=result['audio'][0], audio_sample_rate=result['sampling_rate'])
                native_frames = len(result['videos'][0])
                if frames == 345:
                    native_target = target.with_name(target.stem + '-native.mp4')
                    target.rename(native_target)
                    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', str(native_target), '-vf', 'setpts=(360/345)*PTS,fps=24', '-af', 'atempo=0.9583333333,apad', '-t', '15', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(target)], check=True, capture_output=True)
                metadata = dict(model=H3_MODEL, fp8_checkpoint_revision=H3_FP8_REVISION, precision='FP8 transformer and text encoder linear layers; mixed-precision VAEs', prompt=prompt, width=width, height=height, native_frames=native_frames, workflow='ref2va' if references else 't2va', references=reference_summary, duration=15.0 if frames == 345 else native_frames / 24, retimed=frames == 345, steps=steps, seed=seed, inference_seconds=round(inference_seconds, 2), load_and_prepare_seconds=round(inference_started - started, 2), seconds=round(time.monotonic() - started, 2), peak_gpu_gb=round(torch.cuda.max_memory_allocated() / 1000000000.0, 2))
                target.with_suffix('.json').write_text(json.dumps(metadata, indent=2))
                h3_progress.update(phase='Ready (FP8 omni-reference)' if references else 'Ready (FP8 text)', last_output=str(target))
                return (str(target), metadata)
            except Exception as exc:
                if 'memory_hook' in locals() and memory_hook is not None:
                    memory_hook.remove()
                h3_progress.update(phase='Generation failed', error=f'{type(exc).__name__}: {exc}')
                raise
            finally:
                if 'cancel_hook' in locals():
                    cancel_hook.remove()
                release_studio_gpu()
                if not h3_progress.get('error'):
                    h3_progress['phase'] = 'Complete - GPU weights offloaded; idle'

    def unload():
        release_studio_gpu()
        h3_workflow_pipelines.clear()
        h3_ref_future.unload()
        h3_load_future.unload()
        gc.collect()
        torch.cuda.empty_cache()

    return SimpleNamespace(generate=generate_h3, park=release_studio_gpu, unload=unload, progress=h3_progress)
