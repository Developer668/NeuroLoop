import math

import numpy as np
import pytest

from neuroloop import kragel
from neuroloop.response import COMMON, TSAM_LABELS, _source_window_details, ensemble, kragel_relative, target_score, tsam_series
from neuroloop.schemas import ResponseTarget
from neuroloop.tsam import PREPROCESSING_VERSION, preprocessing_contract, window_plan


def tsam_result(windows, duration=10):
    return {
        'status': 'experimental',
        'labels': list(TSAM_LABELS),
        'source_duration': duration,
        'windows': windows,
        'provenance': {
            'model': {'name': 'fixture-TSAM', 'version': 'fixture-v1'},
            'checkpoint': {'sha256': 'fixture-checkpoint'},
            'preprocessing': {'version': PREPROCESSING_VERSION, 'sha256': 'fixture-preprocessing'},
            'geometry': {'version': None, 'sha256': None},
            'projection': {'version': None, 'sha256': None},
        },
    }


def logits(happiness=0.0, anger=0.0):
    values = [0.0] * 8
    values[0] = anger
    values[4] = happiness
    return values


def test_tsam_contract_has_exact_order_and_window_tail_policy():
    assert TSAM_LABELS == ('Anger', 'Contempt', 'Disgust', 'Fear', 'Happiness', 'Neutral', 'Sadness', 'Surprise')
    assert [item['start'] for item in window_plan(11)] == [0.0, 5.0]
    assert window_plan(4.99) == []
    contract = preprocessing_contract()
    assert contract['version'] == PREPROCESSING_VERSION
    assert contract['window'] == {'seconds': 5, 'stride_seconds': 5, 'tail_policy': 'omit incomplete tail'}
    assert contract['class_order'] == list(TSAM_LABELS)


def test_tsam_rejects_reordered_missing_and_nonfinite_logits():
    base = {'start': 0, 'end': 5, 'logits': logits(happiness=4)}
    with pytest.raises(ValueError, match='class order'):
        tsam_series({**tsam_result([base]), 'labels': list(reversed(TSAM_LABELS))})
    with pytest.raises(ValueError, match='exactly eight'):
        tsam_series(tsam_result([{'start': 0, 'end': 5, 'logits': [0] * 7}]))
    bad = {'start': 0, 'end': 5, 'logits': [float('nan')] + [0] * 7}
    with pytest.raises(ValueError, match='finite'):
        tsam_series(tsam_result([bad]))
    with pytest.raises(ValueError, match='both start and end'):
        tsam_series(tsam_result([{'start': 0, 'logits': logits()}]))


def test_extreme_logits_are_finite_and_flat_logits_are_uniform():
    flat = tsam_result([{'start': 0, 'end': 5, 'logits': [0] * 8}], duration=5)
    values = tsam_series(flat)[0]['values']
    assert all(math.isfinite(value) for value in values.values())
    assert all(value == pytest.approx(1 / 8) for value in values.values())
    extreme = tsam_result([{'start': 0, 'end': 5, 'logits': [-1e300, 1e300, -1e300, -1e300, -1e300, -1e300, -1e300, -1e300]}], duration=5)
    values = tsam_series(extreme)[0]['values']
    assert all(math.isfinite(value) for value in values.values())
    assert values['contempt'] == pytest.approx(1.0)


def test_source_only_and_unsupported_dimensions_are_explicit():
    report = ensemble({'tsam': tsam_result([{'start': 0, 'end': 5, 'logits': logits(happiness=4)}], duration=5)})
    assert report['active_sources'] == ['tsam']
    assert report['values']['happiness'] is not None
    kragel = {'registration_verified':True,'transfer_validated':True,'decision_eligible':True,'status': 'experimental', 'aggregate': {'amused': 1, 'angry': 0, 'content': 0, 'fearful': 0, 'neutral': 0, 'sad': 0, 'surprised': 0}}
    report = ensemble({'kragel': kragel})
    assert report['active_sources'] == ['kragel']
    assert report['sources']['kragel']['contempt'] is None
    assert report['sources']['kragel']['disgust'] is None
    with pytest.raises(ValueError, match='unsupported dimensions'):
        kragel_relative({'status': 'experimental', 'aggregate': {'unpublished': 1}})


def test_invalid_weights_and_nan_never_reach_ensemble():
    evidence = {'tsam': tsam_result([{'start': 0, 'end': 5, 'logits': logits()}], duration=5)}
    with pytest.raises(ValueError, match='negative'):
        ensemble(evidence, weights={'tsam': -0.1, 'kragel': 1.1}, profile='fixture-v1')
    with pytest.raises(ValueError, match='sum'):
        ensemble(evidence, weights={'tsam': 0.6, 'kragel': 0.6}, profile='fixture-v1')
    with pytest.raises(ValueError, match='finite'):
        ensemble({'tsam': tsam_result([{'start': 0, 'end': 5, 'logits': [float('inf')] * 8}], duration=5)})


