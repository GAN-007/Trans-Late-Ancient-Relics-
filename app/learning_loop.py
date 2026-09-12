from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .ai import ai_status, propose_lexicon_entry
from .knowledge import (
    create_proposal,
    get_state,
    mark_ai_proposed,
    set_state,
    top_unresolved,
)
from .runtime import env_bool, env_int

STATE_KEY = "knowledge_loop_last_run"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def knowledge_loop_status() -> dict[str, Any]:
    interval_hours = env_int("ESHB_KNOWLEDGE_LOOP_HOURS", 24, minimum=1, maximum=720)
    last = _parse_iso(get_state(STATE_KEY))
    next_run = last + timedelta(hours=interval_hours) if last else None
    return {
        "enabled": env_bool("ESHB_KNOWLEDGE_LOOP_ENABLED", False),
        "interval_hours": interval_hours,
        "last_run": last.isoformat() if last else None,
        "next_run": next_run.isoformat() if next_run else None,
        "ai": ai_status(),
        "policy": "AI may draft proposals from unresolved terms; only a reviewer/admin can approve them into the runtime lexicon.",
    }


async def run_knowledge_cycle(limit: int = 5, force: bool = False) -> dict[str, Any]:
    status = ai_status()
    if not status["configured"]:
        return {"ok": False, "created": [], "message": "AI provider is not configured.", "status": knowledge_loop_status()}

    interval_hours = env_int("ESHB_KNOWLEDGE_LOOP_HOURS", 24, minimum=1, maximum=720)
    last = _parse_iso(get_state(STATE_KEY))
    now = datetime.now(timezone.utc)
    if not force and last and now < last + timedelta(hours=interval_hours):
        return {"ok": True, "created": [], "message": "Knowledge cycle is not due yet.", "status": knowledge_loop_status()}

    unresolved = top_unresolved(limit=max(1, min(limit, 20)), only_without_ai_proposal=True)
    created = []
    errors = []
    for item in unresolved:
        try:
            draft = await propose_lexicon_entry(item["term"], item["source_language"], item.get("example_context", ""))
            if not draft.get("transliteration"):
                mark_ai_proposed(item["source_language"], item["term"])
                errors.append({"term": item["term"], "reason": draft.get("rationale", "No responsible candidate.")})
                continue
            payload = {
                "transliteration": draft["transliteration"],
                "english": draft.get("english", []),
                "swahili": draft.get("swahili", []),
                "pos": draft.get("pos", "unknown"),
                "notes": (
                    f"AI draft for review. {draft.get('notes', '')} "
                    f"Evidence still required: {draft.get('evidence_needed', '')}"
                ).strip(),
                "confidence": draft.get("confidence", "low") if draft.get("confidence") in {"low","medium","high"} else "low",
            }
            proposal = create_proposal(
                kind="lexicon",
                payload=payload,
                evidence=f"Unresolved term '{item['term']}' seen {item['occurrences']} time(s). AI rationale: {draft.get('rationale', '')}",
                origin="ai",
                confidence=0.5,
            )
            mark_ai_proposed(item["source_language"], item["term"])
            created.append(proposal)
        except Exception as exc:
            errors.append({"term": item["term"], "reason": str(exc)})
    set_state(STATE_KEY, now.isoformat())
    return {"ok": True, "created": created, "errors": errors, "status": knowledge_loop_status()}


async def background_loop(stop_event: asyncio.Event) -> None:
    # Sleep in modest increments so shutdown is responsive. The actual due check lives in run_knowledge_cycle.
    while not stop_event.is_set():
        try:
            await run_knowledge_cycle(limit=env_int("ESHB_KNOWLEDGE_LOOP_BATCH", 5, minimum=1, maximum=20), force=False)
        except Exception:
            # Background enrichment must never take the application down.
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=900)
        except asyncio.TimeoutError:
            continue
