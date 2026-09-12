from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.environ.get("ESHB_APP_NAME", "Trans-Late Ancient Relics")
    environment: str = os.environ.get("ESHB_ENV", "development")
    runtime_dir: Path = Path(os.environ.get("ESHB_RUNTIME_DIR", PROJECT_ROOT / "data-runtime"))
    db_path: Path = Path(os.environ.get("ESHB_DB_PATH", Path(os.environ.get("ESHB_RUNTIME_DIR", PROJECT_ROOT / "data-runtime")) / "translator.sqlite3"))
    session_cookie_name: str = os.environ.get("ESHB_SESSION_COOKIE", "eshb_session")
    session_days: int = int(os.environ.get("ESHB_SESSION_DAYS", "30"))
    secure_cookies: bool = _bool("ESHB_SECURE_COOKIES", False)
    allow_registration: bool = _bool("ESHB_ALLOW_REGISTRATION", True)
    admin_email: str = os.environ.get("ESHB_ADMIN_EMAIL", "").strip().lower()
    admin_password: str = os.environ.get("ESHB_ADMIN_PASSWORD", "")
    admin_name: str = os.environ.get("ESHB_ADMIN_NAME", "Administrator")
    ai_endpoint: str = os.environ.get("ESHB_AI_ENDPOINT", "").strip()
    ai_api_key: str = os.environ.get("ESHB_AI_API_KEY", "").strip()
    vision_endpoint: str = os.environ.get("ESHB_VISION_ENDPOINT", "").strip()
    vision_api_key: str = os.environ.get("ESHB_VISION_API_KEY", "").strip()
    ai_timeout_seconds: float = float(os.environ.get("ESHB_AI_TIMEOUT_SECONDS", "30"))
    auto_research_enabled: bool = _bool("ESHB_AUTO_RESEARCH_ENABLED", False)
    auto_research_interval_hours: float = float(os.environ.get("ESHB_AUTO_RESEARCH_INTERVAL_HOURS", "24"))
    auto_research_min_frequency: int = int(os.environ.get("ESHB_AUTO_RESEARCH_MIN_FREQUENCY", "3"))
    live_frame_interval_ms: int = int(os.environ.get("ESHB_LIVE_FRAME_INTERVAL_MS", "1500"))
    max_image_bytes: int = int(os.environ.get("ESHB_MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))


settings = Settings()
settings.runtime_dir.mkdir(parents=True, exist_ok=True)

ROLE_ORDER = {
    "guest": 0,
    "learner": 10,
    "contributor": 20,
    "reviewer": 30,
    "admin": 40,
}
VALID_ROLES = tuple(ROLE_ORDER)
