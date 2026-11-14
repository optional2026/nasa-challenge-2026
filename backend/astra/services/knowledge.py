"""Scientific knowledge base: loads the traceable JSON knowledge files into the
relational schema and answers queries about hazards, risks, indicators,
countermeasures, sources, rules and procedures."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .. import config, db


def _load(name: str) -> Any:
    return json.loads((config.KNOWLEDGE_DIR / name).read_text(encoding="utf-8"))


def seed_knowledge(conn) -> dict[str, int]:
    """Idempotent upsert of the knowledge base. Returns counts per entity."""
    sources = _load("sources.json")
    hazards = _load("hazards.json")
    risks = _load("risks.json")
    ind = _load("indicators.json")
    cms = _load("countermeasures.json")
    protocols = _load("protocols.json")
    rules = _load("rules.json")["rules"]
    symptoms = _load("symptoms.json")
    with db.transaction(conn):
        for s in sources:
            conn.execute("INSERT OR REPLACE INTO evidence_sources VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (s["id"], s["title"], s.get("publisher"), s.get("document_id"), s.get("url"), s.get("year"),
                          s["source_type"], s["verification_status"], s.get("accessed_date"), s.get("notes")))
        for h in hazards:
            conn.execute("INSERT OR REPLACE INTO hazard_definitions VALUES (?,?,?,?)",
                         (h["id"], h["name"], h["description"], h.get("monitoring_role")))
            conn.execute("DELETE FROM hazard_sources WHERE hazard_id=?", (h["id"],))
            for sid in h["source_ids"]:
                conn.execute("INSERT INTO hazard_sources VALUES (?,?)", (h["id"], sid))
        scales = ind["scales"]
        for i in ind["indicators"]:
            conn.execute(
                "INSERT OR REPLACE INTO health_indicators VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (i["code"], i["name"], i["category"], i["subject"], i["value_type"], i["canonical_unit"],
                 db.dumps(i["allowed_units"]), i.get("plausible_min"), i.get("plausible_max"), i.get("body_system"),
                 int(i.get("challenge_required", False)), i.get("privacy", "standard"),
                 int(i.get("clinician_only", False)), int(i.get("clinician_directed", False)),
                 i.get("description"), i.get("measurement_instructions"), i.get("limitations"),
                 db.dumps(scales.get(i["code"])) if i["code"] in scales else None))
        for c in cms:
            conn.execute("INSERT OR REPLACE INTO countermeasures VALUES (?,?,?,?)",
                         (c["id"], c["name"], c["description"], c["approval_status"]))
            conn.execute("DELETE FROM countermeasure_sources WHERE countermeasure_id=?", (c["id"],))
            for sid in c["source_ids"]:
                conn.execute("INSERT INTO countermeasure_sources VALUES (?,?)", (c["id"], sid))
        for r in risks:
            conn.execute("INSERT OR REPLACE INTO risk_definitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (r["id"], r["name"], r.get("nasa_risk_title"), r["description"], db.dumps(r["body_systems"]),
                          db.dumps(r["measurement_methods"]), db.dumps(r["symptoms"]), db.dumps(r["limitations"]),
                          r["evidence_status"], r["approval_status"], r.get("privacy", "standard"),
                          r.get("specialized_assessment_note")))
            for t in ("risk_hazard_relationships", "risk_sources", "risk_indicators", "risk_countermeasures"):
                conn.execute(f"DELETE FROM {t} WHERE risk_id=?", (r["id"],))
            for h in r["hazards"]:
                conn.execute("INSERT INTO risk_hazard_relationships VALUES (?,?,?)", (r["id"], h["hazard_id"], h["rationale"]))
            for sid in r["source_ids"]:
                conn.execute("INSERT INTO risk_sources VALUES (?,?)", (r["id"], sid))
            for code in r["indicator_codes"]:
                conn.execute("INSERT INTO risk_indicators VALUES (?,?)", (r["id"], code))
            for cid in r["countermeasure_ids"]:
                conn.execute("INSERT INTO risk_countermeasures VALUES (?,?)", (r["id"], cid))
        for s in symptoms:
            conn.execute("INSERT OR REPLACE INTO symptom_vocabulary VALUES (?,?,?)", (s["code"], s["label"], db.dumps(s["risk_ids"])))
        for p in protocols:
            conn.execute("INSERT OR REPLACE INTO medical_protocols VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (p["id"], p["version"], p["title"], p["approval_status"], p["disclaimer"],
                          db.dumps(p["applies_to_rules"]), db.dumps(p["applies_to_risks"]),
                          db.dumps(p["verification_checklist"]), db.dumps(p["steps"]), db.dumps(p["escalation"]),
                          p.get("source_id")))
        for r in rules:
            conn.execute("INSERT OR REPLACE INTO assessment_rules VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (r["id"], r["version"], r["name"], r["rule_class"], r["approval_status"], int(r["active"]),
                          db.dumps(r["metrics"]), r["evaluation_method"], db.dumps(r["params"]),
                          db.dumps(r["context_filter"]), r["severity"], db.dumps(r["risk_ids"]), r.get("protocol_id"),
                          r.get("source_id"), r.get("effective_date"), db.dumps(r["escalation"]), r["description"],
                          int(r.get("private", False))))
    indicators.cache_clear()
    return {"sources": len(sources), "hazards": len(hazards), "risks": len(risks),
            "indicators": len(ind["indicators"]), "countermeasures": len(cms), "protocols": len(protocols),
            "rules": len(rules), "symptoms": len(symptoms)}


# ------------------------------------------------------------------ cached registries (read from JSON source of truth)
@lru_cache(maxsize=1)
def indicators() -> dict[str, dict]:
    data = _load("indicators.json")
    out = {}
    for i in data["indicators"]:
        i = dict(i)
        i["scale_labels"] = data["scales"].get(i["code"])
        out[i["code"]] = i
    return out


@lru_cache(maxsize=1)
def symptom_codes() -> dict[str, dict]:
    return {s["code"]: s for s in _load("symptoms.json")}


# ------------------------------------------------------------------ queries
def _decode_risk(conn, r: dict) -> dict:
    rid = r["id"]
    r = dict(r)
    for k in ("body_systems", "measurement_methods", "symptoms", "limitations"):
        r[k] = db.loads(r[k], [])
    r["hazards"] = db.all_(conn, """SELECT h.id AS hazard_id, h.name, rh.rationale FROM risk_hazard_relationships rh
                                   JOIN hazard_definitions h ON h.id=rh.hazard_id WHERE rh.risk_id=? ORDER BY h.id""", (rid,))
    r["indicators"] = [x["indicator_code"] for x in db.all_(conn, "SELECT indicator_code FROM risk_indicators WHERE risk_id=?", (rid,))]
    r["countermeasures"] = db.all_(conn, """SELECT c.* FROM risk_countermeasures rc JOIN countermeasures c ON c.id=rc.countermeasure_id
                                           WHERE rc.risk_id=?""", (rid,))
    r["sources"] = db.all_(conn, """SELECT s.* FROM risk_sources rs JOIN evidence_sources s ON s.id=rs.source_id
                                    WHERE rs.risk_id=?""", (rid,))
    return r


def list_risks(conn, body_system: str | None = None, hazard_id: str | None = None) -> list[dict]:
    rows = db.all_(conn, "SELECT * FROM risk_definitions ORDER BY id")
    out = [_decode_risk(conn, r) for r in rows]
    if body_system:
        out = [r for r in out if body_system in r["body_systems"]]
    if hazard_id:
        out = [r for r in out if any(h["hazard_id"] == hazard_id for h in r["hazards"])]
    return out


def get_risk(conn, risk_id: str) -> dict | None:
    r = db.one(conn, "SELECT * FROM risk_definitions WHERE id=?", (risk_id,))
    return _decode_risk(conn, r) if r else None


def list_hazards(conn) -> list[dict]:
    out = []
    for h in db.all_(conn, "SELECT * FROM hazard_definitions ORDER BY id"):
        h = dict(h)
        h["risks"] = db.all_(conn, """SELECT r.id, r.name, rh.rationale FROM risk_hazard_relationships rh
                                      JOIN risk_definitions r ON r.id=rh.risk_id WHERE rh.hazard_id=? ORDER BY r.id""", (h["id"],))
        h["sources"] = db.all_(conn, """SELECT s.* FROM hazard_sources hs JOIN evidence_sources s ON s.id=hs.source_id
                                        WHERE hs.hazard_id=?""", (h["id"],))
        out.append(h)
    return out


def list_countermeasures(conn) -> list[dict]:
    out = []
    for c in db.all_(conn, "SELECT * FROM countermeasures ORDER BY id"):
        c = dict(c)
        c["risk_ids"] = [x["risk_id"] for x in db.all_(conn, "SELECT risk_id FROM risk_countermeasures WHERE countermeasure_id=?", (c["id"],))]
        c["sources"] = db.all_(conn, """SELECT s.* FROM countermeasure_sources cs JOIN evidence_sources s ON s.id=cs.source_id
                                        WHERE cs.countermeasure_id=?""", (c["id"],))
        out.append(c)
    return out


def list_indicators(conn) -> list[dict]:
    rows = db.all_(conn, "SELECT * FROM health_indicators ORDER BY category, code")
    for r in rows:
        r["allowed_units"] = db.loads(r["allowed_units"], [])
        r["scale_labels"] = db.loads(r["scale_labels"])
        r["risk_ids"] = [x["risk_id"] for x in db.all_(conn, "SELECT risk_id FROM risk_indicators WHERE indicator_code=?", (r["code"],))]
        for k in ("challenge_required", "clinician_only", "clinician_directed"):
            r[k] = bool(r[k])
    return rows


def decode_protocol(p: dict | None) -> dict | None:
    if not p:
        return None
    p = dict(p)
    for k in ("applies_to_rules", "applies_to_risks", "verification_checklist", "steps", "escalation"):
        p[k] = db.loads(p[k], [])
    return p


def get_protocol(conn, protocol_id: str, version: int | None = None) -> dict | None:
    if version is None:
        p = db.one(conn, "SELECT * FROM medical_protocols WHERE id=? ORDER BY version DESC LIMIT 1", (protocol_id,))
    else:
        p = db.one(conn, "SELECT * FROM medical_protocols WHERE id=? AND version=?", (protocol_id, version))
    return decode_protocol(p)


def decode_rule(r: dict) -> dict:
    r = dict(r)
    for k in ("metrics", "params", "context_filter", "risk_ids", "escalation"):
        r[k] = db.loads(r[k], {} if k in ("params", "context_filter", "escalation") else [])
    r["active"] = bool(r["active"])
    r["private"] = bool(r["private"])
    return r


def active_rules(conn) -> list[dict]:
    rows = db.all_(conn, """SELECT r.* FROM assessment_rules r
                            JOIN (SELECT id, MAX(version) v FROM assessment_rules GROUP BY id) m ON m.id=r.id AND m.v=r.version
                            WHERE r.active=1 ORDER BY r.id""")
    return [decode_rule(r) for r in rows]


def all_rules(conn) -> list[dict]:
    return [decode_rule(r) for r in db.all_(conn, "SELECT * FROM assessment_rules ORDER BY id, version")]
