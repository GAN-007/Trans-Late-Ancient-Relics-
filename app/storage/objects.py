"""Content-addressed object storage for images, datasets and model files.

Objects are stored under their SHA-256 (objects/ab/cdef…), so identical files are stored once and
any later change is detectable. Backends:
  ESHB_OBJECT_STORE=local (default)  files under ESHB_OBJECT_DIR or <runtime>/objects
  ESHB_OBJECT_STORE=s3               an S3-compatible bucket (AWS S3, MinIO, Ceph, R2): ESHB_S3_BUCKET,
                                     ESHB_S3_ENDPOINT_URL (optional), ESHB_S3_PREFIX, standard AWS credentials;
                                     needs boto3 (pip install -r requirements-postgres.txt)
An index row per object (key, sha256, size, content type, who stored it, when) lives in the database.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runtime import connect, runtime_dir

SCHEMA = """CREATE TABLE IF NOT EXISTS storage_objects (key TEXT PRIMARY KEY, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
    content_type TEXT, backend TEXT NOT NULL, purpose TEXT, created_by TEXT, created_at TEXT NOT NULL)"""
_CLIENT: Any = None  # injectable S3 client (tests)


def backend() -> str:
    return os.environ.get("ESHB_OBJECT_STORE", "local").strip().lower() or "local"


def _local_root() -> Path:
    root = Path(os.environ.get("ESHB_OBJECT_DIR") or runtime_dir() / "objects")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _s3():
    global _CLIENT
    if _CLIENT is None:
        import boto3
        _CLIENT = boto3.client("s3", endpoint_url=os.environ.get("ESHB_S3_ENDPOINT_URL") or None)
    return _CLIENT


def _bucket() -> str:
    bucket = os.environ.get("ESHB_S3_BUCKET", "")
    if not bucket:
        raise RuntimeError("ESHB_S3_BUCKET is required for ESHB_OBJECT_STORE=s3")
    return bucket


def key_for(sha: str) -> str:
    prefix = os.environ.get("ESHB_S3_PREFIX", "").strip("/") if backend() == "s3" else ""
    return "/".join(p for p in (prefix, "objects", sha[:2], sha[2:]) if p)


def put(data: bytes, content_type: str = "application/octet-stream", purpose: str = "", actor: str = "system") -> dict[str, Any]:
    sha = hashlib.sha256(data).hexdigest()
    key = key_for(sha)
    if backend() == "s3":
        _s3().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType=content_type, Metadata={"sha256": sha})
    else:
        path = _local_root() / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
    conn = connect()
    try:
        conn.execute(SCHEMA)
        conn.execute("INSERT INTO storage_objects (key,sha256,size,content_type,backend,purpose,created_by,created_at) "
                     "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (key) DO NOTHING",
                     (key, sha, len(data), content_type, backend(), purpose, actor, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        conn.commit()
    finally:
        conn.close()
    return {"key": key, "sha256": sha, "size": len(data), "backend": backend()}


def get(key: str) -> bytes:
    if ".." in key.split("/"):
        raise ValueError("invalid key")
    if backend() == "s3":
        data = _s3().get_object(Bucket=_bucket(), Key=key)["Body"].read()
    else:
        data = (_local_root() / key).read_bytes()
    sha = key.rsplit("/", 2)
    if len(sha) >= 2 and hashlib.sha256(data).hexdigest() != sha[-2] + sha[-1]:
        raise ValueError(f"Object {key} does not match its checksum: storage corruption or tampering")
    return data


def exists(key: str) -> bool:
    if backend() == "s3":
        try:
            _s3().head_object(Bucket=_bucket(), Key=key)
            return True
        except Exception:
            return False
    return (_local_root() / key).exists()


def status() -> dict[str, Any]:
    out: dict[str, Any] = {"backend": backend()}
    if backend() == "s3":
        out.update(bucket=os.environ.get("ESHB_S3_BUCKET"), endpoint=os.environ.get("ESHB_S3_ENDPOINT_URL") or "aws")
    else:
        out["path"] = str(_local_root())
    conn = connect()
    try:
        conn.execute(SCHEMA)
        conn.commit()
        row = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes FROM storage_objects").fetchone()
        out.update(objects=row["n"], bytes=row["bytes"])
    finally:
        conn.close()
    return out
