"""Crew Side / Earth Side policy: which accounts may sign in and which write operations exist on each deployment.

Enforced on the server for every request (framework) and at login; the frontend only mirrors it.
"""
from __future__ import annotations

from . import config
from .security import CREW_ROLES, EARTH_ROLES

SIDE_LABEL = {"onboard": "Crew Side — onboard spacecraft server", "earth": "Earth Side — ground operations server",
              "standalone": "Standalone prototype (all roles on one server)"}

# Earth Side: astronaut health records are created aboard and arrive by synchronization. The only write operations
# are account management and ground follow-up notes (separate, attributable records).
EARTH_WRITE_ALLOW = {
    ("POST", "/auth/login"), ("POST", "/users"), ("PATCH", "/users/{user_id}"), ("POST", "/users/{user_id}/deactivate"),
    ("POST", "/users/{user_id}/activate"), ("POST", "/users/{user_id}/password"), ("POST", "/ground/annotations"),
}
# Onboard: the legacy in-process ground-station controls are replaced by real replication and the CMO link control.
ONBOARD_WRITE_DENY = {("POST", "/sync/link"), ("POST", "/sync/{queue_id}/retry")}


def allowed_roles() -> tuple[str, ...]:
    dep = config.deployment()
    if dep == "onboard":
        return CREW_ROLES
    if dep == "earth":
        return EARTH_ROLES
    return CREW_ROLES + EARTH_ROLES


def role_allowed(role: str) -> bool:
    return role in allowed_roles()


def wrong_side_message(role: str) -> str:
    if config.deployment() == "onboard":
        return ("This is the onboard (Crew Side) ASTRA server. Earth-based accounts (administrator, ground flight "
                "surgeon) sign in at the Earth ASTRA server.")
    return ("This is the Earth Side ASTRA server. Crew accounts (astronauts, Crew Medical Officer) sign in at the "
            "onboard ASTRA server on the spacecraft network.")


def route_problem(method: str, path: str) -> tuple[int, str, str] | None:
    """(status, code, message) if this operation does not exist on this deployment, else None."""
    dep = config.deployment()
    if method == "GET":
        return None
    if dep == "earth" and (method, path) not in EARTH_WRITE_ALLOW:
        return (409, "earth_side_read_only",
                "This is the Earth Side ASTRA server: astronaut health records, assessments, alerts and medical events are "
                "created aboard the spacecraft and arrive here by synchronization. Use ground follow-up notes to respond.")
    if dep == "onboard" and (method, path) in ONBOARD_WRITE_DENY:
        return (409, "use_link_control",
                "The onboard server synchronizes with the real Earth server; the legacy simulated ground-station controls "
                "are disabled. The CMO can use the Earth-link demonstration control instead.")
    return None
