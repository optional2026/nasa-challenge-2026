"""Authentication, role-based authorization and privacy rules.

Prototype-level controls (see docs/SECURITY.md):
* passwords hashed with scrypt (stdlib) and per-user salt,
* HMAC-SHA256 signed session tokens (PyJWT) with expiry,
* device API keys stored only as SHA-256 hashes,
* role checks on every endpoint, privacy filtering for behavioral-health data.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

import jwt

from . import config

ROLES = ("astronaut", "medical_officer", "flight_surgeon", "admin")
MEDICAL_ROLES = ("medical_officer", "flight_surgeon")
# Aboard the spacecraft (have a personal astronaut health record) vs. Earth-based personnel (no personal record).
CREW_ROLES = ("astronaut", "medical_officer")
EARTH_ROLES = ("flight_surgeon", "admin")
# Every role signs in with a username and password (scrypt hash, never returned by the API).
# Roles an administrator may create/assign through user management.
ADMIN_ASSIGNABLE_ROLES = CREW_ROLES

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
_COMMON_PASSWORDS = {"password", "password1", "12345678", "123456789", "1234567890", "qwerty123", "letmein1",
                     "astronaut", "iloveyou", "11111111", "00000000", "abcdefgh", "changeme", "welcome1"}


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def password_problems(password: str, username: str | None = None) -> list[str]:
    """Server-side password policy for new and reset passwords. Returns human-readable problems (empty = OK)."""
    probs = []
    if len(password) < PASSWORD_MIN_LENGTH:
        probs.append(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        probs.append(f"password must be at most {PASSWORD_MAX_LENGTH} characters")
    if password.strip() != password or not password.strip():
        probs.append("password must not start or end with whitespace")
    if len(set(password)) < 4:
        probs.append("password must contain at least 4 different characters")
    if password.lower() in _COMMON_PASSWORDS:
        probs.append("password is too common")
    if username and password.lower() == username.lower():
        probs.append("password must not be the same as the username")
    return probs


# ------------------------------------------------------------------ device keys
def new_device_key() -> str:
    return "astra_dev_" + secrets.token_urlsafe(24)


def hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ------------------------------------------------------------------ principals
@dataclass
class Principal:
    kind: str  # 'user' | 'device' | 'system'
    name: str
    role: str  # user role, 'device' or 'system'
    user_id: int | None = None
    astronaut_id: str | None = None
    device_id: str | None = None
    mission_id: str | None = None
    display_name: str = ""
    extra: dict = field(default_factory=dict)
    # Crew Medical Officer only: astronaut ids in the same mission + crew (resolved at authentication).
    crew_astronaut_ids: frozenset = field(default_factory=frozenset)
    # Earth-based roles: astronaut ids on the mission(s) the account is assigned to (resolved at authentication).
    # None = no mission restriction (an administrator with no mission assignment oversees every mission).
    scope_astronaut_ids: frozenset | None = None

    @property
    def is_medical(self) -> bool:
        return self.role in MEDICAL_ROLES

    @property
    def actor(self) -> str:
        return f"{self.kind}:{self.name}"


SYSTEM = Principal(kind="system", name="astra-engine", role="system")


def issue_token(user: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user["id"]), "username": user["username"], "role": user["role"],
        "astronaut_id": user.get("astronaut_id"), "iat": now, "exp": now + config.TOKEN_TTL_SECONDS,
        "iss": "astra",
    }
    return jwt.encode(payload, config.secret_key(), algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, config.secret_key(), algorithms=["HS256"], issuer="astra")


def crew_astronaut_ids(conn, astronaut_id: str | None) -> frozenset:
    """Astronauts assigned to the same mission and crew as `astronaut_id` (including itself)."""
    if not astronaut_id:
        return frozenset()
    rows = conn.execute("""SELECT b.id FROM astronauts a JOIN astronauts b
                           ON b.mission_id=a.mission_id AND b.crew=a.crew WHERE a.id=?""", (astronaut_id,)).fetchall()
    return frozenset(r["id"] for r in rows)


def mission_astronaut_ids(conn, mission_id: str | None) -> frozenset:
    if not mission_id:
        return frozenset()
    return frozenset(r["id"] for r in conn.execute("SELECT id FROM astronauts WHERE mission_id=?", (mission_id,)).fetchall())


def user_principal(conn, user: dict) -> Principal:
    """Build the request principal for an active user row (shared by HTTP and WebSocket auth)."""
    mission_id = None
    scope = None
    if user["astronaut_id"]:
        a = conn.execute("SELECT mission_id FROM astronauts WHERE id=?", (user["astronaut_id"],)).fetchone()
        mission_id = a["mission_id"] if a else None
    elif user["role"] in EARTH_ROLES:
        mission_id = user.get("mission_id")
        if user["role"] == "flight_surgeon":
            # Ground flight surgeon: ONLY the assigned mission (no assignment = no astronaut access).
            scope = mission_astronaut_ids(conn, mission_id)
        elif mission_id:
            scope = mission_astronaut_ids(conn, mission_id)
    crew = crew_astronaut_ids(conn, user["astronaut_id"]) if user["role"] == "medical_officer" else frozenset()
    return Principal(kind="user", name=user["username"], role=user["role"], user_id=user["id"],
                     astronaut_id=user["astronaut_id"], mission_id=mission_id,
                     display_name=user["display_name"], crew_astronaut_ids=crew, scope_astronaut_ids=scope)


def in_earth_scope(p: Principal, astronaut_id: str) -> bool:
    return p.scope_astronaut_ids is None or astronaut_id in p.scope_astronaut_ids


# ------------------------------------------------------------------ authorization helpers
def can_view_astronaut(p: Principal, astronaut_id: str | None) -> bool:
    """Standard (non-private) health data of one astronaut."""
    if astronaut_id is None:  # environment data — visible to all users
        return p.kind in ("user", "system")
    if p.kind == "system":
        return True
    if p.role == "flight_surgeon":  # ground medical oversight of the ASSIGNED mission only
        return in_earth_scope(p, astronaut_id)
    if p.role == "admin":
        # Earth-based mission administrator: READ-ONLY view of the crew's non-private health records.
        # Every write path (ingestion, records, medication, history, baselines, alert/event actions)
        # rejects the admin role separately, and private behavioral-health content stays hidden
        # (can_view_private / can_see_private_exists are False for admin). Limited to the assigned mission
        # when the administrator account has one.
        return in_earth_scope(p, astronaut_id)
    if p.role == "medical_officer":  # own record + astronauts assigned to the CMO's crew
        return p.astronaut_id == astronaut_id or astronaut_id in p.crew_astronaut_ids
    if p.role == "astronaut":
        return p.astronaut_id == astronaut_id
    return False


def can_view_private(p: Principal, astronaut_id: str | None) -> bool:
    """Private behavioral-health content: the astronaut themself and the flight surgeon.

    The onboard medical officer sees that a private item exists (redacted) but
    not its content, unless it is their own record.
    """
    if p.kind == "system":
        return True
    if p.role == "flight_surgeon":
        return astronaut_id is not None and in_earth_scope(p, astronaut_id)
    if p.role in ("astronaut", "medical_officer") and astronaut_id is not None:
        return p.astronaut_id == astronaut_id
    return False


def can_see_private_exists(p: Principal, astronaut_id: str | None) -> bool:
    return can_view_private(p, astronaut_id) or (p.role == "medical_officer" and can_view_astronaut(p, astronaut_id))


REDACTED = "[PRIVATE — restricted to the astronaut and the flight surgeon]"
