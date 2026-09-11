import io

from PIL import Image

from neuroloop.modality import plan_for_asset, plan_for_input, routing_capabilities


def test_video_without_audio_or_transcript_only_loads_video_branch():
    plan = plan_for_input("video")
    assert plan.tribe_features == ("video",)
    assert plan.text_source == "none"
    assert plan.as_dict()["inactive_feature_encoders"] == ["text", "audio"]


def test_video_with_audio_and_words_loads_all_matching_branches():
    plan = plan_for_input("video", has_audio=True, has_timed_text=True)
    assert plan.tribe_features == ("text", "audio", "video")
    assert plan.text_source == "provided_timed_words"


def test_no_speech_audio_plan_does_not_add_text_implicitly():
    plan = plan_for_asset(
        "video",
        {"has_audio": True},
        {"no_speech": True, "allow_static_presentation": False},
    )
    assert plan.tribe_features == ("audio", "video")
    assert plan.text_source == "none"


def test_image_uses_explicit_repeated_frame_compatibility_path():
    plan = plan_for_input("image", allow_static_presentation=True)
    assert plan.tribe_features == ("video",)
    assert plan.input_adaptation == "repeated_frame_video_presentation"
    assert any("DINOv2" in note for note in plan.notes)


def test_text_uses_only_text_encoder_and_declares_reader_limit():
    plan = plan_for_input("text", has_timed_text=True)
    assert plan.tribe_features == ("text",)
    assert plan.as_dict()["reader_measurement"] == "not_available"
    assert any("individual reader" in note for note in plan.notes)


def test_text_without_timing_is_rejected():
    try:
        plan_for_input("text")
    except ValueError as exc:
        assert "timed-word" in str(exc)
    else:
        raise AssertionError("untimed text must not be sent to the neural pipeline")


def test_capabilities_explain_input_specific_routing():
    capabilities = routing_capabilities()
    assert capabilities["video"]["features"] == ["video"]
    assert capabilities["image"]["direct_image_encoder"] == "not_selected_for_current_checkpoint"
    assert capabilities["text"]["reader_measurement"] == "not_available"


def test_api_persists_the_selected_plan_for_an_image(client, headers):
    output = io.BytesIO()
    Image.new("RGB", (32, 24), (80, 60, 40)).save(output, format="PNG")
    uploaded = client.post(
        "/api/assets",
        headers=headers,
        files={"file": ("routing.png", output.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    project = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Routing contract", "asset_id": asset["id"]},
    )
    assert project.status_code == 201, project.text
    queued = client.post(
        "/api/runs",
        headers=headers,
        json={"project_id": project.json()["id"], "allow_static_presentation": True},
    )
    assert queued.status_code == 202, queued.text
    saved = client.get("/api/runs/" + queued.json()["id"], headers=headers)
    assert saved.status_code == 200, saved.text
    plan = saved.json()["config"]["modality_plans"][asset["id"]]
    assert plan["tribe_features"] == ["video"]
    assert plan["inactive_feature_encoders"] == ["text", "audio"]
