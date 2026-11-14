"""Persistent medical event lifecycle (state machine with audited transitions).

DETECTED → VERIFYING → ACTIVE → ESCALATED → MONITORING → RESOLVED
A medical event never disappears because an alert was acknowledged or dismissed.
"""
from __future__ import annotations

from .. import audit, db
from ..bus import BUS
from ..security import MEDICAL_ROLES, Principal
from . import knowledge

STATES = ("DETECTED", "VERIFYING", "ACTIVE", "ESCALATED", "MONITORING", "RESOLVED")
TRANSITIONS: dict[str, set[str]] = {
    "DETECTED": {"VERIFYING", "ESCALATED"},
    "VERIFYING": {"ACTIVE", "ESCALATED", "RESOLVED"},
    "ACTIVE": {"ESCALATED", "MONITORING"},
    "ESCALATED": {"ACTIVE", "MONITORING"},
    "MONITORING": {"ACTIVE", "ESCALATED", "RESOLVED"},
    "RESOLVED": {"ACTIVE"},  # re-open with reason
}
REASON_REQUIRED = {"RESOLVED", "ESCALATED"}
MEDICAL_ONLY = {"RESOLVED"}


class TransitionError(ValueError):
    pass


def _publish(conn, event_id: str, kind: str) -> None:
    e = db.one(conn, "SELECT * FROM medical_events WHERE id=?", (event_id,))
    BUS.publish(kind, {"id": event_id, "state": e["state"], "severity": e["severity"], "title": e["title"]},
                astronaut_id=e["astronaut_id"], private=bool(e["is_private"]))


def create(conn, actor: Principal | str, *, astronaut_id, mission_id, title, category, risk_id, severity,
           protocol_id=None, private=False, synthetic=False, sim_run_id=None) -> str:
    eid = db.new_id("EVT")
    now = db.now_iso()
    proto = knowledge.get_protocol(conn, protocol_id) if protocol_id else None
    actor_name = actor.actor if isinstance(actor, Principal) else actor
    with db.transaction(conn):
        db.insert(conn, "medical_events", {
            "id": eid, "astronaut_id": astronaut_id, "mission_id": mission_id, "title": title, "category": category,
            "risk_id": risk_id, "state": "DETECTED", "severity": severity,
            "protocol_id": proto["id"] if proto else None, "protocol_version": proto["version"] if proto else None,
            "opened_at": now, "updated_at": now, "resolved_at": None, "is_private": int(private),
            "is_synthetic": int(synthetic), "sim_run_id": sim_run_id})
        db.insert(conn, "medical_event_transitions", {"event_id": eid, "from_state": None, "to_state": "DETECTED",
                                                      "actor": actor_name, "reason": "Created by assessment engine", "at": now})
        audit.record(conn, actor, "medical_event.create", "medical_event", eid, {"severity": severity, "title": title})
    _publish(conn, eid, "medical_event.created")
    return eid


def transition(conn, actor: Principal, event_id: str, to_state: str, reason: str | None) -> dict:
    e = db.one(conn, "SELECT * FROM medical_events WHERE id=?", (event_id,))
    if not e:
        raise LookupError(event_id)
    frm = e["state"]
    if to_state not in TRANSITIONS.get(frm, set()):
        raise TransitionError(f"invalid transition {frm} → {to_state}; allowed: {sorted(TRANSITIONS[frm]) or 'none'}")
    if to_state in REASON_REQUIRED and not (reason and reason.strip()):
        raise TransitionError(f"a reason is required to move to {to_state}")
    if frm == "RESOLVED" and not (reason and reason.strip()):
        raise TransitionError("a reason is required to re-open a resolved event")
    if to_state in MEDICAL_ONLY and actor.role not in MEDICAL_ROLES:
        raise PermissionError("only the medical officer or flight surgeon can resolve a medical event")
    now = db.now_iso()
    with db.transaction(conn):
        db.update(conn, "medical_events", "id", event_id, {
            "state": to_state, "updated_at": now, "resolved_at": now if to_state == "RESOLVED" else None})
        db.insert(conn, "medical_event_transitions", {"event_id": event_id, "from_state": frm, "to_state": to_state,
                                                      "actor": actor.actor, "reason": reason, "at": now})
        audit.record(conn, actor, "medical_event.transition", "medical_event", event_id,
                     {"from": frm, "to": to_state, "reason": reason})
    _publish(conn, event_id, "medical_event.updated")
    return get(conn, event_id)


