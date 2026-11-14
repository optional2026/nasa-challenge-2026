"""ASTRA runtime configuration (environment variables, paths)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge" / "data"
DATA_DIR = Path(os.environ.get("ASTRA_DATA_DIR", BACKEND_DIR / "data"))
FRONTEND_DIST = Path(os.environ.get("ASTRA_FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist"))

API_PREFIX = "/api/v1"
TOKEN_TTL_SECONDS = int(os.environ.get("ASTRA_TOKEN_TTL", 12 * 3600))
# Maximum allowed clock skew for measurements dated in the future.
FUTURE_SKEW_SECONDS = 300
# Oldest accepted measurement (pre-mission baselines are allowed).
MAX_AGE_DAYS = 730


def db_path() -> Path:
    return Path(os.environ.get("ASTRA_DB_PATH", DATA_DIR / "astra.sqlite3"))


def secret_key() -> str:
    """Signing key for session tokens.

    Read from ASTRA_SECRET_KEY, otherwise generated once and stored in the
    server data directory (never in frontend code).
    """
    env = os.environ.get("ASTRA_SECRET_KEY")
    if env:
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_file = DATA_DIR / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(48))
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    return key_file.read_text().strip()
