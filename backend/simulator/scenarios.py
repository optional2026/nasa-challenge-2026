"""Scenario definitions for the ASTRA mission simulator.

Every scenario produces a deterministic, internally consistent time series
(seeded noise around each astronaut's synthetic physiology + scenario-specific
patterns such as circadian rhythm, exercise bouts, gradual drifts, solar
particle event profiles). Nothing is pure random numbers.

ALL OUTPUT IS SYNTHETIC.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from astra import db
from astra.seed import ASTRONAUTS, MISSION_ID

SCENARIOS = {
    "nominal": "Nominal mission — stable measurements, routine assessments, regular environmental observations.",
    "cardiovascular": "Cardiovascular change — gradual rise in resting heart rate and blood pressure, optional palpitations/dizziness.",
    "sleep_fatigue": "Sleep and fatigue — shortened sleep opportunities, reduced sleep, rising fatigue and slower reaction times.",
    "illness": "Possible illness — temperature rise above personal baseline with sore throat, congestion and fatigue.",
    "radiation_event": "Radiation event — synthetic solar-particle-event profile in area and personal dosimeters.",
    "musculoskeletal": "Musculoskeletal deconditioning — reduced exercise adherence and declining strength test results.",
    "behavioral": "Behavioral health concern — declining self-reported mood, rising stress and workload (private workflow).",
    "emergency": "Synthetic medical emergency — sudden heart-rate rise, SpO2 fall and cardiorespiratory symptoms (urgent workflow).",
}
PRIMARY = "AST-001"


@dataclass(order=True)
class Emission:
    t: datetime
    kind: str = field(compare=False)          # 'telemetry' | 'sleep' | 'mood' | 'exercise' | 'nutrition' | 'daily_assessment'
    device_id: str | None = field(compare=False, default=None)
    astronaut_id: str | None = field(compare=False, default=None)
    payload: dict = field(compare=False, default_factory=dict)


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class ScenarioBuilder:
    def __init__(self, scenario: str, start: datetime, days: int, seed: int, launch: datetime, run_id: str):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        self.s, self.start, self.days, self.launch, self.run_id = scenario, start, days, launch, run_id
        self.rng = random.Random(seed)
        self.onset = max(1.0, days * 0.55)
        self.out: list[Emission] = []
        self.counter = 0
        self.cum = {}  # cumulative dose per dosimeter (mGy)

    # ---------------------------------------------------------------- helpers
    def prog(self, t: datetime) -> float:
        d = (t - self.start).total_seconds() / 86400
        return _clamp((d - self.onset) / max(0.5, self.days - self.onset))

    def day(self, t):
        return (t - self.start).total_seconds() / 86400

    def g(self, ms, scale=1.0):
        return self.rng.gauss(ms[0], ms[1] * scale)

    def oid(self, prefix):
        self.counter += 1
        return f"SIM-{self.run_id[-6:]}-{prefix}-{self.counter:06d}"

    def obs(self, t, ast, metric, value, unit, source, device, quality="valid", ctx=None, location=None, symptoms=None):
        o = {"observation_id": self.oid(metric[:4].upper()), "astronaut_id": ast, "mission_id": MISSION_ID,
             "metric_code": metric, "value": value, "unit": unit, "measured_at": db.iso(t), "source_type": source,
             "device_id": device, "quality": quality, "context": dict(ctx or {}, simulator_scenario=self.s),
             "location": location, "synthetic": True}
        if symptoms:
            o["symptoms"] = symptoms
        return o

    def tele(self, t, device, observations, ast=None):
        self.out.append(Emission(t, "telemetry", device, ast, {"observations": observations}))

    # ---------------------------------------------------------------- build
    def build(self) -> list[Emission]:
        for a in ASTRONAUTS:
            self._crew(a, primary=(a["id"] == PRIMARY))
        self._environment()
        for d in range(self.days + 1):
            t = self.start + timedelta(days=d, hours=8, minutes=5)
            for a in ASTRONAUTS:
                self.out.append(Emission(t, "daily_assessment", None, a["id"], {}))
        end = self.start + timedelta(days=self.days)
        self.out = sorted(e for e in self.out if self.start <= e.t <= end)
        return self.out

    def _crew(self, a, primary):
        p, aid, n = a["p"], a["id"], int(a["id"][-1])
        wearable, s = f"DEV-HRW-00{n}", self.s if primary else "nominal"
        hr_step = 30 if primary else 60
        t = self.start.replace(minute=0, second=0, microsecond=0)
        end = self.start + timedelta(days=self.days)
        emergency_t = None
        if s == "emergency":  # sudden onset ~3 h before the end of the simulated window
            emergency_t = (end - timedelta(hours=3)).replace(second=0, microsecond=0)
            emergency_t -= timedelta(minutes=emergency_t.minute % 30)
        while t <= end:
            hour = t.hour + t.minute / 60
            pr = self.prog(t)
            mins = int(t.hour * 60 + t.minute)
            # ---------- heart rate (wearable) with circadian rhythm and activity context
            if mins % hr_step == 0:
                act = "sleep" if (hour >= 23 or hour < 7) else "exercise" if (9 <= hour < 9.75 or 15 <= hour < 15.75) else "resting"
                base = p["hr"][0] + 2.0 * math.sin((hour - 10) / 24 * 2 * math.pi)
                if act == "sleep":
                    base -= 6
                elif act == "exercise":
                    base += 62 + self.rng.uniform(-6, 6)
                if s == "cardiovascular":
                    base += 15 * pr
                if s == "illness":
                    base += 7 * pr
                if s == "sleep_fatigue":
                    base += 3 * pr
                rr = None
                quality = "valid"
                if emergency_t and t >= emergency_t:
                    k = _clamp((t - emergency_t).total_seconds() / 3600 / 1.0)
                    base = p["hr"][0] + 58 * k
                    act = "resting"
                    rr = round(p["rr"][0] + 13 * k + self.rng.gauss(0, 0.6))
                if primary and self.rng.random() < 0.004 and act == "resting":
                    quality = "questionable"  # synthetic motion artefact
                obs = [self.obs(t, aid, "heart_rate", round(base + self.rng.gauss(0, p["hr"][1] * 0.6), 1), "bpm", "wearable",
                                wearable, quality, {"activity": act, "sensor": "optical_wrist"})]
                if rr is not None:
                    obs.append(self.obs(t, aid, "respiratory_rate", rr, "breaths/min", "wearable", wearable, "valid",
                                        {"method": "wearable_estimate"}))
                self.tele(t, wearable, obs, aid)
            # ---------- morning vitals (shared medical devices)
            if t.hour == 7 and t.minute == 30 and not (emergency_t and t >= emergency_t):
                self._morning_vitals(a, t, s, pr)
            # ---------- sleep record (wearable + astronaut correction) at 07:00
            if t.hour == 7 and t.minute == 0:
                self._sleep(a, t, s, pr)
            # ---------- exercise sessions end 09:45 / 15:45
            if (t.hour, t.minute) in ((9, 45), (15, 45)):
                self._exercise(a, t, s, pr)
            # ---------- hydration 5x/day
            if t.minute == 0 and t.hour in (8, 11, 14, 17, 20):
                self._water(a, t, s, pr)
            # ---------- check-in 21:15
            if t.hour == 21 and t.minute == 15:
                self._checkin(a, t, s, pr)
            # ---------- personal dosimeter every 2 h
            if t.minute == 0 and t.hour % 2 == 0:
                self._dosimeter(f"DEV-DOS-00{n}", aid, t, personal=True)
            t += timedelta(minutes=15)
        if emergency_t:
            te = emergency_t + timedelta(minutes=50)
            sp = self.obs(te, aid, "spo2", 89, "%", "medical_device", "DEV-OXI-01", "valid", {"signal_quality": 0.9},
                          symptoms=[{"code": "shortness_of_breath", "severity": 4, "onset_at": db.iso(emergency_t + timedelta(minutes=20))},
                                    {"code": "dizziness", "severity": 3, "onset_at": db.iso(emergency_t + timedelta(minutes=30))},
                                    {"code": "chest_discomfort", "severity": 3, "onset_at": db.iso(emergency_t + timedelta(minutes=35))}])
            self.tele(te, "DEV-OXI-01", [sp], aid)
            te2 = te + timedelta(minutes=10)
            self.tele(te2, "DEV-OXI-01", [self.obs(te2, aid, "spo2", 90, "%", "medical_device", "DEV-OXI-01", "valid",
                                                   {"signal_quality": 0.88, "repeat": True})], aid)

    def _morning_vitals(self, a, t, s, pr):
        p, aid = a["p"], a["id"]
        sbp = self.g(p["sbp"], 0.7) + (17 * pr if s == "cardiovascular" else 0)
        dbp = self.g(p["dbp"], 0.7) + (11 * pr if s == "cardiovascular" else 0)
        hr_cuff = self.g(p["hr"], 0.7) + (15 * pr if s == "cardiovascular" else 7 * pr if s == "illness" else 0)
        syms = []
        if s == "cardiovascular" and 0.55 < pr < 0.7 and not getattr(self, "_palp", False):
            self._palp = True
            syms.append({"code": "palpitations", "severity": 2, "onset_at": db.iso(t - timedelta(hours=1))})
        if s == "cardiovascular" and pr > 0.85 and not getattr(self, "_dizzy", False):
            self._dizzy = True
            syms.append({"code": "dizziness", "severity": 2, "onset_at": db.iso(t - timedelta(minutes=30))})
        bp = [self.obs(t, aid, "bp_systolic", round(sbp), "mmHg", "medical_device", "DEV-BPM-01", "valid",
                       {"cuff": "upper_arm", "activity": "resting"}),
              self.obs(t, aid, "bp_diastolic", round(dbp), "mmHg", "medical_device", "DEV-BPM-01", "valid",
                       {"cuff": "upper_arm", "activity": "resting"}, symptoms=syms or None),
              self.obs(t, aid, "heart_rate", round(hr_cuff), "bpm", "medical_device", "DEV-BPM-01", "valid",
                       {"activity": "resting", "sensor": "bp_cuff"})]
        self.tele(t, "DEV-BPM-01", bp, aid)
        t2 = t + timedelta(minutes=3)
        self.tele(t2, "DEV-OXI-01", [self.obs(t2, aid, "spo2", round(min(100, self.g(p["spo2"], 0.8))), "%", "medical_device",
                                              "DEV-OXI-01", "valid", {"signal_quality": 0.95})], aid)
        t3 = t + timedelta(minutes=6)
        temp = self.g(p["temp"], 0.8)
        tsyms = []
        if s == "illness":
            temp += 0.95 * _clamp(pr * 1.6)
            if pr > 0.15:  # ongoing symptoms re-reported each morning with the original onset time
                if not getattr(self, "_ill_onset", None):
                    self._ill_onset = t3 - timedelta(hours=6)
                tsyms = [{"code": "sore_throat", "severity": 2, "onset_at": db.iso(self._ill_onset)},
                         {"code": "nasal_congestion", "severity": 2, "onset_at": db.iso(self._ill_onset + timedelta(hours=1))},
                         {"code": "unusual_fatigue", "severity": 3, "onset_at": db.iso(self._ill_onset + timedelta(hours=3))}]
        self.tele(t3, "DEV-THM-01", [self.obs(t3, aid, "body_temperature", round(temp, 2), "degC", "medical_device", "DEV-THM-01",
                                              "valid", {"method": "oral"}, symptoms=tsyms or None)], aid)
        rr = self.g(p["rr"], 0.7)
        t4 = t + timedelta(minutes=8)
        self.tele(t4, f"DEV-HRW-00{int(aid[-1])}",
                  [self.obs(t4, aid, "respiratory_rate", round(rr), "breaths/min", "wearable", f"DEV-HRW-00{int(aid[-1])}",
                            "valid", {"method": "wearable_estimate"})], aid)
        if a["glucose"]:
            t5 = t + timedelta(minutes=10)
            self.tele(t5, "DEV-GLU-01", [self.obs(t5, aid, "blood_glucose", round(self.g(p["glu"], 0.8)), "mg/dL",
                                                  "medical_device", "DEV-GLU-01", "valid", {"meal_context": "fasting"})], aid)

    def _sleep(self, a, t, s, pr):
        p, aid = a["p"], a["id"]
        opp = 510
        dur = self.g(p["sleep"], 0.8)
        fatigue = None
        if s == "nominal" and int(self.day(t)) == 3:
            opp = 450  # one compressed schedule day (scheduling reference note)
        if s == "sleep_fatigue":
            opp = 510 - 120 * _clamp(pr * 1.5)
            dur -= 160 * pr
            fatigue = int(round(2 + 3 * pr))
        if s == "behavioral":
            dur -= 50 * pr
        if s == "illness":
            dur -= 30 * pr
        dur = max(120, min(dur, opp + 20))
        start = t - timedelta(minutes=dur + self.rng.uniform(10, 35))
        body = {"astronaut_id": aid, "sleep_start": db.iso(start), "sleep_end": db.iso(t),
                "corrected_duration_min": round(dur, 1), "quality": int(_clamp(round(4 - 2.5 * pr) if s in ("sleep_fatigue", "behavioral") else round(self.rng.gauss(4, 0.5)), 1, 5)),
                "awakenings": int(max(0, round(self.rng.gauss(1 + (3 * pr if s == "sleep_fatigue" else 0), 0.7)))),
                "scheduled_opportunity_min": round(opp), "source_type": "simulator", "synthetic": True,
                "client_submission_id": self.oid("SLP")}
        if fatigue is not None:
            body["fatigue_after_waking"] = int(_clamp(fatigue, 1, 5))
        self.out.append(Emission(t, "sleep", None, aid, body))

    def _exercise(self, a, t, s, pr):
        aid = a["id"]
        aerobic = t.hour == 9
        status, dur = "completed", 45.0
        if s == "musculoskeletal" and pr > 0:
            r = self.rng.random()
            if r < 0.6 * _clamp(pr * 2.5):
                status, dur = "skipped", None
            elif r < 0.85 * _clamp(pr * 2.5):
                status, dur = "partial", 20.0
        if s == "illness" and pr > 0.3 and aerobic:
            status, dur = "skipped", None
        body = {"astronaut_id": aid, "exercise_type": "Treadmill aerobic session" if aerobic else "Resistive exercise session",
                "category": "aerobic" if aerobic else "resistive", "start_at": db.iso(t - timedelta(minutes=45)),
                "duration_min": dur, "intensity": "moderate" if status != "skipped" else None, "completion_status": status,
                "source_type": "simulator", "synthetic": True, "client_submission_id": self.oid("EXR")}
        d = self.day(t)
        test_every = 2 if s == "musculoskeletal" else 7
        if not aerobic and int(d) % test_every == 1:
            grip = self.g(a["p"]["grip"], 0.7) - (6 * _clamp(pr * 1.5) if s == "musculoskeletal" else 0)
            body["performance_test"] = {"test": "grip_strength", "value": round(grip, 1), "unit": "kg"}
            if s == "musculoskeletal" and pr > 0.5:
                body["pain_score"] = 3
                body["pain_location"] = "lower back"
        self.out.append(Emission(t, "exercise", None, aid, body))

    def _water(self, a, t, s, pr):
        frac = {8: 0.25, 11: 0.2, 14: 0.2, 17: 0.2, 20: 0.15}[t.hour]
        daily = self.g(a["p"]["water"], 0.6) * (1 - 0.35 * pr if s == "illness" else 1)
        body = {"astronaut_id": a["id"], "recorded_at": db.iso(t), "record_type": "water", "water_ml": round(daily * frac),
                "source_type": "simulator", "synthetic": True, "client_submission_id": self.oid("H2O")}
        if t.hour in (8, 14, 20):
            body.update({"record_type": "meal", "energy_kcal": round(self.rng.gauss(750, 60) * (1 - 0.3 * pr if s == "illness" else 1)),
                         "appetite": int(_clamp(round(3 - 1.5 * pr) if s in ("illness", "behavioral") else 3 + round(self.rng.random()), 1, 5)),
                         "description": "Standard menu item (synthetic)"})
        self.out.append(Emission(t, "nutrition", None, a["id"], body))

    def _checkin(self, a, t, s, pr):
        p, aid = a["p"], a["id"]
        q = lambda k, delta=0.0: int(_clamp(round(self.g(p[k], 0.6) + delta), 1, 5))
        body = {"astronaut_id": aid, "assessed_at": db.iso(t), "mood": q("mood"), "stress": q("stress"), "fatigue": q("fatigue"),
                "sleep_rating": q("mood"), "workload": q("workload"), "connectedness": q("conn"), "synthetic": True,
                "client_submission_id": self.oid("MOOD")}
        if s == "behavioral":
            p2 = _clamp(pr * 2.2)
            body.update({"mood": q("mood", -2.9 * p2), "stress": q("stress", 2.9 * p2), "workload": q("workload", 1.6 * p2),
                         "connectedness": q("conn", -2.2 * p2)})
            if pr > 0.6 and not getattr(self, "_note", False):
                self._note = True
                body["note_for_medical"] = "SYNTHETIC: Feeling disconnected from the team and not sleeping well. Would like to talk privately."
        if s == "sleep_fatigue":
            body.update({"fatigue": q("fatigue", 2.8 * pr), "workload": q("workload", 1.5 * pr), "sleep_rating": q("mood", -2 * pr)})
        if s == "illness" and pr > 0.2:
            body["fatigue"] = q("fatigue", 2.0)
        if int(self.day(t)) % 3 == 0:
            body["cognitive_pvt_rt_ms"] = round(self.g(p["pvt"], 0.7) + (70 * pr if s == "sleep_fatigue" else 0))
        if s == "behavioral" and pr == 0 and self.rng.random() < 0.3:
            body["stress"] = None  # astronaut skipped a question (shown as missing, never as fine)
        self.out.append(Emission(t, "mood", None, aid, body))

    def _dosimeter(self, dev, aid, t, personal, location=None):
        rate = 18.0 * (0.55 if personal else 1.0) * self._spe_factor(t, personal) + self.rng.gauss(0, 0.6)
        rate = max(0.5, rate)
        key = dev
        if key not in self.cum:
            self.cum[key] = 0.43 * max(0.0, (self.start - self.launch).total_seconds() / 86400) * (0.55 if personal else 1)
            self._last_t = getattr(self, "_last_t", {})
            self._last_t[key] = t
        dt_h = (t - self._last_t[key]).total_seconds() / 3600
        self.cum[key] += rate * dt_h / 1000.0
        self._last_t[key] = t
        o = [self.obs(t, aid if personal else None, "radiation_dose_rate", round(rate, 2), "uGy/h",
                      "wearable" if personal else "environmental_sensor", dev, "valid",
                      {"dosimeter_mode": "personal" if personal else "area", "quantity": "absorbed_dose"}, location=location),
             self.obs(t, aid if personal else None, "radiation_dose_cumulative", round(self.cum[key], 3), "mGy",
                      "wearable" if personal else "environmental_sensor", dev, "valid",
                      {"dosimeter_mode": "personal" if personal else "area", "quantity": "absorbed_dose"}, location=location)]
        self.tele(t, dev, o, aid if personal else None)

    def _spe_factor(self, t, personal):
        if self.s != "radiation_event":
            return 1.0
        peak = self.start + timedelta(days=self.onset + 0.5)
        h = (t - peak).total_seconds() / 3600
        if h < -3 or h > 14:
            return 1.0
        if h < 0:
            amp = (h + 3) / 3
        else:
            amp = math.exp(-h / 4)
        return 1.0 + amp * (9 if personal else 30)

    def _environment(self):
        t = self.start.replace(minute=0, second=0, microsecond=0)
        end = self.start + timedelta(days=self.days)
        em_t = None
        if self.s == "emergency":
            em_t = (end - timedelta(hours=4)).replace(second=0, microsecond=0)
            em_t -= timedelta(minutes=em_t.minute % 30)
        while t <= end:
            hour = t.hour + t.minute / 60
            if t.minute in (0, 30):
                for dev, mod, off in (("DEV-ENV-HABA", "HAB-A", 0.0), ("DEV-ENV-LAB", "LAB", -0.2)):
                    co2 = 2.1 + off + 0.35 * math.sin((hour - 14) / 24 * 2 * math.pi) + self.rng.gauss(0, 0.06)
                    if em_t and mod == "HAB-A" and em_t <= t <= em_t + timedelta(hours=4):
                        co2 += 2.4 * math.sin(_clamp((t - em_t).total_seconds() / 14400) * math.pi)
                    o = [self.obs(t, None, "cabin_co2", round(co2, 2), "mmHg", "environmental_sensor", dev, location=mod),
                         self.obs(t, None, "cabin_o2", round(160 + self.rng.gauss(0, 0.8), 1), "mmHg", "environmental_sensor", dev, location=mod),
                         self.obs(t, None, "cabin_temperature", round(22.3 + off + 0.4 * math.sin((hour - 15) / 24 * 2 * math.pi) + self.rng.gauss(0, 0.08), 2),
                                  "degC", "environmental_sensor", dev, location=mod),
                         self.obs(t, None, "cabin_humidity", round(46 + 3 * math.sin((hour - 9) / 24 * 2 * math.pi) + self.rng.gauss(0, 0.6), 1),
                                  "%RH", "environmental_sensor", dev, location=mod),
                         self.obs(t, None, "air_tvoc", round(max(0.05, 0.32 + self.rng.gauss(0, 0.03)), 3), "mg/m3", "environmental_sensor", dev, location=mod),
                         self.obs(t, None, "air_pm25", round(max(0.5, 5 + self.rng.gauss(0, 0.8)), 1), "ug/m3", "environmental_sensor", dev, location=mod)]
                    self.tele(t, dev, o)
                self._dosimeter("DEV-RAD-HABA", None, t, personal=False, location="HAB-A")
            t += timedelta(minutes=30)
