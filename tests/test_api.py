from __future__ import annotations

import base64
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app import storage


def unique_email(prefix="learner"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def register(client: TestClient, prefix="learner"):
    email = unique_email(prefix)
    r = client.post("/api/auth/register", json={"email": email, "display_name": prefix.title(), "password": "correct-horse-battery"})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def test_health_and_pwa_shell():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["version"] == "2.0.0"
        assert client.get("/manifest.webmanifest").status_code == 200
        assert client.get("/service-worker.js").status_code == 200


def test_auth_progress_and_history():
    with TestClient(app) as client:
        user = register(client)
        me = client.get("/api/auth/me").json()
        assert me["authenticated"]
        assert me["user"]["id"] == user["id"]

        p = client.post("/api/progress", json={"item_type": "lesson", "item_id": "1", "score": 1})
        assert p.status_code == 200
        assert client.get("/api/progress").json()[0]["item_id"] == "1"

        tr = client.post("/api/translate", json={"text": "good", "source": "english", "target": "egyptian", "use_ai": False})
        assert tr.status_code == 200
        assert tr.json()["translation_id"]
        history = client.get("/api/history").json()["history"]
        assert any(h["source_text"] == "good" for h in history)


def test_guest_cannot_submit_lexicon_proposal():
    with TestClient(app) as client:
        r = client.post("/api/contributions/lexicon", json={
            "transliteration": "xyz", "english": ["test"], "swahili": ["jaribio"], "pos": "noun"
        })
        assert r.status_code == 401


def test_contributor_and_reviewer_workflow():
    with TestClient(app) as contributor_client, TestClient(app) as reviewer_client:
        contributor = register(contributor_client, "contributor")
        storage.set_user_role(contributor["id"], "contributor")
        # Re-login to read the role from the DB-backed session user.
        contributor_client.post("/api/auth/logout", json={})
        email = storage.get_user(contributor["id"])["email"]
        login = contributor_client.post("/api/auth/login", json={"email": email, "password": "correct-horse-battery"})
        assert login.status_code == 200

        proposal = contributor_client.post("/api/contributions/lexicon", json={
            "transliteration": "tst",
            "english": ["test-object"],
            "swahili": ["kitu-cha-jaribio"],
            "pos": "noun",
            "notes": "automated test proposal",
            "evidence": "test fixture"
        })
        assert proposal.status_code == 200, proposal.text
        proposal_id = proposal.json()["proposal"]["id"]

        reviewer = register(reviewer_client, "reviewer")
        storage.set_user_role(reviewer["id"], "reviewer")
        reviewer_client.post("/api/auth/logout", json={})
        reviewer_email = storage.get_user(reviewer["id"])["email"]
        reviewer_client.post("/api/auth/login", json={"email": reviewer_email, "password": "correct-horse-battery"})
        queue = reviewer_client.get("/api/review/lexicon?status=pending")
        assert queue.status_code == 200
        assert any(x["id"] == proposal_id for x in queue.json()["proposals"])
        decision = reviewer_client.post(f"/api/review/lexicon/{proposal_id}", json={"decision": "approved", "notes": "fixture approval"})
        assert decision.status_code == 200

        search = reviewer_client.get("/api/dictionary?q=test-object&language=english")
        assert any(x["transliteration"] == "tst" for x in search.json()["results"])


def test_live_vision_is_honest_without_provider():
    with TestClient(app) as client:
        # The validator checks transport/size, not file semantics, which is enough to test provider gating.
        data_url = "data:image/jpeg;base64," + base64.b64encode(b"test-image").decode()
        r = client.post("/api/live/vision/analyze", json={"image_data_url": data_url, "target_language": "english", "context": "test"})
        assert r.status_code == 200
        assert r.json()["status"] in {"vision_provider_not_configured", "analyzed"}
