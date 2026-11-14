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


# ------------------------------------------------------------------ authorization helpers
def can_view_astronaut(p: Principal, astronaut_id: str | None) -> bool:
    """Standard (non-private) health data of one astronaut."""
    if astronaut_id is None:  # environment data — visible to all users
        return p.kind in ("user", "system")
    if p.kind == "system":
        return True
    if p.role in MEDICAL_ROLES:
        return True
    if p.role == "astronaut":
        return p.astronaut_id == astronaut_id
    return False  # admin: system administration only, no medical data


def can_view_private(p: Principal, astronaut_id: str | None) -> bool:
    """Private behavioral-health content: the astronaut themself and the flight surgeon.

    The onboard medical officer sees that a private item exists (redacted) but
    not its content, unless it is their own record.
    """
    if p.kind == "system":
        return True
    if p.role == "flight_surgeon":
        return True
    if p.role in ("astronaut", "medical_officer") and astronaut_id is not None:
        return p.astronaut_id == astronaut_id
    return False


def can_see_private_exists(p: Principal, astronaut_id: str | None) -> bool:
    return can_view_private(p, astronaut_id) or p.role == "medical_officer"


REDACTED = "[PRIVATE — restricted to the astronaut and the flight surgeon]"
