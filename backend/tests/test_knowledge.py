"""Stage 1 — scientific knowledge base."""
import json

from astra import config


def test_five_hazards_and_relationships(client):
    hz = client.get("/api/v1/hazards").json()
    assert {h["id"] for h in hz} == {"HAZ-RAD", "HAZ-ISO", "HAZ-DIST", "HAZ-GRAV", "HAZ-ENV"}
    for h in hz:
        assert h["sources"], f"{h['id']} has no source"
        assert h["risks"], f"{h['id']} has no related risks"


def test_twelve_risks_have_all_required_fields(client):
    risks = client.get("/api/v1/risks").json()
    assert len(risks) == 12
    for r in risks:
        for key in ("id", "name", "description", "hazards", "body_systems", "indicators", "measurement_methods",
                    "symptoms", "limitations", "countermeasures", "sources", "evidence_status", "approval_status"):
            assert key in r and r[key] not in (None, ""), (r["id"], key)
        assert r["sources"], r["id"]
    multi = [r for r in risks if len(r["hazards"]) > 1]
    assert multi, "risks must be allowed to relate to several hazards"


def test_challenge_indicators_present(client):
    codes = {i["code"]: i for i in client.get("/api/v1/indicators").json()}
    for c in ("bp_systolic", "bp_diastolic", "heart_rate", "blood_glucose", "body_temperature", "sleep_duration", "mood"):
        assert c in codes and codes[c]["challenge_required"], c
    assert codes["blood_glucose"]["clinician_directed"]
    assert codes["mood"]["privacy"] == "private"


def test_every_source_reference_resolves(client):
    srcs = {s["id"] for s in client.get("/api/v1/sources").json()}
    data = json.loads((config.KNOWLEDGE_DIR / "risks.json").read_text())
    for r in data:
        assert set(r["source_ids"]) <= srcs
    rules = json.loads((config.KNOWLEDGE_DIR / "rules.json").read_text())["rules"]
    for r in rules:
        assert r["source_id"] is None or r["source_id"] in srcs
        assert r["rule_class"] in ("CLINICIAN_APPROVED", "NASA_OPERATIONAL_REFERENCE", "DEMONSTRATION_ONLY")
        if r["rule_class"] == "DEMONSTRATION_ONLY":
            assert "APPROVED" not in r["approval_status"].upper().replace("NOT_VALIDATED", "")


def test_no_clinician_rule_active_without_configuration(client, auth):
    rules = client.get("/api/v1/rules", headers=auth("vega")).json()
    clin = [r for r in rules if r["rule_class"] == "CLINICIAN_APPROVED"]
    assert clin and all(not r["active"] for r in clin)


def test_protocols_are_labelled_synthetic(client, auth):
    for p in client.get("/api/v1/medical-protocols", headers=auth("vega")).json():
        assert p["approval_status"] == "SYNTHETIC_DEMO"
        assert "SYNTHETIC" in p["title"] and "SYNTHETIC" in p["disclaimer"]
