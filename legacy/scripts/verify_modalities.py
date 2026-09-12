"""Real inference smoke checks through the running API; never seed production claims.

The speech file is a small public ASR technical fixture. Test video/image/text
are explicitly labelled technical fixtures. Scores are actual model outputs;
these checks do not measure emotion accuracy or advertising effectiveness.
"""
from __future__ import annotations
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from neuroloop.config import settings
from neuroloop.media import execute
import httpx
from PIL import Image, ImageDraw

OUT = ROOT / 'data/verification/modalities'
OUT.mkdir(parents=True, exist_ok=True)
report = {'scope': 'Real API, preprocessing, encoders, TRIBE and saved cortical arrays. No mock inference; not a human-outcome validation.', 'cases': []}


def save_report():
    (OUT / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def checked(response):
    response.raise_for_status()
    return response.json()


def main():
    url = 'https://huggingface.co/datasets/Narsil/asr_dummy/resolve/8d141c8/1.flac'
    speech = OUT / 'asr-speech-fixture.flac'
    if not speech.exists():
        with httpx.Client(follow_redirects=True, timeout=60) as downloader:
            response = downloader.get(url)
            response.raise_for_status()
            if not 1000 < len(response.content) < 1_000_000:
                raise ValueError('Unexpected speech fixture size')
            speech.write_bytes(response.content)
    provenance = {'source': url, 'bytes': speech.stat().st_size, 'sha256': hashlib.sha256(speech.read_bytes()).hexdigest(), 'purpose': 'Technical ASR/inference integration verification only'}
    (OUT / 'speech-source.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')

    video = OUT / 'technical-video-with-speech.mp4'
    if not video.exists():
        execute(['-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=12', '-i', str(speech), '-shortest', '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], 60)
    image = OUT / 'technical-static-fixture.png'
    canvas = Image.new('RGB', (640, 360), (236, 225, 211))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((80, 70, 260, 290), fill=(118, 43, 63))
    draw.rectangle((310, 145, 570, 170), fill=(63, 51, 50))
    canvas.save(image)
    text = OUT / 'technical-timed-language.txt'
    content = 'A clear product story deserves a deliberate reveal.'
    text.write_text(content, encoding='utf-8')

    with httpx.Client(base_url='http://127.0.0.1:8010', headers={'Authorization': 'Bearer ' + settings().auth_token}, timeout=120) as client:
        for name, path in [('audio_with_speech', speech), ('video_audio_language', video), ('timed_text', text), ('static_image_presentation', image)]:
            started = time.monotonic()
            with path.open('rb') as stream:
                asset = checked(client.post('/api/assets', files={'file': (path.name, stream)}))
            if name == 'timed_text':
                words = [{'text': word, 'start': i * 0.6, 'end': (i + 1) * 0.6 - 0.05} for i, word in enumerate(content.split())]
                checked(client.put('/api/assets/' + asset['id'] + '/transcript', json={'words': words}))
            project = checked(client.post('/api/projects', json={'name': 'Technical modality verification / ' + name, 'brief': report['scope'], 'asset_id': asset['id']}))
            payload = {'project_id': project['id'], 'mode': 'analyze', 'max_evaluations': 1, 'max_seconds': 420, 'allow_static_presentation': name == 'static_image_presentation', 'no_speech': False}
            run = checked(client.post('/api/runs', json=payload))
            deadline = time.monotonic() + 460
            while time.monotonic() < deadline:
                current = checked(client.get('/api/runs/' + run['id']))
                if current['status'] in {'completed', 'failed', 'cancelled'}:
                    break
                time.sleep(2)
            else:
                checked(client.post('/api/runs/' + run['id'] + '/cancel'))
                raise RuntimeError('Verification exceeded its wait limit: ' + name)
            row = {'case': name, 'run_id': run['id'], 'status': current['status'], 'seconds': round(time.monotonic() - started, 3), 'error': current.get('error')}
            if current['status'] == 'completed':
                evaluation = checked(client.get('/api/evaluations/' + current['result']['baseline_evaluation_id']))
                row['shape'] = evaluation['evidence']['shape']
                row['modalities'] = evaluation['evidence']['modalities']
                row['transcript_source'] = evaluation['evidence']['transcript_source']
                row['scope_label'] = evaluation['evidence'].get('input_adaptation') or 'Direct media inference with recorded modality coverage'
                row['peak_cuda_bytes'] = evaluation['evidence'].get('peak_cuda_bytes')
                assert row['shape'][1] == 20484 and row['shape'][0] > 0
                expected = {'audio_with_speech': {'Audio', 'Word'}, 'video_audio_language': {'Video', 'Audio', 'Word'}, 'timed_text': {'Word'}, 'static_image_presentation': {'Video'}}[name]
                assert expected.issubset(set(row['modalities'])), row
            report['cases'].append(row)
            save_report()
            print(json.dumps(row, indent=2), flush=True)
            if current['status'] != 'completed':
                raise RuntimeError('Real inference failed for ' + name + ': ' + str(current.get('error')))
    report['passed'] = True
    save_report()
    print('All four real modality checks passed.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        report['passed'] = False
        report['failure'] = str(exc)
        save_report()
        raise
