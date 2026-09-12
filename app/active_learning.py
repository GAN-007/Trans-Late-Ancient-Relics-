from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime import connect, env_bool, runtime_dir

VALID_STATUSES = {"pending", "approved", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def collection_policy() -> dict[str, Any]:
    store_images = env_bool("ESHB_ACTIVE_LEARNING_STORE_IMAGES", False)
    return {
        "enabled": env_bool("ESHB_ACTIVE_LEARNING_ENABLED", True),
        "store_images_server_side": store_images,
        "requires_explicit_image_consent": True,
        "automatic_retraining": False,
        "automatic_model_promotion": False,
        "policy": (
            "Corrections can improve evaluation and future training sets. Image bytes are stored only when the user explicitly consents AND "
            "the deployment enables ESHB_ACTIVE_LEARNING_STORE_IMAGES. Approved corrections are never allowed to replace a production model automatically."
        ),
    }


def init_active_learning_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vision_corrections(
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            machine_analysis_json TEXT NOT NULL,
            expert_correction_json TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '',
            model_version TEXT NOT NULL DEFAULT '',
            image_sha256 TEXT NOT NULL DEFAULT '',
            stored_image_path TEXT,
            image_consent INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by_user_id INTEGER REFERENCES users(id),
            review_note TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_vision_corrections_status ON vision_corrections(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_vision_corrections_user ON vision_corrections(user_id, created_at);
        """
    )
    conn.commit()
    conn.close()


def _row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "machine_analysis": json.loads(row["machine_analysis_json"]),
        "expert_correction": json.loads(row["expert_correction_json"]),
        "context": row["context"],
        "model_version": row["model_version"],
        "image_sha256": row["image_sha256"],
        "image_stored": bool(row["stored_image_path"]),
        "image_consent": bool(row["image_consent"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
        "reviewed_by_user_id": row["reviewed_by_user_id"],
        "review_note": row["review_note"],
    }


def _safe_store_image(correction_id: str, raw: bytes, mime: str) -> str:
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".bin")
    directory = runtime_dir() / "active-learning" / "images"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{correction_id}{suffix}"
    # Exclusive create prevents replacement of an earlier correction artifact.
    with path.open("xb") as handle:
        handle.write(raw)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return str(path.relative_to(runtime_dir()))


def submit_vision_correction(
    user_id: int,
    machine_analysis: dict[str, Any],
    expert_correction: dict[str, Any],
    context: str = "",
    model_version: str = "",
    image_data_url: str | None = None,
    consent_store_image: bool = False,
) -> dict[str, Any]:
    policy = collection_policy()
    if not policy["enabled"]:
        raise ValueError("Active-learning correction collection is disabled.")
    if not expert_correction:
        raise ValueError("A correction must describe at least one expert/user-proposed change.")

    correction_id = str(uuid.uuid4())
    image_sha256 = ""
    stored_path: str | None = None
    if image_data_url:
        # Import lazily to avoid a module cycle during API startup.
        from .vision import decode_image_data_url

        metadata, raw = decode_image_data_url(image_data_url)
        image_sha256 = metadata["sha256"]
        if consent_store_image and policy["store_images_server_side"]:
            stored_path = _safe_store_image(correction_id, raw, metadata["mime"])

    now = _now()
    conn = connect()
    conn.execute(
        """
        INSERT INTO vision_corrections(
            id,user_id,machine_analysis_json,expert_correction_json,context,model_version,
            image_sha256,stored_image_path,image_consent,status,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)
        """,
        (
            correction_id,
            user_id,
            json.dumps(machine_analysis, ensure_ascii=False, sort_keys=True),
            json.dumps(expert_correction, ensure_ascii=False, sort_keys=True),
            context[:4000],
            model_version[:200],
            image_sha256,
            stored_path,
            1 if consent_store_image else 0,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM vision_corrections WHERE id=?", (correction_id,)).fetchone()
    conn.close()
    result = _row(row)
    if consent_store_image and image_data_url and not policy["store_images_server_side"]:
        result["image_storage_notice"] = "Consent was recorded, but this deployment has server-side research image storage disabled; only the image hash was retained."
    return result


def list_vision_corrections(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if status and status not in VALID_STATUSES:
        raise ValueError("Invalid correction status.")
    conn = connect()
    if status:
        rows = conn.execute(
            "SELECT * FROM vision_corrections WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, max(1, min(int(limit), 500))),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM vision_corrections ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    conn.close()
    return [_row(row) for row in rows]


def review_vision_correction(correction_id: str, status: str, reviewer_user_id: int, note: str = "") -> dict[str, Any]:
    if status not in {"approved", "rejected"}:
        raise ValueError("Correction status must be approved or rejected.")
    if status == "approved" and not note.strip():
        raise ValueError("Approval requires a reviewer note describing the evidence/check performed.")
    conn = connect()
    existing = conn.execute("SELECT * FROM vision_corrections WHERE id=?", (correction_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("Correction not found.")
    if existing["status"] != "pending":
        conn.close()
        raise ValueError("Only pending corrections can be reviewed.")
    now = _now()
    conn.execute(
        "UPDATE vision_corrections SET status=?,reviewed_at=?,reviewed_by_user_id=?,review_note=? WHERE id=?",
        (status, now, reviewer_user_id, note.strip(), correction_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM vision_corrections WHERE id=?", (correction_id,)).fetchone()
    conn.close()
    return _row(row)


def approved_dataset_manifest(limit: int = 5000) -> dict[str, Any]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM vision_corrections WHERE status='approved' ORDER BY reviewed_at ASC LIMIT ?",
        (max(1, min(int(limit), 20000)),),
    ).fetchall()
    conn.close()
    items = [_row(row) for row in rows]
    return {
        "generated_at": _now(),
        "count": len(items),
        "items": items,
        "training_policy": {
            "automatic_retraining": False,
            "automatic_model_promotion": False,
            "required_before_training": [
                "license/provenance review for every retained image",
                "duplicate/leakage checks",
                "train/validation/test split by artifact or source, not random frame",
                "class-balance and annotation QA",
            ],
            "required_before_promotion": [
                "frozen benchmark evaluation",
                "per-sign precision/recall and calibration",
                "epigraphic sequence evaluation",
                "human reviewer sign-off",
                "rollback-capable deployment",
            ],
        },
    }
