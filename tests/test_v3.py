from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from app.active_learning import (
    approved_dataset_manifest,
    collection_policy,
    init_active_learning_db,
    list_vision_corrections,
    review_vision_correction,
    submit_vision_correction,
)
from app.auth import create_user, init_auth_db
from app.epigraphy import analyze_hieroglyphic_text, epigraphy_capabilities, is_hieroglyph
from app.main import app
from app.morphology import analyze_transliteration
from app.speech import pronunciation_analysis
from app.vision import vision_status


@pytest.fixture(autouse=True)
def isolated_runtime_v3(tmp_path, monkeypatch):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "v3-test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.setenv("ESHB_VISION_BACKEND", "auto")
    monkeypatch.setenv("ESHB_VISION_MODEL_PATH", str(tmp_path / "missing.onnx"))
    monkeypatch.setenv("ESHB_VISION_CLASSES_PATH", str(tmp_path / "missing-classes.json"))
    monkeypatch.setenv("ESHB_ACTIVE_LEARNING_STORE_IMAGES", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ESHB_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ESHB_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    yield


def test_unicode_epigraphy_ranges_and_format_controls():
    assert is_hieroglyph("𓄤")
    assert is_hieroglyph(chr(0x13460))
    analysis = analyze_hieroglyphic_text("𓄤" + chr(0x13430) + "𓆑𓂋")
    assert analysis["sign_count"] == 3
    assert analysis["layout"]["vertical_joins"] == 1
    assert analysis["phonetic_complement_candidates"]
    assert analysis["phonetic_complement_candidates"][0]["host_value"] == "nfr"
    assert analysis["reading_direction"]["value"] == "undetermined_from_unicode_alone"
    caps = epigraphy_capabilities()
    assert caps["known_core_signs"] >= 25


def test_morphology_exposes_sdm_n_f_without_overclaiming_tense():
    result = analyze_transliteration("sḏm.n.f")
    assert result["words"][0]["base"] == "sḏm"
    forms = result["words"][0]["form_candidates"]
    assert forms[0]["form"] == "sḏm.n.f-type"
    assert forms[0]["subject"]["person"] == 3
    assert "context" in forms[0]["warning"]


def test_pronunciation_separates_classroom_from_historical_reconstruction():
    result = pronunciation_analysis("nfr ꜥnḫ", profile="research")
    assert result["classroom"]["classroom_reading"] == "nefer ankh"
    assert result["consonantal"]["certainty"] == "consonantal_only"
    assert result["historical_vowels"]["reconstructed"] is False
    assert len(result["research_requirements"]) >= 4


def test_local_vision_adapter_reports_missing_model_without_fake_inference():
    status = vision_status()
    assert status["resolved_backend"] == "unavailable"
    assert status["local"]["available"] is False
    assert status["ai"]["configured"] is False


def test_active_learning_never_stores_image_without_server_and_user_opt_in():
    init_auth_db()
    init_active_learning_db()
    learner = create_user("correctionlearner", "Correction-pass-123", role="learner")
    data = base64.b64encode(b"\xff\xd8\xffresearch-frame").decode()
    saved = submit_vision_correction(
        user_id=learner["id"],
        machine_analysis={"sign_candidates": [{"gardiner": "N37", "confidence": 0.61}]},
        expert_correction={"sign_candidates": [{"gardiner": "N35"}]},
        context="museum study",
        model_version="test-model",
        image_data_url=f"data:image/jpeg;base64,{data}",
        consent_store_image=True,
    )
    assert saved["image_sha256"]
    assert saved["image_consent"] is True
    assert saved["image_stored"] is False
    assert "server-side research image storage disabled" in saved["image_storage_notice"]
    assert collection_policy()["automatic_model_promotion"] is False


def test_reviewed_correction_enters_export_manifest_but_does_not_promote_model():
    init_auth_db()
    init_active_learning_db()
    learner = create_user("learnerexport", "Learner-export-123", role="learner")
    reviewer = create_user("reviewerexport", "Reviewer-export-123", role="reviewer")
    saved = submit_vision_correction(
        learner["id"],
        {"translation": "wrong"},
        {"translation": "corrected"},
        context="synthetic unit test",
    )
    reviewed = review_vision_correction(saved["id"], "approved", reviewer["id"], "Checked against synthetic fixture")
    assert reviewed["status"] == "approved"
    manifest = approved_dataset_manifest()
    assert manifest["count"] == 1
    assert manifest["training_policy"]["automatic_model_promotion"] is False


def test_correction_api_is_permission_bound_and_origin_hardened():
    with TestClient(app) as client:
        registered = client.post(
            "/api/auth/register",
            json={"username": "visionlearner", "display_name": "Vision Learner", "password": "Long-vision-pass-123"},
        )
        assert registered.status_code == 200
        created = client.post(
            "/api/vision/corrections",
            json={
                "machine_analysis": {"sign": "N37"},
                "expert_correction": {"sign": "N35"},
                "context": "unit test",
                "consent_store_image": False,
            },
        )
        assert created.status_code == 200
        denied = client.get("/api/vision/corrections")
        assert denied.status_code == 403
        cross_site = client.post(
            "/api/feedback",
            headers={"Origin": "https://evil.example"},
            json={"kind": "vision", "rating": 0},
        )
        assert cross_site.status_code == 403


def test_streaming_vision_socket_has_backpressure_and_guarded_result():
    data = base64.b64encode(b"\xff\xd8\xffsocket-frame").decode()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/vision") as ws:
            ws.send_json({
                "type": "frame",
                "image_data_url": f"data:image/jpeg;base64,{data}",
                "target_language": "english",
                "context": "test",
                "detail": "low",
            })
            payload = ws.receive_json()
            assert payload["type"] == "analysis"
            assert payload["sequence"] == 1
            assert payload["result"]["ok"] is False


def test_streaming_conversation_preserves_known_translation():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/conversation") as ws:
            ws.send_json({
                "type": "utterance",
                "text": "good",
                "source": "english",
                "target": "egyptian",
                "context": "describing quality",
                "use_ai": False,
            })
            payload = ws.receive_json()
            assert payload["type"] == "translation"
            assert payload["turn"] == 1
            assert payload["result"]["deterministic"]["transliteration"] == "nfr"


def test_v3_api_exposes_sign_morphology_pronunciation_and_policy():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["version"] == "3.0.0"
        signs = client.post("/api/egyptian/analyze-signs", json={"text": "𓄤𓆑𓂋"})
        assert signs.status_code == 200
        assert signs.json()["phonetic_complement_candidates"]
        morphology = client.post("/api/egyptian/analyze-transliteration", json={"text": "sḏm.n.f"})
        assert morphology.status_code == 200
        pronunciation = client.post("/api/speech/pronunciation", json={"text": "nfr", "profile": "research"})
        assert pronunciation.status_code == 200
        assert pronunciation.json()["historical_vowels"]["reconstructed"] is False
        policy = client.get("/api/research/collection-policy").json()
        assert policy["automatic_retraining"] is False


def test_list_corrections_status_validation():
    init_auth_db()
    init_active_learning_db()
    with pytest.raises(ValueError, match="Invalid correction status"):
        list_vision_corrections(status="trained")
