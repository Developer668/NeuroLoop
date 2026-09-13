from copy import deepcopy

import pytest

from neuroloop_app.decision_context import project_decision_context
from neuroloop_app.domain import digest


def state_for(*, eligible=False, scores=None, required=False):
    return {
        "config": {"optional_evaluators": ["tribe"], "required_evaluators": ["vision"] + (["tribe"] if required else [])},
        "evidence_bundles": [{
            "eligible": True, "quality": {"value": .82}, "hard_constraints": [{"status": "PASS"}],
            "evaluations": [{"id": "recorded-evaluation", "evaluator": "tribe", "result": {
                "status": "SUCCEEDED", "scores": scores or {}, "constraints": [],
                "provenance": {"model": "tribe", "checkpoint_sha256": "checkpoint"},
                "limitations": ["Not an individual brain scan"],
                "observations": {
                    "shape": [6, 20484], "warning": "Keep this warning",
                    "kragel": {
                        "decision_eligible": eligible, "cannot_be_used_for_decisions": True,
                        "trajectories": {"neutral": list(range(2000))},
                        "provenance": {"projection": {"registration": {"verified": False, "reason": "Registration unverified"}}},
                        "limitations": ["Not measured human emotions"],
                        "new_warning": "An unknown warning must survive",
                        "time_axis": {"missing_policy": "Never substitute zero"},
                    },
                },
            }}],
        }],
    }


def test_excluded_numerical_diagnostics_shrink_without_mutating_receipts():
    state = state_for()
    original = deepcopy(state)
    projected = project_decision_context(state)
    assert state == original
    old = state["evidence_bundles"][0]["evaluations"][0]
    new = projected["evidence_bundles"][0]["evaluations"][0]
    assert {k: v for k, v in old["result"].items() if k != "observations"} == {
        k: v for k, v in new["result"].items() if k != "observations"}
    before, after = old["result"]["observations"], new["result"]["observations"]
    assert "trajectories" not in after["kragel"]
    for key in ("limitations", "new_warning", "time_axis", "decision_eligible", "cannot_be_used_for_decisions"):
        assert after["kragel"][key] == before["kragel"][key]
    provenance = after["kragel"]["provenance"]
    assert provenance["original_sha256"] == digest(before["kragel"]["provenance"])
    assert provenance["metadata"]["/projection/registration/reason"] == "Registration unverified"
    assert provenance["metadata"]["/projection/registration/verified"] is False
    assert after["decision_context_projection"]["original_observations_sha256"] == digest(before)
    assert after["kragel"]["diagnostic_projection"]["original_sha256"] == digest(before["kragel"])
    assert projected["evidence_bundles"][0]["quality"] == state["evidence_bundles"][0]["quality"]


@pytest.mark.parametrize("kwargs", [{"eligible": True}, {"eligible": None}, {"scores": {"response": {"value": .5}}}, {"required": True}])
def test_active_scored_required_or_unknown_eligibility_is_never_projected(kwargs):
    state = state_for(**kwargs)
    assert project_decision_context(state) == state


def test_warning_inside_numeric_field_is_not_hidden():
    state = state_for()
    observations = state["evidence_bundles"][0]["evaluations"][0]["result"]["observations"]
    observations["kragel"]["trajectories"]["warning"] = "Uncertain preprocessing"
    result = project_decision_context(state)
    assert result["evidence_bundles"][0]["evaluations"][0]["result"]["observations"]["kragel"]["trajectories"] == observations["kragel"]["trajectories"]
