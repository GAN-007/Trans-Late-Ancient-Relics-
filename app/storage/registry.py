"""Model registry: every vision or language model the platform may use, with provenance and gates.

A model file is stored in the object store (content-addressed) and registered as a numbered
version with its dataset, licence, metrics and model card. Status moves
candidate -> approved -> deployed -> retired; approval requires metrics from a benchmark-eligible
dataset with a recorded licence and meets the minimum scores, and only one version per name is
deployed at a time. Every change is written to the audit log.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runtime import connect, runtime_dir
from . import audit, objects

SCHEMA = """CREATE TABLE IF NOT EXISTS model_registry (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, version INTEGER NOT NULL,
    task TEXT, sha256 TEXT NOT NULL, object_key TEXT NOT NULL, size INTEGER NOT NULL, dataset TEXT, license TEXT,
    metrics TEXT, card TEXT, status TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL, approved_by TEXT,
    approved_at TEXT, deployed_at TEXT, UNIQUE (name, version))"""
STATUSES = ("candidate", "approved", "deployed", "retired")
TRANSITIONS = {"candidate": {"approved", "retired"}, "approved": {"deployed", "retired"}, "deployed": {"retired"}, "retired": set()}
DEFAULT_GATES = {"top1": 0.80, "expected_calibration_error": 0.10}


class RegistryError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure(conn) -> None:
    conn.execute(SCHEMA)
    conn.commit()


def _row(r) -> dict[str, Any]:
    out = dict(r)
    for key in ("metrics", "card"):
        out[key] = json.loads(out[key]) if out.get(key) else {}
    return out


def register(name: str, path: str, metrics: dict[str, Any] | None = None, dataset: str | None = None, license: str | None = None,
             card: dict[str, Any] | None = None, task: str = "sign-classification", actor: str = "system") -> dict[str, Any]:
    data = Path(path).read_bytes()
    stored = objects.put(data, "application/octet-stream", purpose=f"model:{name}", actor=actor)
    conn = connect()
    try:
        _ensure(conn)
        row = conn.execute("SELECT COALESCE(MAX(version),0) AS v FROM model_registry WHERE name=?", (name,)).fetchone()
        version = int(row["v"]) + 1
        cur = conn.execute("INSERT INTO model_registry (name,version,task,sha256,object_key,size,dataset,license,metrics,card,status,"
                           "created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (name, version, task, stored["sha256"], stored["key"], stored["size"], dataset, license,
                            json.dumps(metrics or {}, default=str), json.dumps(card or {}, default=str, ensure_ascii=False),
                            "candidate", actor, _now()))
        model_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    audit.record(actor, "model.register", f"{name}@{version}", {"sha256": stored["sha256"], "dataset": dataset, "license": license})
    return get(model_id)


def get(model_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        _ensure(conn)
        row = conn.execute("SELECT * FROM model_registry WHERE id=?", (model_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise RegistryError(f"No model {model_id}")
    return _row(row)


def list_models(name: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        _ensure(conn)
        rows = conn.execute("SELECT * FROM model_registry" + (" WHERE name=?" if name else "") + " ORDER BY name, version DESC",
                            ((name,) if name else ())).fetchall()
    finally:
        conn.close()
    return [_row(r) for r in rows]


def promote(model_id: int, status: str, actor: str, gates: dict[str, float] | None = None) -> dict[str, Any]:
    from ..vision_bench import DATASETS
    model = get(model_id)
    if status not in STATUSES:
        raise RegistryError(f"status must be one of {', '.join(STATUSES)}")
    if status not in TRANSITIONS[model["status"]]:
        raise RegistryError(f"Cannot move a {model['status']} model to {status}")
    if status == "approved":
        gates = gates or DEFAULT_GATES
        problems = []
        dataset = DATASETS.get(model.get("dataset") or "")
        if not dataset or not dataset.get("benchmark_eligible"):
            problems.append(f"dataset '{model.get('dataset')}' is not a benchmark-eligible, licensed dataset")
        if not model.get("license"):
            problems.append("no licence recorded")
        metrics = model.get("metrics") or {}
        for metric, floor in gates.items():
            value = metrics.get(metric)
            if value is None:
                problems.append(f"missing metric {metric}")
            elif metric == "expected_calibration_error" and value > floor:
                problems.append(f"{metric} {value} is above {floor}")
            elif metric != "expected_calibration_error" and value < floor:
                problems.append(f"{metric} {value} is below {floor}")
        if problems:
            audit.record(actor, "model.approve_refused", f"{model['name']}@{model['version']}", {"problems": problems})
            raise RegistryError("Approval refused: " + "; ".join(problems))
    conn = connect()
    try:
        _ensure(conn)
        if status == "deployed":
            conn.execute("UPDATE model_registry SET status='retired' WHERE name=? AND status='deployed'", (model["name"],))
            conn.execute("UPDATE model_registry SET status=?, deployed_at=? WHERE id=?", (status, _now(), model_id))
        elif status == "approved":
            conn.execute("UPDATE model_registry SET status=?, approved_by=?, approved_at=? WHERE id=?", (status, actor, _now(), model_id))
        else:
            conn.execute("UPDATE model_registry SET status=? WHERE id=?", (status, model_id))
        conn.commit()
    finally:
        conn.close()
    audit.record(actor, f"model.{status}", f"{model['name']}@{model['version']}", {"sha256": model["sha256"]})
    if status == "deployed":
        materialize(model_id)
    return get(model_id)


def materialize(model_id: int) -> Path:
    """Write the deployed model file to <runtime>/models/active/<name>.onnx after checking its hash."""
    model = get(model_id)
    data = objects.get(model["object_key"])
    target = runtime_dir() / "models" / "active" / f"{model['name']}.onnx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def deployed(name: str) -> dict[str, Any] | None:
    return next((m for m in list_models(name) if m["status"] == "deployed"), None)
