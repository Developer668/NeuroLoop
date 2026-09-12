import pytest

from neuroloop import services
from neuroloop.schemas import RunCreate


def _image_bytes():
    from io import BytesIO
    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (32, 24), (90, 60, 60)).save(output, format="PNG")
    return output.getvalue()


def test_optional_readout_status_reports_missing_checkout_assets(tmp_path):
    status = services.readout_asset_status(tmp_path)

    assert status["tsam"]["ready"] is False
    assert status["tsam"]["status"] == "missing_weights"
    assert "models/emotion/tsam/weights/tsam_weights.tar" in status["tsam"]["missing"]

    assert status["kragel"]["ready"] is False
    assert status["kragel"]["status"] == "missing_assets"
    assert any(path.startswith("models/brain_readouts/kragel2015/source/")
               for path in status["kragel"]["missing"])


def test_tsam_checkpoint_alone_does_not_claim_readiness(tmp_path):
    checkpoint = tmp_path / "models/emotion/tsam/weights/tsam_weights.tar"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.touch()

    status = services.readout_asset_status(tmp_path)["tsam"]

    assert status["ready"] is False
    assert status["status"] == "missing_assets"
    assert any(path.startswith("models/emotion/tsam/source-code/") for path in status["missing"])


def test_complete_path_contract_keeps_later_ui_statuses(tmp_path):
    initial = services.readout_asset_status(tmp_path)
    for readout in initial.values():
        for relative_path in readout["required"]:
            path = tmp_path / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    status = services.readout_asset_status(tmp_path)

    assert status["tsam"]["status"] == "experimental_weights_present"
    assert status["tsam"]["ready"] is True
    assert status["tsam"]["validation"] == "unvalidated"
    assert status["kragel"]["status"] == "experimental_ready"
    assert status["kragel"]["ready"] is True
    assert status["kragel"]["validation"] == "unvalidated"


def test_capabilities_endpoint_exposes_missing_optional_assets(client, headers):
    response = client.get("/api/capabilities", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["tsam"]["ready"] is False
    assert data["tsam"]["status"] == "missing_weights"
    assert data["tsam"]["missing"]
    assert data["kragel"]["ready"] is False
    assert data["kragel"]["status"] == "missing_assets"
    assert data["kragel"]["missing"]


def test_requested_tsam_fails_closed_before_queueing_when_assets_are_missing():
    request = RunCreate(
        project_id="not-used",
        include_tsam=True,
        tsam_research_acknowledged=True,
    )

    with pytest.raises(services.DomainError, match="TSAM readout was requested") as error:
        services.create_run(request)
    assert "models/emotion/tsam/weights/tsam_weights.tar" in str(error.value)


def test_requested_kragel_fails_closed_before_queueing_when_assets_are_missing():
    request = RunCreate(project_id="not-used", include_kragel=True)

    with pytest.raises(services.DomainError, match="Kragel readout was requested") as error:
        services.create_run(request)
    assert "models/brain_readouts/kragel2015/source/" in str(error.value)


def test_tribe_only_path_can_queue_without_optional_readout_assets(client, headers):
    upload = client.post(
        "/api/assets",
        headers=headers,
        files={"file": ("tribe-only.png", _image_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    project = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "TRIBE-only readiness", "asset_id": upload.json()["id"]},
    )
    assert project.status_code == 201, project.text

    queued = client.post(
        "/api/runs",
        headers=headers,
        json={"project_id": project.json()["id"], "allow_static_presentation": True},
    )
    assert queued.status_code == 202, queued.text
    request = queued.json()["config"]["request"]
    assert request["include_tsam"] is False
    assert request["include_kragel"] is False
