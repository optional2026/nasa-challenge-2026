"""Append-only audit log helper."""
from __future__ import annotations

from typing import Any

from . import db
from .security import Principal


def record(conn, actor: Principal | str, action: str, entity_type: str, entity_id: str | None,
           details: dict[str, Any] | None = None) -> None:
    if isinstance(actor, Principal):
        name, role = actor.actor, actor.role
    else:
        name, role = actor, None
    db.insert(conn, "audit_log", {
        "at": db.now_iso(), "actor": name, "actor_role": role, "action": action,
        "entity_type": entity_type, "entity_id": entity_id, "details": db.dumps(details or {}),
    })
