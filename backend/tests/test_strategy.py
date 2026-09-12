from __future__ import annotations

import pytest

from neuroloop.strategy import CreativeStrategist, InterventionProposal


@pytest.fixture(autouse=True)
def allow_model_free_optional_readouts(monkeypatch):
    """Controller tests use deterministic fixtures instead of optional models."""
    from neuroloop import services, kragel

    # Explicit controller fixture, not a claim about the actual registration.
    monkeypatch.setattr(kragel, "registration", lambda: {"decision_eligible": True})

    monkeypatch.setattr(services, 'readout_asset_status', lambda root=None: {
        'tsam': {'ready': True, 'missing': []},
        'kragel': {'ready': True, 'missing': []},
    })


def test_deterministic_strategist_emits_typed_candidates_from_target_gap():
    target = {
        "version": "target-spec/v1",
        "scope": "time_window",
        "time_window": {"start": 0.25, "end": 0.5, "label": "opening"},
        "emotions": {"happiness": {"desired": 0.8, "weight": 2}},
    }
    report = {
        "version": "response-ensemble/v1",
        "profile": "fixture-profile",
        "values": {"happiness": 0.2},
        "source_weights": {"tsam": 1.0, "kragel": 0.0},
        "source_series": {
            "tsam": [{"start_norm": 0.0, "end_norm": 1.0, "values": {"happiness": 0.2}}],
            "kragel": None,
        },
    }
    strategist = CreativeStrategist()

    first = strategist.propose(
        target,
        report,
        {"source_duration": 8, "headline_start": 1.0},
        [],
        {"preserve_duration": True, "preserve_audio": True},
        allowed_operators=["brightness_up", "contrast_up", "saturation_up"],
    )
    candidates = strategist.propose_candidates(
        target,
        report,
        {"source_duration": 8, "headline_start": 1.0},
        [],
        {"preserve_duration": True, "preserve_audio": True},
        allowed_operators=["brightness_up", "contrast_up", "saturation_up"],
    )

    assert isinstance(first, InterventionProposal)
    assert [item.model_dump(mode="json") for item in candidates] == [
        item.model_dump(mode="json") for item in strategist.propose_candidates(
            target,
            report,
            {"source_duration": 8, "headline_start": 1.0},
            [],
            {"preserve_duration": True, "preserve_audio": True},
            allowed_operators=["brightness_up", "contrast_up", "saturation_up"],
        )
    ]
    assert len(candidates) == 3
    assert all(item.targeted_window.start == 0.25 for item in candidates)
    assert all(item.response_gap.dimension == "happiness" for item in candidates)
    assert all(item.backend_identity.startswith("creative-strategist/") for item in candidates)
    assert all(item.expected_relative_evidence_effect.evidence_only for item in candidates)


def test_policy_omits_invalid_outcomes_without_cross_context_update(client):
    from neuroloop import policy

    context = "strategy-invalid-fixture"
    assert not policy.record_outcome(context, "brightness_up", 0.4, 1, 0.01, decision="reverted", valid=False)
    assert policy.choose(context, ["brightness_up"], set(), "fixture")["attempts"] == 0
    assert policy.record_outcome(context, "brightness_up", 0.04, 1, 0.01, decision="kept")
    assert policy.choose(context, ["brightness_up"], set(), "fixture")["attempts"] == 1
    assert policy.choose("strategy-other-context", ["brightness_up"], set(), "fixture")["attempts"] == 0


def test_worker_evaluates_three_siblings_and_retains_the_winner(client, headers, monkeypatch):
    from backend.tests.test_contracts import project, upload
    from neuroloop import worker
    from neuroloop.db import Evaluation, Experiment, Run, Session

    asset = upload(client, headers, name="branching.png")
    project_row = project(client, headers, asset)
    queued = client.post(
        "/api/runs",
        headers=headers,
        json={
            "project_id": project_row["id"],
            "mode": "optimize",
            "objective": "response_target",
            "target": {"emotions": {"happiness": {"desired": 0.8}}},
            "include_kragel": True,
            "allow_static_presentation": True,
            "operators": ["brightness_up", "contrast_up", "saturation_up"],
            "max_evaluations": 4,
            "target_score": 0.95,
        },
    )
    assert queued.status_code == 202, queued.text
    run_id = queued.json()["id"]
    original = worker.get_asset(asset["id"])
    scores = iter((0.2, 0.5, 0.8, 0.6))

    def fake_evaluation(identity, selected, config):
        score = next(scores)
        return Evaluation(
            id=f"branch-eval-{score}",
            asset_id=selected.id,
            cache_key=f"branch-cache-{score}",
            evaluator="fixture",
            profile="fixed-profile",
            evidence={
                "response_ensemble": {
                    "profile": "fixture",
                    "values": {"happiness": score},
                    "sources": {},
                    "source_weights": {},
                    "decision_eligible": True, "active_sources": ["fixture"],
                    "disagreement": {},
                    "mean_disagreement": None,
                    "confidence": "fixture",
                    "interpretation": "deterministic controller fixture",
                }
            },
            prediction_path=None,
            duration_seconds=0,
        )

    monkeypatch.setattr(worker, "evaluation", fake_evaluation)
    monkeypatch.setattr(worker, "render_candidate", lambda *args, **kwargs: original)
    monkeypatch.setattr(worker, "record_evidence", lambda *args, **kwargs: None)

    with pytest.raises(worker.StopRun, match="No untested permitted operators|evaluation budget|response target reached"):
        worker.execute_run(run_id)

    with Session() as db:
        run = db.get(Run, run_id)
        experiments = db.query(Experiment).filter(Experiment.run_id == run_id).order_by(Experiment.sequence).all()
        assert len(experiments) == 3
        assert len({row.specification["lineage_id"] for row in experiments}) == 1
        assert all(set(row.specification["sibling_ids"]) == {item.id for item in experiments} for row in experiments)
        assert [row.decision for row in experiments].count("kept") == 1
        assert max(row.candidate_score for row in experiments if row.candidate_score is not None) == pytest.approx(1.0)
        assert run.result["best_metric"]["value"] == pytest.approx(1.0)


