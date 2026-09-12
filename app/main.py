from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import storage
from .ai import ai_status, analyze_image, augment_translation, propose_from_learning_insights
from .auth import (
    authenticate,
    bootstrap_admin,
    current_user,
    current_user_optional,
    end_session,
    public_user,
    register_user,
    require_role,
    start_session,
    validate_role,
)
from .config import ROLE_ORDER, settings
from .egyptian import (
    hieroglyphize_phrase,
    mdc_to_transliteration,
    parse_uniliterals,
    search_dictionary,
    transliteration_to_mdc,
    uniliteral_table,
)
from .eshb import codebook_rows, decode, decode_ipa, encode, encode_ipa
from .models import (
    ESHBEncodeRequest,
    FeedbackRequest,
    LearningProposalRequest,
    LexiconProposalRequest,
    LiveVisionRequest,
    LoginRequest,
    ProgressRequest,
    ProposalDecisionRequest,
    RegisterRequest,
    RoleChangeRequest,
    TextRequest,
    TranslationRequest,
    UserDisableRequest,
)
from .pedagogy import get_lesson, lessons, random_vocab_quiz
from .linguistics import classroom_pronunciation, analyze_morphology
from .translator import contextual_translate

BASE = Path(__file__).parent
STATIC = BASE / "static"
DATA = BASE / "data"


async def _daily_research_loop():
    interval = max(1.0, settings.auto_research_interval_hours) * 3600
    while True:
        try:
            await propose_from_learning_insights(settings.auto_research_min_frequency, 20, None)
            storage.audit("learning.auto_research_run", None, "learning_loop", None, {"interval_hours": settings.auto_research_interval_hours})
        except Exception as exc:
            storage.audit("learning.auto_research_error", None, "learning_loop", None, {"error": str(exc)[:500]})
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    bootstrap_admin()
    task = None
    if settings.auto_research_enabled and settings.ai_endpoint:
        task = asyncio.create_task(_daily_research_loop())
    try:
        yield
    finally:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Trans-Late Ancient Relics",
    version="2.0.0",
    description="Live, context-aware Ancient Egyptian learning and translation system with ESHB, English, Swahili, IPA and review-gated AI.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    return response


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    return FileResponse(STATIC / "service-worker.js", media_type="application/javascript")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": settings.app_name,
        "version": "2.0.0",
        "environment": settings.environment,
        "ai": ai_status(),
        "live_frame_interval_ms": settings.live_frame_interval_ms,
        "auto_research_enabled": settings.auto_research_enabled,
    }


# --- Authentication and role-aware user management ---
@app.post("/api/auth/register")
def register(req: RegisterRequest, request: Request, response: Response):
    user = register_user(str(req.email), req.display_name, req.password)
    start_session(response, user, request)
    return {"ok": True, "user": public_user(user)}


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    user = authenticate(str(req.email), req.password)
    start_session(response, user, request)
    return {"ok": True, "user": public_user(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    end_session(response, request)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict | None = Depends(current_user_optional)):
    return {"authenticated": bool(user), "user": public_user(user), "role_order": ROLE_ORDER}


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(require_role("admin"))):
    return {"users": storage.list_users()}


@app.patch("/api/admin/users/{user_id}/role")
def admin_set_role(user_id: int, req: RoleChangeRequest, user: dict = Depends(require_role("admin"))):
    role = validate_role(req.role)
    updated = storage.set_user_role(user_id, role)
    if not updated:
        raise HTTPException(404, "User not found")
    storage.audit("user.role_change", user["id"], "user", user_id, {"role": role})
    return {"ok": True, "user": public_user(updated)}


@app.patch("/api/admin/users/{user_id}/disabled")
def admin_disable_user(user_id: int, req: UserDisableRequest, user: dict = Depends(require_role("admin"))):
    if user_id == user["id"] and req.disabled:
        raise HTTPException(422, "You cannot disable your own active administrator account")
    updated = storage.set_user_disabled(user_id, req.disabled)
    if not updated:
        raise HTTPException(404, "User not found")
    storage.audit("user.disabled_change", user["id"], "user", user_id, {"disabled": req.disabled})
    return {"ok": True, "user": public_user(updated)}


