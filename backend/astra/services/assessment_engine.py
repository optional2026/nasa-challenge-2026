"""ASTRA assessment engine.

1. receive validated observations          6. evaluate symptoms and context
2. retrieve the astronaut profile           7. identify missing / unreliable data
3. retrieve the applicable baselines        8. produce an explainable assessment
4. retrieve relevant risk definitions       9. create alerts / events when appropriate
5. evaluate configured (versioned) rules   10. store the assessment result

Rules come only from the centralized rule configuration (assessment_rules).
No thresholds are hard-coded here; numeric parameters live in the rule rows.
"""
from __future__ import annotations

import statistics
from datetime import timedelta
from typing import Any, Callable

from .. import db
from ..bus import BUS
from ..security import SYSTEM
from . import alerts as alert_svc
from . import baselines, knowledge, medical_events, trends

SEV = alert_svc.SEVERITY_ORDER
STATUS_FOR = {0: "NO_CONCERN_IDENTIFIED", 1: "INFORMATION", 2: "REASSESSMENT_RECOMMENDED",
              3: "MEDICAL_REVIEW_RECOMMENDED", 4: "URGENT_PROCEDURE"}
NEXT_STEP = {
    "NO_CONCERN_IDENTIFIED": "Continue the scheduled monitoring routine.",
    "INSUFFICIENT_DATA": "Complete the missing measurements or ask medical personnel to approve a baseline; no conclusion can be drawn yet.",
    "INFORMATION": "Review the information; no action is required unless symptoms appear.",
    "REASSESSMENT_RECOMMENDED": "Verify the measurement and repeat it following the configured reassessment procedure.",
    "MEDICAL_REVIEW_RECOMMENDED": "Inform the Crew Medical Officer; the finding requires review by authorized medical personnel.",
    "URGENT_PROCEDURE": "Open the Medical Response Center now and follow the applicable approved procedure.",
}
DEMO_LIMITATION = "Finding produced by a DEMONSTRATION-ONLY synthetic rule — not a NASA-approved or clinically validated threshold."


# ------------------------------------------------------------------ helpers
def _ind_name(code: str) -> str:
    return knowledge.indicators().get(code, {}).get("name", code)


def _unit(code: str) -> str:
    return knowledge.indicators().get(code, {}).get("canonical_unit", "")


def _recent(conn, astronaut_id, metric, end_iso, hours, valid_only=True, location=None):
    start = db.iso(db.parse_iso(end_iso) - timedelta(hours=hours))
    return trends.series(conn, astronaut_id, metric, start=start, end=end_iso, valid_only=valid_only, location=location)


def _baseline_ctx(b: dict, value: float | None = None) -> dict:
    ctx = {"baseline_id": b["id"], "baseline_version": b["version"], "mean": b["mean"], "sd": b["sd"], "n": b["n"],
           "approved_by": b["approved_by"], "approved_at": b["approved_at"], "source": b["source"],
           "period": [b["period_start"], b["period_end"]]}
    if value is not None:
        ctx["latest_value"] = value
        ctx["latest_z"] = round(trends.zscore(value, b), 2)
    return ctx


def _finding(rule, *, metric, severity=None, title, finding, explanation, evidence, baseline=None,
             symptoms=None, category="health", dedup_suffix="", astronaut_id=None, finding_only=False,
             limitations=None) -> dict:
    sev = severity or rule["severity"]
    status = STATUS_FOR[SEV[sev]]
    lims = list(limitations or [])
    if rule["rule_class"] == "DEMONSTRATION_ONLY":
        lims.append(DEMO_LIMITATION)
    return {"rule": rule, "metric": metric, "severity": sev, "title": title, "finding": finding,
            "explanation": explanation, "evidence": evidence, "baseline_comparison": baseline or {},
            "symptoms": symptoms or [], "category": category, "risk_ids": rule["risk_ids"],
            "private": rule.get("private", False), "finding_only": finding_only or rule["escalation"].get("finding_only", False),
            "dedup_key": f"{astronaut_id or 'ENV'}|{rule['id']}|{metric}{dedup_suffix}",
            "next_step": NEXT_STEP[status] if not rule.get("protocol_id") else NEXT_STEP[status] + f" (procedure {rule['protocol_id']})",
            "limitations": lims}


def _ctx_ok(rule: dict, metric: str, obs: dict) -> bool:
    cf = rule["context_filter"].get(metric)
    if not cf:
        return True
    ctx = db.loads(obs["context"], {}) if isinstance(obs.get("context"), str) else (obs.get("context") or {})
    for key, allowed in cf.items():
        if ctx.get(key) not in allowed:
            return False
    return True


