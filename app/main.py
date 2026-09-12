from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .active_learning import (
    approved_dataset_manifest,
    collection_policy,
    init_active_learning_db,
    list_vision_corrections,
    review_vision_correction,
    submit_vision_correction,
)
from .ai import ai_status
from .auth import (
    authenticate,
    clear_session_cookie,
    create_session,
    create_user,
    destroy_session,
    get_current_user,
    init_auth_db,
    list_users,
    require_permission,
    require_user,
    set_session_cookie,
    set_user_role,
)
from .contextual import contextual_translate
from .egyptian import (
    current_lexicon,
    hieroglyphize_phrase,
    mdc_to_transliteration,
    parse_uniliterals,
    search_dictionary,
    transliteration_to_mdc,
    uniliteral_table,
)
from .epigraphy import analyze_hieroglyphic_text, epigraphy_capabilities
from .eshb import codebook_rows, decode, decode_ipa, encode, encode_ipa
from .feedback import create_feedback, init_feedback_db, list_feedback
from .history import clear_history, init_history_db, list_history, save_history
from .knowledge import (
    create_proposal,
    init_knowledge_db,
    list_proposals,
    review_proposal,
    top_unresolved,
    update_proposal_evidence,
)
from .learning_loop import background_loop, knowledge_loop_status, run_knowledge_cycle
from .models import (
    ContextualTranslationRequest,
    CorrectionReviewRequest,
    ESHBEncodeRequest,
    FeedbackRequest,
    KnowledgeEvidenceRequest,
    KnowledgeProposalRequest,
    KnowledgeReviewRequest,
    KnowledgeRunRequest,
    LoginRequest,
    ProgressRequest,
    PronunciationRequest,
    RegisterRequest,
    RoleUpdateRequest,
    TextRequest,
    TranslationRequest,
    VisionCorrectionRequest,
    VisionRequest,
)
from .morphology import analyze_transliteration
from .pedagogy import ensure_progress_db, get_lesson, get_progress, lessons, random_vocab_quiz, save_progress
from .runtime import env_bool
from .security import enforce_unsafe_origin, security_headers
from .speech import classroom_reading, pronunciation_analysis
from .streaming import conversation_socket, streaming_capabilities, vision_socket
from .translator import egyptian_to_modern, translate_phrase, translate_word
from .vision import analyze_frame, vision_status

