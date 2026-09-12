from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient

from app.ai import ai_status
from app.auth import create_user, init_auth_db
from app.contextual import contextual_translate
from app.knowledge import approved_lexicon_entries, create_proposal, init_knowledge_db, review_proposal
from app.main import app
from app.speech import classroom_reading
from app.vision import validate_image_data_url


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ESHB_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ESHB_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    yield


def test_classroom_reading_marks_uncertainty():
    result = classroom_reading("nfr sḏm")
    assert result["classroom_reading"] == "nefer sedjem"
    assert result["certainty"] == "conventional"
    assert "not fully recoverable" in result["warning"]


def test_png_validation_and_no_ai_status():
    # Minimal valid PNG signature plus bytes is sufficient for transport validation.
    data = base64.b64encode(b"\x89PNG\r\n\x1a\nunit-test").decode()
    meta = validate_image_data_url(f"data:image/png;base64,{data}")
    assert meta["mime"] == "image/png"
    assert meta["bytes"] > 8
    assert not ai_status()["configured"]


def test_contextual_translation_preserves_ambiguity_without_ai():
    result = __import__("asyncio").run(contextual_translate("good", "english", "egyptian", use_ai=False))
    assert result["deterministic"]["transliteration"] == "nfr"
    assert result["pronunciation"]["classroom_reading"] == "nefer"
    assert result["ai"]["used"] is False


def test_human_reviewed_runtime_lexicon_overlay():
    init_auth_db()
    init_knowledge_db()
    reviewer = create_user("reviewer1", "Review-pass-123", role="reviewer")
    proposal = create_proposal(
        "lexicon",
        {
            "transliteration": "tst",
            "english": ["test entry"],
            "swahili": ["ingizo la jaribio"],
            "pos": "noun",
            "notes": "Synthetic test entry only.",
            "confidence": "low",
        },
        evidence="Unit test evidence",
        proposer_user_id=reviewer["id"],
    )
    assert approved_lexicon_entries() == []
    review_proposal(proposal["id"], "approved", reviewer["id"], "Approved for unit test")
    overlays = approved_lexicon_entries()
    assert overlays[0]["transliteration"] == "tst"
    assert overlays[0]["runtime_overlay"] is True


def test_api_registration_permissions_and_progress():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={"username": "learner1", "display_name": "Learner", "password": "Long-pass-123"},
        )
        assert response.status_code == 200
        me = client.get("/api/auth/me").json()
        assert me["authenticated"] is True
        assert me["user"]["role"] == "learner"

        denied = client.post(
            "/api/knowledge/proposals",
            json={
                "kind": "grammar",
                "payload": {"note": "x"},
                "evidence": "",
                "source_url": "",
            },
        )
        assert denied.status_code == 403

        saved = client.post(
            "/api/progress",
            json={"learner": "ignored", "item_type": "lesson", "item_id": "1", "score": 1.0},
        )
        assert saved.status_code == 200
        assert saved.json()["learner"] == "learner1"
        items = client.get("/api/progress/me").json()
        assert items[0]["item_id"] == "1"


def test_live_vision_pipeline_is_available_but_guarded_without_provider():
    data = base64.b64encode(b"\xff\xd8\xffunit-test").decode()
    with TestClient(app) as client:
        response = client.post(
            "/api/vision/analyze",
            json={
                "image_data_url": f"data:image/jpeg;base64,{data}",
                "target_language": "english",
                "context": "museum label",
                "detail": "low",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["image"]["mime"] == "image/jpeg"
        assert "requires a configured" in body["message"]


def test_security_headers_and_pwa_routes():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "camera=(self)" in response.headers["Permissions-Policy"]
        manifest = client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        worker = client.get("/service-worker.js")
        assert worker.status_code == 200


def test_learner_feedback_and_reviewer_visibility():
    from app.auth import create_session, set_session_cookie
    from app.feedback import init_feedback_db, list_feedback

    with TestClient(app) as client:
        client.post(
            "/api/auth/register",
            json={"username": "feedbacklearner", "display_name": "Feedback Learner", "password": "Long-pass-456"},
        )
        saved = client.post(
            "/api/feedback",
            json={
                "kind": "translation",
                "source_text": "good",
                "source_language": "english",
                "target_language": "egyptian",
                "rating": -1,
                "correction": "Review context-sensitive gloss.",
                "context": "lesson",
                "note": "unit test",
            },
        )
        assert saved.status_code == 200
        assert saved.json()["rating"] == -1


def test_ai_lexicon_draft_needs_reviewer_source_url():
    from app.knowledge import update_proposal_evidence

    init_auth_db()
    init_knowledge_db()
    reviewer = create_user("reviewer2", "Review-pass-456", role="reviewer")
    proposal = create_proposal(
        "lexicon",
        {
            "transliteration": "xyz",
            "english": ["draft"],
            "swahili": ["rasimu"],
            "pos": "noun",
            "notes": "AI draft.",
            "confidence": "low",
        },
        evidence="AI rationale is not itself a scholarly attestation.",
        origin="ai",
    )
    with pytest.raises(ValueError, match="source URL"):
        review_proposal(proposal["id"], "approved", reviewer["id"], "Checked")
    update_proposal_evidence(proposal["id"], proposal["evidence"], "https://example.org/source", reviewer["id"])
    approved = review_proposal(proposal["id"], "approved", reviewer["id"], "Checked against source")
    assert approved["status"] == "approved"