def _consecutive(values_z: list[tuple[dict, float]], k: float, direction: str = "either") -> tuple[int, int]:
    """Count consecutive most-recent observations beyond k SD in the same direction. Returns (count, sign)."""
    if not values_z:
        return 0, 0
    sign = 1 if values_z[-1][1] > 0 else -1
    if direction == "high":
        sign = 1
    elif direction == "low":
        sign = -1
    c = 0
    for _, z in reversed(values_z):
        if abs(z) > k and (1 if z > 0 else -1) == sign:
            c += 1
        else:
            break
    return c, sign


# ------------------------------------------------------------------ evaluators
def ev_baseline_sustained(conn, rule, ast, metrics, obs, anchor):
    out, p = [], rule["params"]
    for m in metrics & set(rule["metrics"]):
        b = baselines.approved(conn, ast, m, baselines.context_key_for(m, {}))
        if not b:
            continue
        rows = [r for r in _recent(conn, ast, m, anchor, p["window_hours"]) if _ctx_ok(rule, m, r)]
        rows = [r for r in rows if baselines.context_key_for(m, db.loads(r["context"], {})) == b["context_key"]]
        vz = [(r, trends.zscore(r["value_num"], b)) for r in rows if r["value_num"] is not None]
        count, sign = _consecutive(vz, p["k_sd"])
        if count >= p["min_consecutive"]:
            sev = p["escalate_severity"] if count >= p.get("escalate_consecutive", 10**9) else rule["severity"]
            ev = [r["id"] for r, _ in vz[-count:]]
            latest = vz[-1][0]["value_num"]
            word = "above" if sign > 0 else "below"
            out.append(_finding(rule, metric=m, severity=sev, astronaut_id=ast,
                                title=f"{_ind_name(m)}: sustained deviation from individual baseline",
                                finding="Sustained deviation from individual baseline",
                                explanation=(f"The last {count} valid {_ind_name(m).lower()} measurements are {word} the approved "
                                             f"baseline ({b['mean']:.1f} ± {b['sd']:.1f} {_unit(m)}, v{b['version']}) by more than "
                                             f"{p['k_sd']} SD. Latest value {latest:.1f} {_unit(m)}."),
                                evidence=ev, baseline=_baseline_ctx(b, latest)))
    return out


def ev_rapid_change(conn, rule, ast, metrics, obs, anchor):
    out, p = [], rule["params"]
    for m in metrics & set(rule["metrics"]):
        b = baselines.approved(conn, ast, m, baselines.context_key_for(m, {}))
        if not b:
            continue
        rows = [r for r in _recent(conn, ast, m, anchor, 24) if _ctx_ok(rule, m, r) and r["value_num"] is not None]
        rows = [r for r in rows if baselines.context_key_for(m, db.loads(r["context"], {})) == b["context_key"]]
        if len(rows) < 2:
            continue
        a, c = rows[-2], rows[-1]
        gap = (db.parse_iso(c["measured_at"]) - db.parse_iso(a["measured_at"])).total_seconds() / 60
        delta = c["value_num"] - a["value_num"]
        if gap <= p["max_gap_minutes"] and abs(delta) / trends.effective_sd(b) > p["k_sd"]:
            out.append(_finding(rule, metric=m, astronaut_id=ast,
                                title=f"{_ind_name(m)}: rapid change — verify measurement",
                                finding="Rapid change between consecutive observations",
                                explanation=(f"{_ind_name(m)} changed by {delta:+.1f} {_unit(m)} within {gap:.0f} min "
                                             f"(more than {p['k_sd']} baseline SD). Check the device and repeat the measurement."),
                                evidence=[a["id"], c["id"]], baseline=_baseline_ctx(b, c["value_num"])))
    return out


def ev_quality_flag(conn, rule, ast, metrics, obs, anchor):
    out = []
    for r in obs:
        if r["quality"] in rule["params"]["qualities"]:
            out.append(_finding(rule, metric=r["metric_code"], astronaut_id=ast or r.get("location"),
                                dedup_suffix=f"|{r['id']}",
                                title=f"{_ind_name(r['metric_code'])}: measurement quality questionable",
                                finding="Measurement quality questionable — not interpreted",
                                explanation=("This measurement was marked questionable by the device or the user. ASTRA does not "
                                             "interpret it as abnormal or normal. Repeat the measurement."),
                                evidence=[r["id"]], category="data"))
    return out


