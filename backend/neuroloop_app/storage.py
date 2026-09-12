"""Immutable content storage and deterministic media validation.

Only server-generated object keys are accepted. No arbitrary URL fetching.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from .config import Settings
from .domain import uid


class StorageError(ValueError):
    pass


@dataclass
class MediaInfo:
    kind: str
    mime: str
    details: dict


def inspect_media(path: Path, settings: Settings, internal: bool = False) -> MediaInfo:
    with path.open("rb") as header_stream:
        header = header_stream.read(32)
    # Image parsing is a real decoder check, not trust in user extensions/MIME.
    if header.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8")) or (header[:4] == b"RIFF" and header[8:12] == b"WEBP"):
        from PIL import Image
        with Image.open(path) as image:
            width, height = image.size
            if width * height > settings.max_pixels or getattr(image, "n_frames", 1) > 1:
                raise StorageError("Oversized or animated images are not supported")
            mime = Image.MIME.get(image.format, "application/octet-stream")
            image.verify()
        return MediaInfo("image", mime, {"width": width, "height": height})
    if internal and header.startswith(b"PK"):
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if {i.filename for i in entries} != {"values.npy", "times.npy"} or len(entries) != 2:
                raise StorageError("Cortical archive contains unexpected entries")
            if sum(i.file_size for i in entries) > 100 * 1024 * 1024:
                raise StorageError("Cortical archive expansion limit exceeded")
        import numpy as np
        with np.load(path, allow_pickle=False) as data:
            if set(data.files) != {"values", "times"}:
                raise StorageError("Cortical NPZ must contain only values and times")
            values, times = data["values"], data["times"]
            if values.ndim != 2 or values.shape[1] != 20484 or not 1 <= values.shape[0] <= 600:
                raise StorageError("Expected frames x 20484 fsaverage5 cortical values")
            if times.shape != (len(values),) or not np.isfinite(values).all() or not np.isfinite(times).all():
                raise StorageError("Cortical artifact contains invalid numerical values")
            if (np.diff(times) < 0).any():
                raise StorageError("Cortical timestamps must be monotonic")
            info = {"frames": len(values), "vertices": 20484, "range": [float(values.min()), float(values.max())]}
        return MediaInfo("cortical", "application/octet-stream", info)
    if header.startswith(b"%PDF-"):
        return MediaInfo("document", "application/pdf", {"extraction_status": "NOT_RUN"})
    if header.startswith(b"PK"):
        with zipfile.ZipFile(path) as archive:
            total = sum(i.file_size for i in archive.infolist())
            if total > 40 * 1024 * 1024 or len(archive.infolist()) > 1000:
                raise StorageError("Document archive expansion limit exceeded")
            if "word/document.xml" not in archive.namelist():
                raise StorageError("Unsupported archive")
        return MediaInfo("document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", {"extraction_status": "NOT_RUN"})
    is_video = b"ftyp" in header or header.startswith(b"\x1aE\xdf\xa3") or header.startswith(b"RIFF")
    if is_video or header.startswith((b"ID3", b"fLaC", b"OggS")):
        try:
            output = subprocess.run([settings.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, timeout=30, check=True)
        except FileNotFoundError as exc:
            raise StorageError("UNAVAILABLE: ffprobe is required to validate video/audio") from exc
        except (subprocess.SubprocessError, OSError) as exc:
            raise StorageError("Media failed ffprobe validation") from exc
        data = json.loads(output.stdout)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = any(s.get("codec_type") == "audio" for s in streams)
        duration = float(data.get("format", {}).get("duration", 0))
        if not 0 < duration <= settings.max_media_seconds or not (video or audio):
            raise StorageError("Unsupported or over-budget media duration")
        details = {"duration_seconds": duration, "has_audio": audio}
        if video:
            width, height = int(video["width"]), int(video["height"])
            if width * height > settings.max_pixels:
                raise StorageError("Video resolution exceeds limits")
            details.update(width=width, height=height, frame_rate=video.get("avg_frame_rate"))
        return MediaInfo("video" if video else "audio", "video/mp4" if video and b"ftyp" in header else "video/webm" if video else "audio/wav", details)
    if path.stat().st_size <= 256 * 1024:
        try:
            content = path.read_text(encoding="utf-8-sig")
            if "\0" in content:
                raise ValueError()
            return MediaInfo("document", "text/plain", {"text": content, "extraction_status": "SUCCEEDED"})
        except (UnicodeError, ValueError):
            pass
    raise StorageError("Unsupported media format. Use PNG/JPEG/WebP, MP4/WebM, audio, PDF, DOCX or UTF-8 text")


def extract_document(path: Path, info: MediaInfo) -> dict:
    if info.mime == "text/plain":
        return info.details
    try:
        if info.mime == "application/pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            if len(reader.pages) > 100:
                raise StorageError("PDF page limit exceeded")
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        elif "wordprocessingml" in info.mime:
            from docx import Document
            text = "\n".join(p.text for p in Document(path).paragraphs)
        else:
            return info.details
        return {"text": text[:24000], "truncated": len(text) > 24000, "extraction_status": "SUCCEEDED" if text.strip() else "INSUFFICIENT_EVIDENCE"}
    except ImportError:
        return {"extraction_status": "NOT_CONFIGURED", "reason": "Install neuroloop[documents] to extract this format"}


class ObjectStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir / "objects"
        self.root.mkdir(parents=True, exist_ok=True)
        self.temp = settings.data_dir / "tmp"
        self.temp.mkdir(parents=True, exist_ok=True)
        self._s3 = None

    def s3(self):
        if self._s3 is None:
            import boto3
            s = self.settings
            if not s.s3_bucket:
                raise StorageError("NOT_CONFIGURED: S3 bucket")
            self._s3 = boto3.client("s3", endpoint_url=s.s3_endpoint or None, region_name=s.s3_region, aws_access_key_id=s.s3_access_key.get_secret_value() or None, aws_secret_access_key=s.s3_secret_key.get_secret_value() or None)
        return self._s3

    def local_path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root.resolve()):
            raise StorageError("Invalid object key")
        return candidate

    def put(self, source: Path, campaign_id: str, asset_id: str) -> tuple[str, str, int]:
        sha = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(block)
        key = f"{campaign_id}/{asset_id}/{sha.hexdigest()}"
        size = source.stat().st_size
        if self.settings.storage == "s3":
            # Conditional write prevents accidental replacement of an immutable key.
            with source.open("rb") as stream:
                self.s3().put_object(Bucket=self.settings.s3_bucket, Key=key, Body=stream, IfNoneMatch="*", Metadata={"sha256": sha.hexdigest()})
        else:
            dest = self.local_path(key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as out, source.open("rb") as inp:
                shutil.copyfileobj(inp, out)
                out.flush()
                os.fsync(out.fileno())
        return key, sha.hexdigest(), size

    def read(self, key: str) -> bytes:
        if self.settings.storage == "s3":
            return self.s3().get_object(Bucket=self.settings.s3_bucket, Key=key)["Body"].read()
        return self.local_path(key).read_bytes()

    def stream(self, key: str):
        if self.settings.storage == "s3":
            body = self.s3().get_object(Bucket=self.settings.s3_bucket, Key=key)["Body"]
            try:
                yield from body.iter_chunks(chunk_size=1024 * 1024)
            finally:
                body.close()
        else:
            with self.local_path(key).open("rb") as stream:
                yield from iter(lambda: stream.read(1024 * 1024), b"")