BASE = Path(__file__).parent
STATIC = BASE / "static"
DATA = BASE / "data"
APP_VERSION = "3.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_db()
    init_knowledge_db()
    init_history_db()
    init_feedback_db()
    init_active_learning_db()
    ensure_progress_db()
    stop_event = asyncio.Event()
    task = None
    if env_bool("ESHB_KNOWLEDGE_LOOP_ENABLED", False):
        task = asyncio.create_task(background_loop(stop_event))
    app.state.knowledge_stop = stop_event
    app.state.knowledge_task = task
    try:
        yield
    finally:
        stop_event.set()
        if task:
            try:
                await asyncio.wait_for(task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()


app = FastAPI(
    title="Trans-Late Ancient Relics",
    version=APP_VERSION,
    description="Evidence-aware Ancient Egyptian learning, epigraphy, contextual translation, live camera analysis, voice and reversible ESHB tools.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def request_security(request: Request, call_next):
    try:
        enforce_unsafe_origin(request)
    except HTTPException as exc:
        response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        security_headers(response)
        return response
    response = await call_next(request)
    security_headers(response)
    return response


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    return FileResponse(STATIC / "service-worker.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "Trans-Late Ancient Relics",
        "version": APP_VERSION,
        "lexicon_entries": len(current_lexicon()),
        "lessons": len(lessons()),
        "ai": ai_status(),
        "vision": vision_status(),
    }


@app.get("/api/capabilities")
def capabilities(request: Request):
    user = get_current_user(request)
    return {
        "version": APP_VERSION,
        "ai": ai_status(),
        "vision": vision_status(),
        "streaming": streaming_capabilities(),
        "epigraphy": epigraphy_capabilities(),
        "active_learning": collection_policy(),
        "knowledge_loop": knowledge_loop_status(),
        "user": user,
        "features": {
            "eshb": True,
            "ipa": True,
            "dictionary": True,
            "lessons": True,
            "contextual_translation": True,
            "morphology_analysis": True,
            "sign_function_analysis": True,
            "unicode_hieroglyph_format_controls": True,
            "unicode_hieroglyph_extended_a_detection": True,
            "camera_pipeline": True,
            "local_onnx_vision_adapter": True,
            "vision_websocket": True,
            "conversation_websocket": True,
            "browser_speech": True,
            "pronunciation_profiles": True,
            "pwa": True,
            "human_reviewed_learning_loop": True,
            "opt_in_active_learning": True,
        },
    }


# ---------------- Authentication & roles ----------------
@app.post("/api/auth/register")
def register(req: RegisterRequest, request: Request, response: Response):
    from .security import check_rate_limit
    check_rate_limit(request, "auth-register", 10, 3600)
    try:
        user = create_user(req.username, req.password, req.display_name or req.username, role="learner")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    token = create_session(user["id"])
    set_session_cookie(response, token)
    return {"authenticated": True, "user": user}


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    from .security import check_rate_limit
    check_rate_limit(request, "auth-login", 20, 900)
    user = authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")
    token = create_session(user["id"])
    set_session_cookie(response, token)
    return {"authenticated": True, "user": user}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    destroy_session(request.cookies.get("eshb_session"))
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    user = get_current_user(request)
    return {"authenticated": bool(user), "user": user, "role": user["role"] if user else "guest"}


@app.get("/api/admin/users")
def admin_users(_user: dict = Depends(require_permission("users:manage"))):
    return {"users": list_users()}


@app.put("/api/admin/users/{user_id}/role")
def admin_set_role(user_id: int, req: RoleUpdateRequest, _user: dict = Depends(require_permission("users:manage"))):
    try:
        return {"user": set_user_role(user_id, req.role)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------- Reversible ESHB / script laboratory ----------------
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


@app.get("/api/egyptian/uniliterals")
def egyptian_uniliterals():
    return uniliteral_table()


@app.get("/api/egyptian/epigraphy-capabilities")
def egyptian_epigraphy_capabilities():
    return epigraphy_capabilities()


@app.post("/api/egyptian/analyze-signs")
def egyptian_analyze_signs(req: TextRequest):
    return analyze_hieroglyphic_text(req.text)


@app.post("/api/egyptian/analyze-transliteration")
def egyptian_analyze_transliteration(req: TextRequest):
    return analyze_transliteration(req.text)


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


@app.post("/api/speech/classroom-reading")
def speech_reading(req: TextRequest):
    return classroom_reading(req.text)


@app.post("/api/speech/pronunciation")
def speech_pronunciation(req: PronunciationRequest):
    try:
        return pronunciation_analysis(req.text, req.profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------- Dictionary & translation ----------------
@app.get("/api/dictionary")
def dictionary(q: str = "", language: str = "all", pos: str | None = None, limit: int = 50):
    return {"query": q, "results": search_dictionary(q, language, pos, limit)}


@app.post("/api/translate")
def translate(req: TranslationRequest):
    if req.source == "egyptian":
        if req.target == "egyptian":
            return hieroglyphize_phrase(req.text)
        return egyptian_to_modern(req.text, req.target)
    if req.target != "egyptian":
        return translate_word(req.text, req.source, req.target)
    exact = translate_word(req.text, req.source, "egyptian")
    if exact.get("ok"):
        return exact
    return translate_phrase(req.text, req.source)


@app.post("/api/translate/contextual")
async def translate_contextual(req: ContextualTranslationRequest, request: Request):
    from .security import check_rate_limit
    check_rate_limit(request, "translate", 120, 60)
    result = await contextual_translate(
        req.text,
        req.source,
        req.target,
        context=req.context,
        register=req.translation_register,
        use_ai=req.use_ai,
        max_alternatives=req.max_alternatives,
    )
    user = get_current_user(request)
    if req.save_history and user:
        result["history"] = save_history(user["id"], req.source, req.target, req.text, result, mode="text")
    elif req.save_history and not user:
        result["history_warning"] = "Sign in to save translation history."
    return result


# ---------------- Live camera / multimodal analysis ----------------
@app.get("/api/vision/status")
def public_vision_status():
    return vision_status()


@app.post("/api/vision/analyze")
async def vision_analyze(req: VisionRequest, request: Request):
    from .security import check_rate_limit
    check_rate_limit(request, "vision", 30, 60)
    try:
        return await analyze_frame(req.image_data_url, req.target_language, req.context, req.detail)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Vision provider failed: {exc}") from exc


@app.websocket("/ws/vision")
async def ws_vision(websocket: WebSocket):
    await vision_socket(websocket)


@app.websocket("/ws/conversation")
async def ws_conversation(websocket: WebSocket):
    await conversation_socket(websocket)


# ---------------- Active-learning correction governance ----------------
@app.get("/api/research/collection-policy")
def research_collection_policy():
    return collection_policy()


@app.post("/api/vision/corrections")
def vision_correction_create(req: VisionCorrectionRequest, user: dict = Depends(require_permission("vision_correction:create"))):
    try:
        return submit_vision_correction(
            user_id=user["id"],
            machine_analysis=req.machine_analysis,
            expert_correction=req.expert_correction,
            context=req.context,
            model_version=req.model_version,
            image_data_url=req.image_data_url,
            consent_store_image=req.consent_store_image,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/vision/corrections")
def vision_correction_list(status: str | None = None, limit: int = 100, _user: dict = Depends(require_permission("dataset:inspect"))):
    try:
        return {"items": list_vision_corrections(status=status, limit=limit), "policy": collection_policy()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/vision/corrections/{correction_id}/review")
def vision_correction_review(correction_id: str, req: CorrectionReviewRequest, user: dict = Depends(require_permission("vision_correction:review"))):
    try:
        return review_vision_correction(correction_id, req.status, user["id"], req.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/research/dataset-manifest")
def research_dataset_manifest(limit: int = 5000, _user: dict = Depends(require_permission("dataset:export"))):
    return approved_dataset_manifest(limit=limit)


# ---------------- Learning ----------------
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
def update_progress(req: ProgressRequest, user: dict = Depends(require_permission("progress:write"))):
    return save_progress(user["username"], req.item_type, req.item_id, req.score)


@app.get("/api/progress/me")
def my_progress(user: dict = Depends(require_user)):
    return get_progress(user["username"])


@app.get("/api/progress/{learner}")
def progress(learner: str, _user: dict = Depends(require_permission("users:manage"))):
    return get_progress(learner)


# ---------------- History ----------------
@app.get("/api/history")
def history(limit: int = 50, user: dict = Depends(require_user)):
    return {"items": list_history(user["id"], limit)}


@app.delete("/api/history")
def history_clear(user: dict = Depends(require_user)):
    return {"deleted": clear_history(user["id"])}


# ---------------- Learner feedback / correction signal ----------------
@app.post("/api/feedback")
def feedback_create(req: FeedbackRequest, user: dict = Depends(require_permission("feedback:create"))):
    try:
        return create_feedback(
            user_id=user["id"], kind=req.kind, source_text=req.source_text, source_language=req.source_language,
            target_language=req.target_language, rating=req.rating, correction=req.correction, context=req.context, note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/feedback")
def feedback_list(kind: str | None = None, limit: int = 100, _user: dict = Depends(require_permission("knowledge:inspect"))):
    return {"items": list_feedback(limit=limit, kind=kind)}


# ---------------- Human-reviewed knowledge growth ----------------
@app.post("/api/knowledge/proposals")
def knowledge_create(req: KnowledgeProposalRequest, user: dict = Depends(require_permission("proposal:create"))):
    try:
        return create_proposal(
            kind=req.kind, payload=req.payload, evidence=req.evidence, source_url=req.source_url,
            proposer_user_id=user["id"], origin="human", confidence=req.confidence,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/knowledge/proposals")
def knowledge_list(status: str | None = None, kind: str | None = None, limit: int = 100, _user: dict = Depends(require_permission("knowledge:inspect"))):
    try:
        return {"items": list_proposals(status=status, kind=kind, limit=limit)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/knowledge/proposals/{proposal_id}/evidence")
def knowledge_evidence(proposal_id: str, req: KnowledgeEvidenceRequest, user: dict = Depends(require_permission("proposal:review"))):
    try:
        return update_proposal_evidence(proposal_id, req.evidence, req.source_url, user["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/knowledge/proposals/{proposal_id}/review")
def knowledge_review(proposal_id: str, req: KnowledgeReviewRequest, user: dict = Depends(require_permission("proposal:review"))):
    try:
        return review_proposal(proposal_id, req.status, user["id"], req.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/knowledge/unresolved")
def unresolved(limit: int = 50, _user: dict = Depends(require_permission("knowledge:inspect"))):
    return {"items": top_unresolved(limit=limit), "loop": knowledge_loop_status()}


@app.get("/api/knowledge/loop")
def loop_status(_user: dict = Depends(require_permission("knowledge:inspect"))):
    return knowledge_loop_status()


@app.post("/api/knowledge/loop/run")
async def loop_run(req: KnowledgeRunRequest, _user: dict = Depends(require_permission("knowledge:run_ai"))):
    return await run_knowledge_cycle(limit=req.limit, force=req.force)


@app.get("/api/ai/status")
def public_ai_status():
    return ai_status()


@app.get("/api/references")
def references():
    path = DATA / "references.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