def ev_combo_cardioresp(conn, rule, ast, metrics, obs, anchor):
    p = rule["params"]
    if not (metrics & {"heart_rate", "spo2", "symptom", "respiratory_rate"}):
        return []
    bh = baselines.approved(conn, ast, "heart_rate", "resting")
    bs = baselines.approved(conn, ast, "spo2", "")
    if not bh or not bs:
        return []
    hrs = p["window_minutes"] / 60
    hr = [r for r in _recent(conn, ast, "heart_rate", anchor, hrs) if r["value_num"] is not None]
    sp = [r for r in _recent(conn, ast, "spo2", anchor, hrs) if r["value_num"] is not None]
    sy = [r for r in _recent(conn, ast, "symptom", anchor, hrs, valid_only=False) if r["value_text"] in p["symptoms"]]
    if not hr or not sp or not sy:
        return []
    hr_last, sp_last = hr[-1], sp[-1]
    zh, zs = trends.zscore(hr_last["value_num"], bh), trends.zscore(sp_last["value_num"], bs)
    if zh > p["k_sd"] and zs < -p["k_sd"]:
        rr = [r for r in _recent(conn, ast, "respiratory_rate", anchor, hrs) if r["value_num"] is not None]
        ev = [hr_last["id"], sp_last["id"]] + [s["id"] for s in sy] + ([rr[-1]["id"]] if rr else [])
        syms = sorted({s["value_text"] for s in sy})
        return [_finding(rule, metric="cardiorespiratory", astronaut_id=ast,
                         title="Combined heart-rate, SpO2 and symptom finding",
                         finding="Heart rate high and SpO2 low relative to baseline, with reported symptoms",
                         explanation=(f"Heart rate {hr_last['value_num']:.0f} bpm (baseline {bh['mean']:.0f} ± {bh['sd']:.1f}, z={zh:+.1f}) and "
                                      f"SpO2 {sp_last['value_num']:.0f}% (baseline {bs['mean']:.1f} ± {bs['sd']:.1f}, z={zs:+.1f}) "
                                      f"together with reported symptoms: {', '.join(syms)}. Open the approved procedure and verify "
                                      f"measurements with independent devices."),
                         evidence=ev, symptoms=syms,
                         baseline={"heart_rate": _baseline_ctx(bh, hr_last["value_num"]),
                                   "spo2": _baseline_ctx(bs, sp_last["value_num"])})]
    return []


def ev_temp_with_symptoms(conn, rule, ast, metrics, obs, anchor):
    p = rule["params"]
    if not (metrics & {"body_temperature", "symptom"}):
        return []
    b = baselines.approved(conn, ast, "body_temperature", "")
    if not b:
        return []
    temps = [r for r in _recent(conn, ast, "body_temperature", anchor, p["window_hours"]) if r["value_num"] is not None]
    vz = [(r, trends.zscore(r["value_num"], b)) for r in temps]
    count, sign = _consecutive(vz, p["k_sd"], "high")
    sy = [r for r in _recent(conn, ast, "symptom", anchor, p["window_hours"], valid_only=False) if r["value_text"] in p["symptoms"]]
    if count >= p["min_consecutive"] and sy:
        syms = sorted({s["value_text"] for s in sy})
        first = min(s["measured_at"] for s in sy)
        latest = vz[-1][0]["value_num"]
        return [_finding(rule, metric="body_temperature", astronaut_id=ast,
                         title="Temperature above personal baseline with illness symptoms",
                         finding="Temperature deviation with reported illness symptoms",
                         explanation=(f"{count} consecutive temperatures above baseline {b['mean']:.2f} ± {b['sd']:.2f} °C "
                                      f"(latest {latest:.2f} °C) and symptoms reported since {first[:16].replace('T', ' ')} UTC: "
                                      f"{', '.join(syms)}. This does not establish infection or immune dysfunction; medical review is recommended."),
                         evidence=[r["id"] for r, _ in vz[-count:]] + [s["id"] for s in sy], symptoms=syms,
                         baseline=_baseline_ctx(b, latest),
                         limitations=["Temperature and symptoms alone cannot establish immune dysfunction; laboratory data would be required."])]
    return []


def ev_symptom_review(conn, rule, ast, metrics, obs, anchor):
    out = []
    for r in obs:
        hit = (r["metric_code"] == "symptom" and r["value_text"] in rule["params"]["symptoms"]) or \
              (r["metric_code"] == "vision_change" and r["value_bool"] == 1)
        if hit:
            code = r["value_text"] if r["metric_code"] == "symptom" else "vision_change"
            out.append(_finding(rule, metric="vision", astronaut_id=ast,
                                title="Reported vision change — clinician eye examination recommended",
                                finding="Vision symptom reported",
                                explanation=("A vision-related symptom was reported. A questionnaire cannot diagnose SANS; "
                                             "a clinician-performed eye examination (and imaging when available) is recommended."),
                                evidence=[r["id"]], symptoms=[code],
                                limitations=["SANS cannot be diagnosed from self-report."]))
    return out[:1]


