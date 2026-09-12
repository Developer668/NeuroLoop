"""Audit pinned public TSAM split metadata without downloading or executing media."""
from pathlib import Path
import csv, hashlib, io, json, urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = '8296612414ce100b773b60f070706c5aa7ee8983'
LABELS = ['Anger', 'Contempt', 'Disgust', 'Fear', 'Happiness', 'Neutral', 'Sadness', 'Surprise']

def audit_splits(splits):
    report = {'splits': {}, 'overlaps': {}}
    for name, rows in splits.items():
        counts = {str(i): sum(int(r['Label']) == i for r in rows) for i in range(8)}
        invalid = [r for r in rows if not 0 <= int(r['Label']) < 8 or float(r['Start_Second']) < 0]
        report['splits'][name] = {'rows': len(rows), 'videos': len({r['Video_Name'] for r in rows}), 'class_counts': counts, 'invalid_rows': len(invalid)}
    names = list(splits)
    for i, left in enumerate(names):
        for right in names[i+1:]:
            a, b = splits[left], splits[right]
            videos = {r['Video_Name'] for r in a} & {r['Video_Name'] for r in b}
            clips = {(r['Video_Name'], float(r['Start_Second'])) for r in a} & {(r['Video_Name'], float(r['Start_Second'])) for r in b}
            report['overlaps'][left + '/' + right] = {'shared_source_videos': len(videos), 'identical_start_windows': len(clips)}
    report['metadata_split_disjoint'] = all(not x['shared_source_videos'] for x in report['overlaps'].values())
    return report

def main():
    target = ROOT / 'artifacts/scientific-audit/tsam'
    target.mkdir(parents=True, exist_ok=True)
    splits, hashes = {}, {}
    for name in ('training', 'validation', 'testing'):
        url = f'https://huggingface.co/datasets/dnamodel/adcumen-viewer-emotions/resolve/{REVISION}/{name}.csv'
        data = urllib.request.urlopen(url, timeout=60).read()
        (target / (name + '.csv')).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
        splits[name] = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
    result = audit_splits(splits)
    result.update(dataset_revision=REVISION, file_sha256=hashes, class_order=LABELS,
                  scope='Metadata audit only; no held-out prediction or calibration performed.',
                  unresolved=['Content-level duplicate detection', 'Checkpoint training-data membership', 'Checkpoint-bound class order confirmation', 'Held-out reproduction', 'Independent intended-domain labels and calibration'])
    source = ROOT / 'models/emotion/tsam/source-code'
    result['source_sha256'] = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source/'setup_data.py', source/'mvlib/mvideo_lib.py']}
    result['upstream_video_lists'] = {}
    original_training = set((source/'DataAdcumen/training_0').read_text().split())
    for name, file in [('training','training_0'),('validation','valid_0_p1'),('testing','valid_0_p2')]:
        expected = set((source/'DataAdcumen'/file).read_text().split())
        observed = {r['Video_Name'] for r in splits[name]}
        result['upstream_video_lists'][name] = {'published_count':len(expected),'csv_count':len(observed),'csv_not_in_list':len(observed-expected),'list_not_in_csv':len(expected-observed), 'overlap_with_original_training_list':len(observed & original_training)}
    (target/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