def test_temporal_target_isolated_from_wrong_segment_and_moves_monotonically():
    first = {'start': 0, 'end': 5, 'logits': logits(happiness=4, anger=0)}
    second_bad = {'start': 5, 'end': 10, 'logits': logits(happiness=-4, anger=4)}
    second_better = {'start': 5, 'end': 10, 'logits': logits(happiness=8, anger=0)}
    target = {'time_window': {'start': 0.0, 'end': 0.5}, 'emotions': {'happiness': {'desired': 0.8}}}
    base = target_score(ensemble({'tsam': tsam_result([first, second_bad])}), target)
    changed_wrong_segment = target_score(ensemble({'tsam': tsam_result([first, second_better])}), target)
    assert changed_wrong_segment['value'] == pytest.approx(base['value'])
    first_bad = {'start': 0, 'end': 5, 'logits': logits(happiness=-4, anger=4)}
    worse_first = target_score(ensemble({'tsam': tsam_result([first_bad, second_bad])}), target)
    assert base['value'] > worse_first['value']
    uncovered = target_score(ensemble({'tsam': tsam_result([first], duration=10)}), {'time_window': {'start': 0.75, 'end': 1.0}, 'emotions': {'happiness': {'desired': 0.8}}})
    assert uncovered is None


def test_overlapping_source_windows_use_explicit_overlap_axis():
    overlapping = tsam_result([
        {'start': 0, 'end': 6, 'logits': logits(happiness=4)},
        {'start': 5, 'end': 10, 'logits': logits(happiness=-4, anger=4)},
    ])
    rows = tsam_series(overlapping)
    assert rows[0]['start_norm'] == pytest.approx(0)
    assert rows[1]['start_norm'] == pytest.approx(0.5)
    report = ensemble({'tsam': overlapping})
    score = target_score(report, {'time_window': {'start': 0.5, 'end': 0.6}, 'emotions': {'happiness': {'desired': 0.5}}})
    assert score is not None
    assert score['segments'][0]['coverage'] == pytest.approx(1.0)


def test_interval_union_does_not_double_count_overlap_or_hide_a_gap():
    rows = [
        {'start_norm': 0.0, 'end_norm': 0.7, 'values': {'happiness': 1.0}},
        {'start_norm': 0.6, 'end_norm': 0.8, 'values': {'happiness': 0.0}},
        {'start_norm': 0.9, 'end_norm': 1.0, 'values': {'happiness': 0.0}},
    ]
    values, coverage, dimension_coverage = _source_window_details(rows, 0.0, 1.0)
    assert values['happiness'] == pytest.approx((0.6 + 0.1 * 0.5) / 0.9)
    assert coverage == pytest.approx(0.9)
    assert dimension_coverage['happiness'] == pytest.approx(0.9)


def test_partial_target_segment_is_not_scoreable_even_when_observed_values_match():
    partial = tsam_result([
        {'start': 0, 'end': 4, 'logits': logits(happiness=20)},
        {'start': 6, 'end': 10, 'logits': logits(happiness=20)},
    ], duration=10)
    report = ensemble({'tsam': partial})
    score = target_score(report, {'time_window': {'start': 0.0, 'end': 1.0}, 'emotions': {'happiness': {'desired': 0.9}}})
    assert score is None


def test_source_coverage_can_be_full_while_dimension_coverage_is_partial():
    rows = [
        {'start_norm': 0.0, 'end_norm': 0.5, 'values': {'happiness': 1.0, 'anger': None}},
        {'start_norm': 0.5, 'end_norm': 1.0, 'values': {'happiness': None, 'anger': 1.0}},
    ]
    values, coverage, dimension_coverage = _source_window_details(rows, 0.0, 1.0)
    assert coverage == pytest.approx(1.0)
    assert dimension_coverage['happiness'] == pytest.approx(0.5)
    assert dimension_coverage['anger'] == pytest.approx(0.5)
    assert values['happiness'] == pytest.approx(1.0)
    assert values['anger'] == pytest.approx(1.0)


def test_temporal_schema_rejects_invalid_or_empty_windows():
    with pytest.raises(ValueError, match='end'):
        ResponseTarget(emotions={'happiness': {'desired': 0.5}}, time_window={'start': 0.8, 'end': 0.2})
    with pytest.raises(ValueError, match='At least one'):
        ResponseTarget()


def test_finite_aware_trilinear_mask_does_not_emit_nan():
    volume = np.arange(8, dtype=float).reshape(2, 2, 2)
    volume[0, 0, 0] = np.nan
    sampled = kragel._trilinear(volume, np.array([[0.5, 0.5, 0.5], [2.0, 2.0, 2.0]]))
    assert math.isfinite(sampled[0])
    assert math.isnan(sampled[1])


def test_kragel_cache_identity_changes_with_geometry_bytes(monkeypatch, tmp_path):
    source = tmp_path / 'source'
    geometry = tmp_path / 'geometry'
    source.mkdir()
    geometry.mkdir()
    monkeypatch.setattr(kragel, '_source', lambda: source)
    monkeypatch.setattr(kragel, '_geometry', lambda name: geometry / name)
    for name in ('pial_left.gii.gz', 'pial_right.gii.gz', 'white_left.gii.gz', 'white_right.gii.gz'):
        (geometry / name).write_bytes(name.encode())
    first = kragel.cache_manifest()
    identity = kragel.cache_identity()
    (geometry / 'pial_left.gii.gz').write_bytes(b'changed-geometry')
    second = kragel.cache_manifest()
    assert first['projection']['version'] == kragel.PROJECTION_VERSION
    assert first['geometry']['sha256'] != second['geometry']['sha256']
    assert identity != kragel.cache_identity()