def ev_sleep_sustained(conn, rule, ast, metrics, obs, anchor):
    p = rule["params"]
    if not (metrics & {"sleep_duration", "fatigue"}):
        return []
    b = baselines.approved(conn, ast, "sleep_duration", "")
    if not b:
        return []
    rows = [r for r in _recent(conn, ast, "sleep_duration", anchor, 24 * 10) if r["value_num"] is not None]
    vz = [(r, trends.zscore(r["value_num"], b)) for r in rows]
    count, _ = _consecutive(vz, p["k_sd"], "low")
    if count < p["min_consecutive"]:
        return []
    fat = [r for r in _recent(conn, ast, "fatigue", anchor, 36) if r["value_num"] is not None]
    high_fatigue = bool(fat) and fat[-1]["value_num"] >= p["fatigue_min"]
    sev = rule["severity"] if high_fatigue else p["severity_without_fatigue"]
    mins = [r["value_num"] for r, _ in vz[-count:]]
    return [_finding(rule, metric="sleep_duration", severity=sev, astronaut_id=ast,
                     title="Sleep shorter than personal baseline for consecutive periods",
                     finding="Sustained short sleep relative to baseline" + (" with high self-reported fatigue" if high_fatigue else ""),
                     explanation=(f"The last {count} sleep periods ({', '.join(f'{m/60:.1f} h' for m in mins)}) were below the "
                                  f"personal baseline {b['mean']/60:.1f} ± {b['sd']/60:.1f} h by more than {p['k_sd']} SD."
                                  + (" Self-reported fatigue is also high (details are private)." if high_fatigue else "")),
                     evidence=[r["id"] for r, _ in vz[-count:]] + ([fat[-1]["id"]] if high_fatigue else []),
                     baseline=_baseline_ctx(b, mins[-1]))]


def ev_behavioral_trend(conn, rule, ast, metrics, obs, anchor):
    p = rule["params"]
    if not (metrics & {"mood", "stress"}):
        return []
    bm, bs = baselines.approved(conn, ast, "mood", ""), baselines.approved(conn, ast, "stress", "")
    if not bm or not bs:
        return []
    moods = [r for r in _recent(conn, ast, "mood", anchor, 24 * p["days"], valid_only=False) if r["value_num"] is not None]
    stresses = [r for r in _recent(conn, ast, "stress", anchor, 24 * p["days"], valid_only=False) if r["value_num"] is not None]
    if len(moods) < p["min_entries"] or len(stresses) < p["min_entries"]:
        return []
    mm, ms = statistics.fmean(r["value_num"] for r in moods), statistics.fmean(r["value_num"] for r in stresses)
    if mm <= bm["mean"] - p["mood_drop"] and ms >= bs["mean"] + p["stress_rise"]:
        return [_finding(rule, metric="behavioral", astronaut_id=ast,
                         title="Private: self-reported mood and stress trend",
                         finding="Self-reported mood lower and stress higher than personal baseline",
                         explanation=(f"Over the last {p['days']} days, average self-reported mood {mm:.1f} (baseline {bm['mean']:.1f}) "
                                      f"and stress {ms:.1f} (baseline {bs['mean']:.1f}). These are self-reported indicators, not a "
                                      f"diagnosis. A private medical conference is recommended."),
                         evidence=[r["id"] for r in moods + stresses],
                         baseline={"mood": _baseline_ctx(bm, mm), "stress": _baseline_ctx(bs, ms)},
                         limitations=["Self-reported scores are not psychiatric diagnoses."])]
    return []


def ev_note_to_medical(conn, rule, ast, metrics, obs, anchor):
    out = []
    for r in obs:
        ctx = db.loads(r["context"], {})
        if r["metric_code"] == "mood" and ctx.get("has_note_for_medical"):
            out.append(_finding(rule, metric="note", astronaut_id=ast, dedup_suffix=f"|{ctx.get('mood_assessment_id')}",
                                title="Private note for medical support",
                                finding="The astronaut left a private note for medical support",
                                explanation="Open the private check-in record to read the note (visible only to authorized personnel).",
                                evidence=[r["id"]]))
    return out


def ev_exercise_adherence(conn, rule, ast, metrics, obs, anchor):
    p = rule["params"]
    if "exercise_session" not in metrics:
        return []
    start = db.iso(db.parse_iso(anchor) - timedelta(days=p["days"]))
    recs = db.all_(conn, "SELECT * FROM exercise_records WHERE astronaut_id=? AND start_at>=? AND start_at<=? "
                         "AND category!='performance_test'", (ast, start, anchor))
    planned = len(recs)
    if planned < p["min_planned"]:
        return []
    done = sum(1.0 if r["completion_status"] == "completed" else 0.5 if r["completion_status"] == "partial" else 0 for r in recs)
    ratio = done / planned
    if ratio < p["min_ratio"]:
        return [_finding(rule, metric="exercise_session", astronaut_id=ast,
                         title="Exercise sessions completed below plan",
                         finding=f"{ratio:.0%} of planned exercise sessions completed in {p['days']} days",
                         explanation=(f"{done:g} of {planned} logged sessions completed. Exercise adherence is NOT a measurement of "
                                      f"bone density; a specialized bone assessment is required to evaluate bone health."),
                         evidence=[r["observation_id"] for r in recs if r["observation_id"]],
                         limitations=["Adherence does not measure bone density or muscle mass."])]
    return []


