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


def public_demo() -> bool:
    """Public demonstration mode (rate limits, locked configuration). Set by tools/start_public_demo.*"""
    return os.environ.get("ASTRA_PUBLIC_DEMO") == "1"


def demo_password() -> str:
    """Password for the synthetic Earth-side demo accounts (administrator, flight surgeon).
    Override with ASTRA_DEMO_PASSWORD (recommended when public)."""
    return os.environ.get("ASTRA_DEMO_PASSWORD") or "astra-demo"


def crew_demo_password() -> str:
    """SHARED DEMONSTRATION password for the three pre-created crew accounts (vega, okafor, mori).
    Only ever stored as a scrypt hash; never sent to the frontend. Must be changed before any real deployment
    (override with ASTRA_CREW_DEMO_PASSWORD before the database is first created, or reset each account
    through User management)."""
    return os.environ.get("ASTRA_CREW_DEMO_PASSWORD") or "optionalwillwin"


# ---------------------------------------------------------------- deployment side (Crew Side / Earth Side)
DEPLOYMENTS = ("standalone", "onboard", "earth")


def deployment() -> str:
    """Which side of ASTRA this server instance is.

    * ``onboard``    — Crew Side: the spacecraft server (astronauts + CMO). Saves records locally first and forwards
                       them to Earth through the persistent replication outbox.
    * ``earth``      — Earth Side: ground operations (administrators + ground flight surgeons). Receives records from
                       the onboard server; does not create astronaut health records itself.
    * ``standalone`` — legacy single-server prototype (every role on one server, in-process simulated ground
                       station). Default, so existing installs and tests keep working.
    """
    v = (os.environ.get("ASTRA_DEPLOYMENT") or "standalone").strip().lower()
    if v not in DEPLOYMENTS:
        raise RuntimeError(f"ASTRA_DEPLOYMENT must be one of {DEPLOYMENTS}, got {v!r}")
    return v


def node_id() -> str:
    """Stable identifier of this server instance (used as replication origin / peer identity)."""
    default = {"onboard": "ONBOARD-1", "earth": "EARTH-1"}.get(deployment(), "STANDALONE-1")
    return os.environ.get("ASTRA_NODE_ID") or default


def earth_url() -> str | None:
    """Onboard only: base URL of the Earth ASTRA server, e.g. https://ground.example:8443 (no trailing /api)."""
    v = os.environ.get("ASTRA_EARTH_URL")
    return v.rstrip("/") if v else None


def sync_key() -> str | None:
    """Pre-shared server-to-server key (HMAC-SHA256). The SAME value must be configured on the onboard server and
    on the Earth server. Read from ASTRA_SYNC_KEY or from the file named by ASTRA_SYNC_KEY_FILE. Never sent over
    the wire and never exposed to browsers."""
    v = os.environ.get("ASTRA_SYNC_KEY")
    if v:
        return v
    f = os.environ.get("ASTRA_SYNC_KEY_FILE")
    if f and Path(f).exists():
        return Path(f).read_text().strip() or None
    return None


def sync_peer_id() -> str:
    """Earth only: node id of the onboard server that is allowed to deliver records."""
    return os.environ.get("ASTRA_SYNC_PEER_ID") or "ONBOARD-1"


def sync_peer_mission() -> str | None:
    """Earth only: the mission whose records the onboard peer may deliver (records of other missions are refused)."""
    return os.environ.get("ASTRA_SYNC_PEER_MISSION") or None


def sync_interval() -> float:
    return float(os.environ.get("ASTRA_SYNC_INTERVAL", "3"))


def sync_ca_bundle() -> str | None:
    """Optional CA bundle used to verify the Earth server's TLS certificate."""
    return os.environ.get("ASTRA_SYNC_CA_BUNDLE") or None


def sync_allow_insecure() -> bool:
    """Allow plain HTTP to a NON-loopback Earth server. Off by default: replication must use HTTPS unless both
    servers run on the same machine (demonstration)."""
    return os.environ.get("ASTRA_SYNC_ALLOW_INSECURE") == "1"


def allow_link_simulation() -> bool:
    """DEMONSTRATION feature: lets the CMO simulate loss of the onboard↔Earth link. Disabled unless explicitly
    enabled for an authorised test/demonstration environment with ASTRA_ALLOW_LINK_SIMULATION=1."""
    return os.environ.get("ASTRA_ALLOW_LINK_SIMULATION") == "1"