def add_action(conn, actor: Principal | str, event_id: str, action_type: str, description: str,
               data: dict | None = None) -> dict:
    e = db.one(conn, "SELECT id FROM medical_events WHERE id=?", (event_id,))
    if not e:
        raise LookupError(event_id)
    aid = db.new_id("ACT")
    actor_name = actor.actor if isinstance(actor, Principal) else actor
    with db.transaction(conn):
        db.insert(conn, "medical_event_actions", {"id": aid, "event_id": event_id, "action_type": action_type,
                                                  "description": description, "performed_by": actor_name,
                                                  "performed_at": db.now_iso(), "data": db.dumps(data or {})})
        conn.execute("UPDATE medical_events SET updated_at=? WHERE id=?", (db.now_iso(), event_id))
        audit.record(conn, actor, "medical_event.action", "medical_event", event_id,
                     {"action_id": aid, "type": action_type})
    _publish(conn, event_id, "medical_event.updated")
    return db.one(conn, "SELECT * FROM medical_event_actions WHERE id=?", (aid,))


def get(conn, event_id: str) -> dict | None:
    e = db.one(conn, "SELECT * FROM medical_events WHERE id=?", (event_id,))
    if not e:
        return None
    e = dict(e)
    e["is_private"] = bool(e["is_private"])
    e["is_synthetic"] = bool(e["is_synthetic"])
    e["transitions"] = db.all_(conn, "SELECT * FROM medical_event_transitions WHERE event_id=? ORDER BY id", (event_id,))
    acts = db.all_(conn, "SELECT * FROM medical_event_actions WHERE event_id=? ORDER BY performed_at", (event_id,))
    for a in acts:
        a["data"] = db.loads(a["data"], {})
    e["actions"] = acts
    e["allowed_transitions"] = sorted(TRANSITIONS[e["state"]])
    e["protocol"] = knowledge.get_protocol(conn, e["protocol_id"], e["protocol_version"]) if e["protocol_id"] else None
    alerts = db.all_(conn, "SELECT id, severity, title, rule_id, created_at, ack_status, escalation_status, resolution_status "
                           "FROM alerts WHERE medical_event_id=? ORDER BY created_at", (event_id,))
    e["alerts"] = alerts
    obs_ids = [r["observation_id"] for r in db.all_(conn, """SELECT DISTINCT ao.observation_id FROM alert_observations ao
                 JOIN alerts a ON a.id=ao.alert_id WHERE a.medical_event_id=?""", (event_id,))]
    obs_ids += [a["data"].get("observation_id") for a in acts if a["action_type"] == "observation_link" and a["data"].get("observation_id")]
    e["observation_ids"] = list(dict.fromkeys(obs_ids))
    checked = {a["data"].get("item") for a in acts if a["action_type"] == "checklist_item" and a["data"].get("checked")}
    if e["protocol"]:
        e["checklist_status"] = [{"item": it, "checked": it in checked} for it in e["protocol"]["verification_checklist"]]
    else:
        e["checklist_status"] = []
    e["reports"] = db.all_(conn, "SELECT id, created_at, created_by, sync_status FROM medical_reports WHERE event_id=? "
                                 "ORDER BY created_at", (event_id,))
    return e


def open_for_alert_rule(conn, astronaut_id, rule_id) -> dict | None:
    return db.one(conn, """SELECT e.* FROM medical_events e JOIN alerts a ON a.medical_event_id=e.id
                           WHERE a.rule_id=? AND (a.astronaut_id IS ? OR a.astronaut_id=?) AND e.state!='RESOLVED'
                           ORDER BY e.opened_at DESC LIMIT 1""", (rule_id, astronaut_id, astronaut_id))