def ev_performance_decline(conn, rule, ast, metrics, obs, anchor):
    p, out = rule["params"], []
    if "physical_performance" not in metrics:
        return out
    tests = {db.loads(r["context"], {}).get("test") for r in obs if r["metric_code"] == "physical_performance"}
    for test in filter(None, tests):
        b = baselines.approved(conn, ast, "physical_performance", test)
        if not b:
            continue
        rows = trends.series(conn, ast, "physical_performance", end=anchor, context_key=test, valid_only=True)
        vz = [(r, trends.zscore(r["value_num"], b)) for r in rows[-10:]]
        count, _ = _consecutive(vz, p["k_sd"], "low")
        if count >= p["min_consecutive"]:
            out.append(_finding(rule, metric=f"physical_performance:{test}", astronaut_id=ast,
                                title=f"Physical performance ({test}) below personal baseline",
                                finding="Physical performance decline relative to baseline",
                                explanation=(f"The last {count} '{test}' results are below baseline {b['mean']:.1f} ± {b['sd']:.1f} "
                                             f"by more than {p['k_sd']} SD. A specialized musculoskeletal assessment is recommended; "
                                             f"ASTRA cannot measure bone density from performance data."),
                                evidence=[r["id"] for r, _ in vz[-count:]], baseline=_baseline_ctx(b, vz[-1][0]["value_num"])))
    return out


def ev_daily_total_low(conn, rule, ast, metrics, obs, anchor):
    p = rule["params"]
    if "water_intake" not in metrics:
        return []
    b = baselines.approved(conn, ast, "water_intake", "daily_total")
    if not b:
        return []
    today = anchor[:10]
    rows = _recent(conn, ast, "water_intake", anchor, 24 * (p["min_days"] + 2), valid_only=False)
    totals = baselines.daily_totals([r for r in rows if r["measured_at"][:10] < today])
    days = sorted(totals)[-p["min_days"]:]
    if len(days) < p["min_days"]:
        return []
    zs = [trends.zscore(totals[d], b) for d in days]
    if all(z < -p["k_sd"] for z in zs):
        return [_finding(rule, metric="water_intake", astronaut_id=ast,
                         title="Daily water intake below personal baseline",
                         finding=f"Water intake below baseline for {len(days)} complete days",
                         explanation=(f"Daily totals {', '.join(f'{totals[d]:.0f} mL' for d in days)} vs personal baseline "
                                      f"{b['mean']:.0f} ± {b['sd']:.0f} mL. Logging may be incomplete. Hydration data cannot diagnose "
                                      f"kidney stones."),
                         evidence=[r["id"] for r in rows if r["measured_at"][:10] in days],
                         baseline=_baseline_ctx(b, totals[days[-1]]))]
    return []


def ev_schedule_reference(conn, rule, ast, metrics, obs, anchor):
    out = []
    for r in obs:
        if r["metric_code"] == "sleep_opportunity" and r["value_num"] is not None and r["value_num"] < rule["params"]["reference_minutes"]:
            out.append(_finding(rule, metric="sleep_opportunity", astronaut_id=ast, finding_only=True,
                                title="Scheduled sleep opportunity shorter than NASA 8.5 h scheduling reference",
                                finding="Scheduling note",
                                explanation=(f"Scheduled sleep opportunity {r['value_num']/60:.1f} h is shorter than the 8.5 h sleep "
                                             f"period recommended for crew scheduling in NASA-STD-3001 Vol. 1 [V1 6001] rationale. "
                                             f"This is a scheduling reference, not a diagnosis."),
                                evidence=[r["id"]]))
    return out[:1]


def ev_reference_range(conn, rule, ast, metrics, obs, anchor):
    out = []
    for m in metrics & set(rule["metrics"]):
        b = baselines.approved(conn, ast, m, baselines.context_key_for(m, {}))
        if not b or b["ref_low"] is None or not b["ref_approved_by"]:
            continue
        rows = [r for r in _recent(conn, ast, m, anchor, 72) if r["value_num"] is not None][-rule["params"]["min_consecutive"]:]
        if len(rows) == rule["params"]["min_consecutive"] and all(not (b["ref_low"] <= r["value_num"] <= b["ref_high"]) for r in rows):
            out.append(_finding(rule, metric=m, astronaut_id=ast,
                                title=f"{_ind_name(m)} outside clinician-approved reference range",
                                finding="Outside clinician-approved individual reference range",
                                explanation=f"Range {b['ref_low']}–{b['ref_high']} {_unit(m)} approved by {b['ref_approved_by']}.",
                                evidence=[r["id"] for r in rows], baseline=_baseline_ctx(b, rows[-1]["value_num"])))
    return out