# --- Deterministic reversible ESHB / IPA ---
@app.get("/api/eshb/codebook")
def eshb_codebook():
    return codebook_rows()


@app.post("/api/eshb/encode")
def eshb_encode(req: ESHBEncodeRequest):
    return encode(req.text, req.language).__dict__


@app.post("/api/eshb/decode")
def eshb_decode(req: TextRequest):
    return {"source": req.text, "decoded": decode(req.text), "warning": "Strict ESHB separators are required for guaranteed reversibility."}


@app.post("/api/eshb/ipa/encode")
def ipa_encode(req: TextRequest):
    return encode_ipa(req.text).__dict__


@app.post("/api/eshb/ipa/decode")
def ipa_decode(req: TextRequest):
    return {"source": req.text, "ipa": decode_ipa(req.text)}


# --- Historical Egyptian script tools ---
@app.get("/api/egyptian/uniliterals")
def egyptian_uniliterals():
    return uniliteral_table()


@app.post("/api/egyptian/hieroglyphize")
def egyptian_hieroglyphize(req: TextRequest):
    return hieroglyphize_phrase(req.text)


@app.post("/api/egyptian/parse-uniliterals")
def egyptian_parse(req: TextRequest):
    return parse_uniliterals(req.text)


@app.post("/api/egyptian/mdc-to-transliteration")
def mdc_to_trans(req: TextRequest):
    return {"source": req.text, "transliteration": mdc_to_transliteration(req.text)}


@app.post("/api/egyptian/transliteration-to-mdc")
def trans_to_mdc(req: TextRequest):
    return {"source": req.text, "mdc": transliteration_to_mdc(req.text)}


@app.post("/api/egyptian/pronunciation")
def egyptian_pronunciation(req: TextRequest):
    return classroom_pronunciation(req.text)


@app.post("/api/egyptian/morphology")
def egyptian_morphology(req: TextRequest):
    return analyze_morphology(req.text)


# --- Context-aware translation, ambiguity, provenance and feedback ---
@app.get("/api/dictionary")
def dictionary(q: str = "", language: str = "all", pos: str | None = None, limit: int = 50):
    return {"query": q, "results": search_dictionary(q, language, pos, max(1, min(limit, 500)))}


@app.post("/api/translate")
async def translate(req: TranslationRequest, user: dict | None = Depends(current_user_optional)):
    result = contextual_translate(req.text, req.source, req.target, req.context, req.intent, req.mode)
    if req.use_ai:
        result["ai_review"] = await augment_translation(req.model_dump(), result)
    history_id = storage.save_translation(
        user["id"] if user else None,
        req.text,
        req.source,
        req.target,
        result.get("mode", req.mode),
        result,
    )
    result["translation_id"] = history_id
    return result


@app.get("/api/history")
def history(limit: int = Query(default=100, ge=1, le=500), user: dict = Depends(current_user)):
    return {"history": storage.translation_history(user["id"], limit)}


@app.post("/api/feedback")
def feedback(req: FeedbackRequest, user: dict | None = Depends(current_user_optional)):
    item = storage.add_feedback(
        user["id"] if user else None,
        req.translation_id,
        req.rating,
        req.suggested_translation,
        req.context,
        req.notes,
    )
    storage.audit("translation.feedback", user["id"] if user else None, "translation", req.translation_id, {"rating": req.rating})
    return {"ok": True, "feedback": item}


# --- Learning curriculum and personalized progress ---
@app.get("/api/lessons")
def all_lessons():
    return lessons()


@app.get("/api/lessons/{lesson_id}")
def lesson(lesson_id: int):
    item = get_lesson(lesson_id)
    if not item:
        raise HTTPException(404, "Lesson not found")
    return item


@app.get("/api/quiz/vocabulary")
def quiz(language: str = "english", count: int = 10):
    if language not in ("english", "swahili"):
        raise HTTPException(400, "language must be english or swahili")
    return random_vocab_quiz(language, max(1, min(count, 50)))


@app.post("/api/progress")
def update_progress(req: ProgressRequest, user: dict = Depends(current_user)):
    return storage.save_progress(user["id"], req.item_type, req.item_id, req.score)


@app.get("/api/progress")
def progress(user: dict = Depends(current_user)):
    return storage.get_progress(user["id"])