def test_worker_preserves_previous_best_when_all_siblings_fail(client, headers, monkeypatch):
    from backend.tests.test_contracts import project, upload
    from neuroloop import worker
    from neuroloop.db import Experiment, Run, Session

    asset = upload(client, headers, name="failed-branching.png")
    project_row = project(client, headers, asset)
    queued = client.post(
        "/api/runs",
        headers=headers,
        json={
            "project_id": project_row["id"],
            "mode": "optimize",
            "objective": "response_target",
            "target": {"emotions": {"happiness": {"desired": 0.8}}},
            "include_kragel": True,
            "allow_static_presentation": True,
            "operators": ["brightness_up", "contrast_up", "saturation_up"],
            "max_evaluations": 4,
            "target_score": 0.95,
        },
    )
    assert queued.status_code == 202, queued.text
    run_id = queued.json()["id"]
    calls = {"count": 0}

    def failing_evaluation(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] > 1:
            raise RuntimeError("fixture evaluator failed")
        from neuroloop.db import Evaluation

        return Evaluation(
            id="failed-branch-baseline",
            asset_id=asset["id"],
            cache_key="failed-branch-baseline-cache",
            evaluator="fixture",
            profile="fixed-profile",
            evidence={
                "response_ensemble": {
                    "profile": "fixture",
                    "values": {"happiness": 0.2},
                    "sources": {},
                    "source_weights": {},
                    "decision_eligible": True, "active_sources": ["fixture"],
                    "disagreement": {},
                    "mean_disagreement": None,
                    "confidence": "fixture",
                    "interpretation": "deterministic controller fixture",
                }
            },
            prediction_path=None,
            duration_seconds=0,
        )

    monkeypatch.setattr(worker, "evaluation", failing_evaluation)
    monkeypatch.setattr(worker, "render_candidate", lambda *args, **kwargs: worker.get_asset(asset["id"]))
    monkeypatch.setattr(worker, "record_evidence", lambda *args, **kwargs: None)

    with pytest.raises(worker.StopRun, match="No untested permitted operators"):
        worker.execute_run(run_id)

    with Session() as db:
        run = db.get(Run, run_id)
        experiments = db.query(Experiment).filter(Experiment.run_id == run_id).all()
        assert run.result["best_asset_id"] == asset["id"]
        assert run.result["best_metric"]["value"] == pytest.approx(0.4)
        assert len(experiments) == 3 and all(item.decision == "invalid" for item in experiments)


def test_worker_rejects_failed_pre_evaluation_gate_before_model_evaluation(client, headers, monkeypatch):
    from backend.tests.test_contracts import project, upload
    from neuroloop import worker
    from neuroloop.db import Experiment, Run, Session
    from neuroloop.media_quality import MediaQualityReport, PreEvaluationReport

    asset = upload(client, headers, name="gate-before-model.png")
    project_row = project(client, headers, asset)
    queued = client.post(
        "/api/runs",
        headers=headers,
        json={
            "project_id": project_row["id"],
            "mode": "optimize",
            "objective": "response_target",
            "target": {"emotions": {"happiness": {"desired": 0.8}}},
            "include_kragel": True,
            "allow_static_presentation": True,
            "operators": ["brightness_up"],
            "max_evaluations": 2,
            "target_score": 0.95,
        },
    )
    run_id = queued.json()["id"]
    original = worker.get_asset(asset["id"])
    calls = {"evaluation": 0, "gate": 0}

    def fake_evaluation(identity, selected, config):
        calls["evaluation"] += 1
        if calls["evaluation"] > 1:
            raise AssertionError("candidate reached the model evaluator")
        from neuroloop.db import Evaluation
        return Evaluation(id="gate-baseline", asset_id=selected.id, cache_key="gate-baseline-cache", evaluator="fixture", profile="fixed-profile", evidence={"response_ensemble": {"profile": "fixture", "values": {"happiness": 0.2}, "sources": {}, "source_weights": {}, "decision_eligible": True, "active_sources": ["fixture"], "disagreement": {}, "mean_disagreement": None, "confidence": "fixture", "interpretation": "control-flow fixture"}}, prediction_path=None, duration_seconds=0)

    def reject_gate(*args, **kwargs):
        calls["gate"] += 1
        quality = MediaQualityReport(False, "image", original.path, violations=("corrupt candidate",))
        return PreEvaluationReport(False, quality)

    monkeypatch.setattr(worker, "evaluation", fake_evaluation)
    monkeypatch.setattr(worker, "render_candidate", lambda *args, **kwargs: original)
    monkeypatch.setattr(worker, "pre_evaluation_gate", reject_gate)

    with pytest.raises(worker.StopRun, match="No untested permitted operators"):
        worker.execute_run(run_id)

    assert calls == {"evaluation": 1, "gate": 1}
    with Session() as db:
        run = db.get(Run, run_id)
        experiment = db.query(Experiment).filter(Experiment.run_id == run_id).one()
        assert run.result["best_asset_id"] == asset["id"]
        assert experiment.decision == "invalid"
        assert experiment.evidence["pre_evaluation_gate"]["quality"]["violations"] == ["corrupt candidate"]