# ---- environmental
def ev_rolling_average_limit(conn, rule, ast, metrics, obs, anchor):
    from . import environment
    p, out = rule["params"], []
    if ast is not None:
        return out
    for m in metrics & set(rule["metrics"]):
        for loc in sorted({r.get("location") for r in obs if r["metric_code"] == m}):
            rows = _recent(conn, None, m, anchor, p["window_minutes"] / 60, valid_only=True, location=loc)
            vals = [r["value_num"] for r in rows if r["value_num"] is not None]
            if len(vals) < p["min_samples"]:
                continue
            avg = statistics.fmean(vals)
            exceeded = avg > p["limit"]
            environment.track_event(conn, rule=rule, event_type=f"{m}_above_limit", location=loc, active=exceeded,
                                    value=avg, unit=_unit(m), obs_ids=[r["id"] for r in rows], anchor=anchor,
                                    description=(f"{_ind_name(m)} 1-hour average {avg:.2f} {_unit(m)} above the NASA-STD-3001 "
                                                 f"V2 [6004] habitat limit of {p['limit']} {p['unit']}."))
            if exceeded:
                out.append(_finding(rule, metric=f"{m}:{loc}", category="environment",
                                    title=f"Cabin CO2 1-hour average above NASA habitat limit ({loc})",
                                    finding="Environmental limit exceeded",
                                    explanation=(f"1-hour average ppCO2 {avg:.2f} mmHg in {loc} exceeds the NASA-STD-3001 Volume 2 "
                                                 f"[V2 6004] limit of {p['limit']} mmHg (average 1-hour ppCO2 in the habitable volume). "
                                                 f"This is an environmental reading, not a medical measurement. Individual sensitivity "
                                                 f"varies; report any headache or symptoms."),
                                    evidence=[r["id"] for r in rows],
                                    limitations=["Environmental sensor reading; does not measure an astronaut directly."]))
    return out


def ev_radiation_spike(conn, rule, ast, metrics, obs, anchor):
    from . import environment
    p, out = rule["params"], []
    if ast is not None or "radiation_dose_rate" not in metrics:
        return out
    for loc in sorted({r.get("location") for r in obs if r["metric_code"] == "radiation_dose_rate"}):
        rows = _recent(conn, None, "radiation_dose_rate", anchor, p["trailing_hours"], valid_only=True, location=loc)
        if len(rows) < p["min_trailing_samples"] + 1:
            continue
        latest = rows[-1]
        cutoff = db.iso(db.parse_iso(anchor) - timedelta(hours=1))
        trailing = [r["value_num"] for r in rows if r["measured_at"] < cutoff]
        if len(trailing) < p["min_trailing_samples"]:
            continue
        med = statistics.median(trailing)
        active = med > 0 and latest["value_num"] >= p["factor"] * med
        environment.track_event(conn, rule=rule, event_type="radiation_event", location=loc, active=active,
                                value=latest["value_num"], unit="uGy/h", obs_ids=[latest["id"]], anchor=anchor,
                                description=(f"Radiation dose rate {latest['value_num']:.1f} µGy/h ≥ {p['factor']}× trailing "
                                             f"24 h median ({med:.1f} µGy/h) at {loc}."), track_peak=True)
        if active:
            out.append(_finding(rule, metric=f"radiation_dose_rate:{loc}", category="environment",
                                title=f"Radiation dose rate elevated ({loc})",
                                finding="Elevated radiation dose rate (environmental event)",
                                explanation=(f"Dose rate {latest['value_num']:.1f} µGy/h is {latest['value_num']/med:.1f}× the trailing "
                                             f"24 h median ({med:.1f} µGy/h). Verify with other dosimeters and follow the mission "
                                             f"radiation-event procedure. Exposure records are not a diagnosis."),
                                evidence=[latest["id"]],
                                limitations=["Absorbed dose rate from an area monitor; not a medical measurement."]))
    return out


def ev_missing_data(conn, rule, ast, metrics, obs, anchor):
    """Evaluated only for scheduled (full) assessments."""
    return []


EVALUATORS: dict[str, Callable] = {
    "baseline_sustained_deviation": ev_baseline_sustained, "rapid_change": ev_rapid_change,
    "quality_flag": ev_quality_flag, "combo_cardiorespiratory": ev_combo_cardioresp,
    "temp_with_symptoms": ev_temp_with_symptoms, "symptom_review": ev_symptom_review,
    "sleep_sustained": ev_sleep_sustained, "behavioral_trend": ev_behavioral_trend,
    "note_to_medical": ev_note_to_medical, "exercise_adherence": ev_exercise_adherence,
    "performance_decline": ev_performance_decline, "daily_total_low": ev_daily_total_low,
    "schedule_reference": ev_schedule_reference, "reference_range": ev_reference_range,
    "rolling_average_limit": ev_rolling_average_limit, "radiation_spike": ev_radiation_spike,
    "missing_data": ev_missing_data,
}


