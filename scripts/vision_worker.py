"""Run the real W&B vision evaluator with local speech evidence."""
import time
from pathlib import Path
from neuroloop_app.config import Settings
from neuroloop_app.notebook import ModelRegistry, NotebookWorker
from neuroloop_app.vision_adapter import VisionAdapter


def main():
    settings = Settings()
    if not settings.audio_transcription_model_path:
        raise SystemExit("Configure NEUROLOOP_AUDIO_TRANSCRIPTION_MODEL_PATH with a local Faster Whisper checkpoint")
    adapter = VisionAdapter(settings)
    registry = ModelRegistry()
    registry.register_evaluator("vision", provenance=adapter.provenance, loader=lambda: adapter)
    import os
    api_port = int(os.environ.get("NEUROLOOP_API_PORT", "8010"))
    worker = NotebookWorker(registry, settings=settings, api_url=f"http://127.0.0.1:{api_port}",
                            worker_id="local-vision-audio", cache_dir=Path("data/v2/vision-worker"))
    worker.start()
    try:
        while worker.thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        worker.stop()
        worker.thread.join()


if __name__ == "__main__":
    main()
