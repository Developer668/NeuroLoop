"""Media sandbox boundary checks; unit fixtures never count as neural results."""
from types import SimpleNamespace
import os
from pathlib import Path
import pytest
from neuroloop import media
from neuroloop.media import guarded_inputs, inspect_media, MediaError, FILE_INPUT_OPTIONS


def test_ffmpeg_remote_input_is_rejected_before_process():
    with pytest.raises(MediaError, match='local media'):
        guarded_inputs(['-i', 'http://127.0.0.1/private', '-f', 'null', '-'])


def test_ffmpeg_missing_path_rejected(tmp_path):
    with pytest.raises(MediaError):
        guarded_inputs(['-i', str(tmp_path / 'missing.mp4')])


def test_ffmpeg_discovers_bundled_posix_runtime(monkeypatch, tmp_path):
    binary = tmp_path / '.runtimes/model/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'pinned ffmpeg fixture')
    monkeypatch.delenv('NEUROLOOP_FFMPEG', raising=False)
    monkeypatch.setattr(media, 'settings', lambda: SimpleNamespace(root=tmp_path, model_python=tmp_path / '.runtimes/model/bin/python'))
    monkeypatch.setattr(media.shutil, 'which', lambda _: None)

    assert os.path.samefile(media.ffmpeg(), binary)


def test_ffmpeg_discovers_bundled_windows_runtime_layout(monkeypatch, tmp_path):
    binary = tmp_path / '.runtimes/model/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win64-v7.1.exe'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'pinned ffmpeg fixture')
    monkeypatch.delenv('NEUROLOOP_FFMPEG', raising=False)
    monkeypatch.setattr(media, 'settings', lambda: SimpleNamespace(root=tmp_path, model_python=tmp_path / '.runtimes/model/Scripts/python.exe'))
    monkeypatch.setattr(media.shutil, 'which', lambda _: None)

    assert os.path.samefile(media.ffmpeg(), binary)


def test_file_inputs_receive_protocol_and_format_limits(tmp_path):
    media = tmp_path / 'owned.mp4'
    media.write_bytes(b'not decoded by this argument-only unit test')
    args = guarded_inputs(['-y', '-i', str(media), '-f', 'null', '-'])
    index = args.index('-i')
    assert args[index-len(FILE_INPUT_OPTIONS):index] == FILE_INPUT_OPTIONS


def test_unapproved_filter_generator_rejected():
    with pytest.raises(MediaError):
        guarded_inputs(['-f', 'lavfi', '-i', 'movie=https://example.invalid/secret'])


def test_internal_technical_fixture_generator_allowed():
    args = ['-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=2', '-t', '1', '-f', 'null', '-']
    assert guarded_inputs(args) == args


def test_playlist_disguised_as_video_rejected_without_network(tmp_path):
    file = tmp_path / 'not-a-video.mp4'
    file.write_text('#EXTM3U\n#EXTINF:3,\nhttp://127.0.0.1:9/never-fetch\n', encoding='utf-8')
    with pytest.raises(MediaError):
        inspect_media(file, 'video')