# --- Human-in-the-loop vocabulary growth ---
@app.post("/api/contributions/lexicon")
def submit_lexicon(req: LexiconProposalRequest, user: dict = Depends(require_role("contributor"))):
    proposal = storage.create_proposal(user["id"], req.model_dump(), ai_generated=False)
    storage.audit("lexicon.proposed", user["id"], "lexicon_proposal", proposal["id"])
    return {"ok": True, "proposal": proposal}


@app.get("/api/review/lexicon")
def review_queue(status: str | None = None, user: dict = Depends(require_role("reviewer"))):
    if status and status not in {"pending", "approved", "rejected"}:
        raise HTTPException(422, "Invalid proposal status")
    return {"proposals": storage.list_proposals(status)}


@app.post("/api/review/lexicon/{proposal_id}")
def review_lexicon(proposal_id: int, req: ProposalDecisionRequest, user: dict = Depends(require_role("reviewer"))):
    proposal = storage.review_proposal(proposal_id, user["id"], req.decision, req.notes)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    storage.audit("lexicon.reviewed", user["id"], "lexicon_proposal", proposal_id, {"decision": req.decision})
    return {"ok": True, "proposal": proposal}


@app.get("/api/admin/learning/insights")
def admin_learning_insights(user: dict = Depends(require_role("reviewer"))):
    return {"ai": ai_status(), **storage.learning_insights()}


@app.post("/api/admin/learning/propose")
async def admin_learning_propose(req: LearningProposalRequest, user: dict = Depends(require_role("reviewer"))):
    result = await propose_from_learning_insights(req.min_frequency, req.limit, user["id"])
    storage.audit("learning.proposal_run", user["id"], "learning_loop", None, {"created": len(result.get("created", []))})
    return result


@app.get("/api/admin/audit")
def audit_log(limit: int = Query(default=200, ge=1, le=1000), user: dict = Depends(require_role("admin"))):
    return {"events": storage.list_audit_events(limit)}


# --- Live camera / vision and WebSocket conversation ---
@app.post("/api/live/vision/analyze")
async def live_vision(req: LiveVisionRequest, user: dict | None = Depends(current_user_optional)):
    status_info = ai_status()
    if status_info["vision_ai_configured"] and not user:
        raise HTTPException(401, "Sign in before using cloud vision analysis")
    result = await analyze_image(req.image_data_url, req.target_language, req.context)
    if user:
        storage.audit("live.vision", user["id"], "live_session", req.session_id, {"status": result.get("status")})
    return result


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket):
    await websocket.accept()
    token = websocket.cookies.get(settings.session_cookie_name)
    user = storage.get_session_user(token)
    last_frame_at = 0.0
    try:
        while True:
            msg = await websocket.receive_json()
            kind = msg.get("type")
            if kind == "ping":
                await websocket.send_json({"type": "pong", "time": time.time()})
                continue
            if kind == "text":
                text = str(msg.get("text", "")).strip()
                if not text:
                    await websocket.send_json({"type": "error", "message": "No text supplied"})
                    continue
                source = msg.get("source", "english")
                target = msg.get("target", "egyptian")
                result = contextual_translate(text, source, target, str(msg.get("context", "")), str(msg.get("intent", "")), str(msg.get("mode", "careful")))
                if msg.get("use_ai", True):
                    result["ai_review"] = await augment_translation(msg, result)
                await websocket.send_json({"type": "translation", "result": result})
                continue
            if kind == "frame":
                now = time.monotonic()
                if now - last_frame_at < 0.75:
                    await websocket.send_json({"type": "throttle", "message": "Frame skipped to protect device and provider resources."})
                    continue
                last_frame_at = now
                if settings.vision_endpoint and not user:
                    await websocket.send_json({"type": "auth_required", "message": "Sign in before using cloud vision analysis."})
                    continue
                result = await analyze_image(str(msg.get("image_data_url", "")), str(msg.get("target_language", "english")), str(msg.get("context", "")))
                await websocket.send_json({"type": "vision", "result": result})
                continue
            await websocket.send_json({"type": "error", "message": f"Unsupported live message type: {kind}"})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@app.get("/api/references")
def references():
    return json.loads((DATA / "references.json").read_text(encoding="utf-8"))