# ------------------------------------------------------------------ main entry
def missing_data_findings(conn, astronaut_id: str, anchor: str) -> list[dict]:
    rule = next((r for r in knowledge.active_rules(conn) if r["evaluation_method"] == "missing_data"), None)
    if not rule:
        return []
    out = []
    for t in db.all_(conn, "SELECT * FROM assessment_schedule WHERE astronaut_id=? AND active=1 AND required=1", (astronaut_id,)):
        codes = db.loads(t["metric_codes"], [])
        last = db.one(conn, f"SELECT MAX(measured_at) m FROM observations WHERE astronaut_id=? AND metric_code IN "
                            f"({','.join('?' * len(codes))})", (astronaut_id, *codes))["m"]
        limit_h = t["interval_hours"] * rule["params"]["grace_factor"]
        age_h = None if not last else (db.parse_iso(anchor) - db.parse_iso(last)).total_seconds() / 3600
        if age_h is None or age_h > limit_h:
            out.append(_finding(rule, metric=t["task_code"], astronaut_id=astronaut_id, finding_only=True,
                                title=f"Missing data: {t['title']}",
                                finding="Scheduled measurement missing — status unknown (not healthy)",
                                explanation=(f"No {t['title'].lower()} recorded " + ("ever." if not last else f"for {age_h:.0f} h "
                                             f"(scheduled every {t['interval_hours']:g} h).")),
                                evidence=[]))
    return out


EVENT_ONLY_METHODS = {"rapid_change", "quality_flag", "symptom_review", "note_to_medical", "schedule_reference"}


def assess(conn, *, astronaut_id: str | None, mission_id: str, trigger: str, observations: list[dict],
           sim_run_id: str | None = None, include_missing: bool = False, anchor: str | None = None) -> dict:
    metrics = {o["metric_code"] for o in observations}
    anchor = anchor or max((o["measured_at"] for o in observations), default=db.now_iso())
    rules = knowledge.active_rules(conn)
    findings: list[dict] = []
    limitations: list[str] = []
    evaluated: dict[str, int] = {}
    for rule in rules:
        if rule["metrics"] != ["*"] and not (set(rule["metrics"]) & metrics) and not include_missing:
            continue
        fn = EVALUATORS.get(rule["evaluation_method"])
        if include_missing and rule["evaluation_method"] in EVENT_ONLY_METHODS:
            continue
        if not fn:
            continue
        evaluated[rule["id"]] = rule["version"]
        findings.extend(fn(conn, rule, astronaut_id, metrics, observations, anchor))
    if include_missing and astronaut_id:
        findings.extend(missing_data_findings(conn, astronaut_id, anchor))

    # baseline availability and data quality limitations
    comparisons = {}
    insufficient = False
    if astronaut_id:
        for m in sorted(metrics):
            ind = knowledge.indicators().get(m, {})
            if ind.get("value_type") not in ("numeric", "ordinal") or m in ("sleep_opportunity",):
                continue
            ck = baselines.context_key_for(m, {})
            b = baselines.approved(conn, astronaut_id, m, ck)
            latest = next((o for o in reversed(observations) if o["metric_code"] == m and o.get("value_num") is not None), None)
            if b and latest and m not in baselines.DAILY_TOTAL_METRICS:
                comparisons[m] = _baseline_ctx(b, latest["value_num"])
            elif not b:
                limitations.append(f"No approved individual baseline for {_ind_name(m)} — comparison not possible.")
                insufficient = True
    for o in observations:
        if o["quality"] != "valid":
            limitations.append(f"{_ind_name(o['metric_code'])} observation {o['id']} quality is '{o['quality']}'.")
    for f in findings:
        limitations.extend(f["limitations"])
    limitations = list(dict.fromkeys(limitations))

    top = max((SEV[f["severity"]] for f in findings if not f["finding_only"]), default=0)
    if top == 0 and any(f["finding_only"] for f in findings):
        top = 1
    status = STATUS_FOR[top]
    if top == 0 and insufficient:
        status = "INSUFFICIENT_DATA"
    private_any = any(f["private"] for f in findings) or any(o.get("is_private") for o in observations)
    risk_ids = sorted({r for f in findings for r in f["risk_ids"]})
    evidence_refs = sorted({f["rule"]["source_id"] for f in findings if f["rule"].get("source_id")})
    asm_id = db.new_id("ASM")
    synthetic = any(o.get("is_synthetic") for o in observations) or bool(sim_run_id)
    created, updated = [], []
    with db.transaction(conn):
        db.insert(conn, "health_assessments", {
            "id": asm_id, "astronaut_id": astronaut_id, "mission_id": mission_id, "created_at": db.now_iso(),
            "trigger": trigger, "status": status, "indicators": db.dumps(sorted(metrics)),
            "findings": db.dumps([{k: f[k] for k in ("metric", "severity", "title", "finding", "explanation", "evidence",
                                                     "finding_only", "category")} | {"rule_id": f["rule"]["id"],
                                                     "rule_version": f["rule"]["version"], "rule_class": f["rule"]["rule_class"]}
                                  for f in findings]),
            "baseline_comparisons": db.dumps(comparisons), "limitations": db.dumps(limitations),
            "risk_ids": db.dumps(risk_ids), "next_step": NEXT_STEP[status],
            "medical_review": int(top >= SEV["MEDICAL_REVIEW"]), "evidence_refs": db.dumps(evidence_refs),
            "rule_versions": db.dumps(evaluated), "is_private": int(private_any), "is_synthetic": int(synthetic),
            "sim_run_id": sim_run_id})
        conn.executemany("INSERT OR IGNORE INTO assessment_observations VALUES (?,?)",
                         [(asm_id, o["id"]) for o in observations[:500]])
        for f in findings:
            if f["finding_only"]:
                continue
            aid, is_new = alert_svc.upsert(conn, finding=f, astronaut_id=astronaut_id, mission_id=mission_id,
                                           assessment_id=asm_id, synthetic=synthetic, sim_run_id=sim_run_id)
            (created if is_new else updated).append(aid)
            esc = f["rule"]["escalation"]
            wants_event = esc.get("create_medical_event") or esc.get("create_medical_event_on") == f["severity"]
            alert = db.one(conn, "SELECT * FROM alerts WHERE id=?", (aid,))
            if wants_event and not alert["medical_event_id"] and f["category"] == "health":
                eid = medical_events.create(conn, SYSTEM, astronaut_id=astronaut_id, mission_id=mission_id,
                                            title=f["title"], category=f["category"],
                                            risk_id=f["risk_ids"][0] if f["risk_ids"] else None, severity=alert["severity"],
                                            protocol_id=f["rule"].get("protocol_id"), private=f["private"],
                                            synthetic=synthetic, sim_run_id=sim_run_id)
                conn.execute("UPDATE alerts SET medical_event_id=? WHERE id=?", (eid, aid))
            elif alert["medical_event_id"]:
                ev = db.one(conn, "SELECT severity FROM medical_events WHERE id=?", (alert["medical_event_id"],))
                if ev and SEV[alert["severity"]] > SEV.get(ev["severity"], 0):
                    conn.execute("UPDATE medical_events SET severity=?, updated_at=? WHERE id=?",
                                 (alert["severity"], db.now_iso(), alert["medical_event_id"]))
                    medical_events.add_action(conn, SYSTEM, alert["medical_event_id"], "note",
                                              f"Severity escalated to {alert['severity']} by rule {f['rule']['id']}")
    for aid in created + updated:
        a = db.one(conn, "SELECT * FROM alerts WHERE id=?", (aid,))
        BUS.publish("alert.created" if aid in created else "alert.updated",
                    {"id": aid, "severity": a["severity"], "title": a["title"], "category": a["category"],
                     "medical_event_id": a["medical_event_id"]},
                    astronaut_id=astronaut_id, private=bool(a["is_private"]))
    BUS.publish("assessment.created", {"id": asm_id, "status": status, "indicators": sorted(metrics)},
                astronaut_id=astronaut_id, private=private_any)
    return {"assessment_id": asm_id, "assessment_ids": [asm_id], "status": status,
            "alerts_created": created, "alerts_updated": updated}


