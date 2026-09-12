"""Registration receipts cannot turn projection success into scientific validation."""
import json
import numpy as np
from neuroloop import kragel


def _assets(monkeypatch, tmp_path):
    source = tmp_path / 'source'
    geometry = tmp_path / 'geometry'
    source.mkdir()
    geometry.mkdir()
    monkeypatch.setattr(kragel, '_source', lambda: source)
    monkeypatch.setattr(kragel, '_geometry', lambda name: geometry / name)
    for kind in ('pial', 'white'):
        for hemi in kragel.HEMISPHERES:
            (geometry / f'{kind}_{hemi}.gii.gz').write_bytes(f'{kind}-{hemi}'.encode())
    for emotion in kragel.EMOTIONS:
        for suffix in ('hdr', 'img'):
            (source / f'mean_3comp_{emotion}_group_emotion_PLS_beta_BSz_10000it.{suffix}').write_bytes(emotion.encode())
    return source, geometry


def test_projection_is_not_registration(monkeypatch, tmp_path):
    _assets(monkeypatch, tmp_path)
    state = kragel.registration()
    assert state['verified'] is False
    assert state['decision_eligible'] is False
    assert state['status'] == 'unverified_coordinate_assumption'


def test_receipt_binds_to_all_geometry_and_volumes(monkeypatch, tmp_path):
    source, geometry = _assets(monkeypatch, tmp_path)
    receipt = {
        'surface_to_volume_world': np.eye(4).tolist(),
        'geometry_sha256': kragel._geometry_manifest()['files'],
        'volume_sha256': {p.name: kragel._sha256(p) for p in source.iterdir()},
        'source_space': 'test surface', 'target_space': 'test volume',
        'method': 'test registration', 'reviewed_by': 'test reviewer',
        'reference': 'https://example.test/registration',
        'validation': {'spatial_alignment_passed': True, 'hemisphere_order_passed': True, 'report_sha256': 'a'*64},
    }
    path = geometry / 'kragel-registration.json'
    path.write_text(json.dumps(receipt))
    first = kragel.registration()
    assert first['verified'] is True
    assert first['decision_eligible'] is False  # Registration never proves TRIBE transfer.
    (geometry / 'white_left.gii.gz').write_bytes(b'changed')
    assert kragel.registration()['status'] == 'invalid_registration_receipt'
    assert kragel.registration()['verified'] is False


def test_invalid_transform_is_rejected(monkeypatch, tmp_path):
    _, geometry = _assets(monkeypatch, tmp_path)
    (geometry / 'kragel-registration.json').write_text(json.dumps({'surface_to_volume_world': np.zeros((4,4)).tolist()}))
    assert kragel.registration()['status'] == 'invalid_registration_receipt'


def test_historical_kragel_is_diagnostic_not_decision_evidence():
    from neuroloop.response import ensemble, target_score
    raw = {'status': 'experimental', 'aggregate': {name: float(i) for i, name in enumerate(kragel.EMOTIONS)}}
    report = ensemble({'kragel': raw})
    assert report['active_sources'] == []
    assert report['source_weights']['kragel'] == 0
    assert report['sources']['kragel'] is None
    assert report['diagnostic_sources']['kragel'] is not None
    assert report['source_series']['kragel'] is None
    assert report['decision_eligible'] is False
    assert target_score(report, {'emotions': {'happiness': {'desired': 0.9}}}) is None
    historical = {'values': {'happiness': 0.9}, 'active_sources': ['kragel']}
    assert target_score(historical, {'emotions': {'happiness': {'desired': 0.9}}}) is None


def test_registration_without_transfer_cannot_enter_ensemble():
    from neuroloop.response import ensemble
    raw = {'status': 'experimental', 'registration_verified': True, 'decision_eligible': True,
           'aggregate': {name: float(i) for i, name in enumerate(kragel.EMOTIONS)}}
    assert ensemble({'kragel': raw})['sources']['kragel'] is None
    raw['transfer_validated'] = True
    assert ensemble({'kragel': raw})['active_sources'] == ['kragel']


def test_diagnostic_allowed_but_optimization_rejected(monkeypatch, tmp_path):
    import pytest
    from neuroloop import services
    from neuroloop.schemas import RunCreate
    monkeypatch.setattr(services, 'readout_asset_status', lambda root: {
        'tsam': {'ready': True, 'missing': []}, 'kragel': {'ready': True, 'missing': []}})
    monkeypatch.setattr(kragel, 'registration', lambda: {'verified': False, 'decision_eligible': False})
    services._require_requested_readouts(RunCreate(project_id='p', mode='analyze', include_kragel=True), tmp_path)
    body = RunCreate(project_id='p', mode='optimize', objective='response_target', include_kragel=True,
                     target={'emotions': {'happiness': {'desired': 0.8}}})
    with pytest.raises(services.DomainError, match='held-out TRIBE transfer'):
        services._require_requested_readouts(body, tmp_path)
