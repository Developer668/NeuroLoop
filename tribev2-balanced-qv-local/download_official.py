from huggingface_hub import snapshot_download
from pathlib import Path
root=Path('tribev2-balanced-qv-local')
for repo,rev,dest,files in [
 ('facebook/tribev2','f894e783020944dcd96e5568550afe2aa9743f9f',root,['best.ckpt','config.yaml','LICENSE']),
 ('facebook/vjepa2-vitg-fpc64-256','875c192b7b704b87d1e1d99345769632dd5f739a',root/'source_video',['model.safetensors','config.json','video_preprocessor_config.json','README.md'])]:
 print('Downloading official source:',repo,flush=True)
 snapshot_download(repo,revision=rev,local_dir=str(dest),allow_patterns=files,token=False)