def full_assessment(conn, astronaut_id: str, trigger: str = "scheduled", hours: float = 72,
                    sim_run_id: str | None = None, anchor: str | None = None) -> dict:
    """Re-evaluate all rules over recent data plus missing-data checks."""
    a = db.one(conn, "SELECT * FROM astronauts WHERE id=?", (astronaut_id,))
    anchor = anchor or db.now_iso()
    start = db.iso(db.parse_iso(anchor) - timedelta(hours=hours))
    obs = db.all_(conn, "SELECT * FROM observations WHERE astronaut_id=? AND measured_at>=? AND measured_at<=? "
                        "ORDER BY measured_at", (astronaut_id, start, anchor))
    # quality flags were already raised when each observation arrived; skip them here
    obs = [dict(o, quality="valid") if o["quality"] == "questionable" else o for o in obs]
    return assess(conn, astronaut_id=astronaut_id, mission_id=a["mission_id"], trigger=trigger,
                  observations=obs, sim_run_id=sim_run_id, include_missing=True, anchor=anchor)


def decode(row: dict) -> dict:
    r = dict(row)
    for k, d in (("indicators", []), ("findings", []), ("baseline_comparisons", {}), ("limitations", []),
                 ("risk_ids", []), ("evidence_refs", []), ("rule_versions", {})):
        r[k] = db.loads(r[k], d)
    r["medical_review"] = bool(r["medical_review"])
    r["is_private"] = bool(r["is_private"])
    r["is_synthetic"] = bool(r["is_synthetic"])
    return r
