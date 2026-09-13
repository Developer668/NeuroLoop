from types import SimpleNamespace

from neuroloop_app.config import Settings
from neuroloop_app.db import Store
from neuroloop_app.diagnostic_telemetry import diagnostics


def test_model_receipts_preserve_recorded_source(tmp_path):
    store = Store(Settings(_env_file=None, data_dir=tmp_path))
    store.initialize()
    sources = ('campaign_loop', 'reference_evaluation', 'generated_ad_evaluation')
    evidence = [SimpleNamespace(
        id=f'evidence-{index}', input_asset_id=f'asset-{index}', evaluator='summary',
        created_at=1.0, result={'status': 'SUCCEEDED'}, comparison_key='test',
        source_kind=source,
    ) for index, source in enumerate(sources)]
    with store.read() as session:
        rows = diagnostics(session, [], [], evidence)['model_receipts']
    assert [row['source'] for row in rows] == list(sources)
