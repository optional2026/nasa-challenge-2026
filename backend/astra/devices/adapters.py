"""Hardware-independent device adapters.

An adapter converts a device-native reading into ASTRA's unified observation
format. The assessment engine never sees device formats. Supporting a new
physical device means writing one adapter class — nothing else changes.

IMPORTANT: no physical device has been tested with ASTRA. The adapters below
define documented reference payloads and are exercised by the simulator and
the test-suite only (`hardware_validated = False`).
"""
from __future__ import annotations

from typing import Any


class AdapterError(ValueError):
    pass


class DeviceAdapter:
    device_type: str = ""
    source_type: str = "medical_device"
    metrics: tuple[str, ...] = ()
    example: dict[str, Any] = {}

    def to_observations(self, reading: dict[str, Any], *, device: dict, measured_at: str, reading_id: str) -> list[dict]:
        raise NotImplementedError

    def _base(self, device, measured_at, reading_id, suffix, metric, value, unit, quality="valid", context=None,
              astronaut=True, location=None):
        return {"observation_id": f"{reading_id}-{suffix}", "astronaut_id": device["astronaut_id"] if astronaut else None,
                "mission_id": device["mission_id"], "metric_code": metric, "value": value, "unit": unit,
                "measured_at": measured_at, "source_type": self.source_type, "device_id": device["id"],
                "quality": quality, "context": context or {}, "location": location,
                "synthetic": bool(device["is_simulated"])}

    @staticmethod
    def _num(reading, key):
        v = reading.get(key)
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise AdapterError(f"field '{key}' must be numeric")
        return v


class HeartRateWearableAdapter(DeviceAdapter):
    device_type = "heart_rate_wearable"
    source_type = "wearable"
    metrics = ("heart_rate", "respiratory_rate", "sleep_duration")
    example = {"hr_bpm": 61, "activity": "resting", "contact": "good", "resp_rate": 14}

    def to_observations(self, reading, *, device, measured_at, reading_id):
        q = "valid" if reading.get("contact", "good") == "good" else "questionable"
        out = []
        hr = self._num(reading, "hr_bpm")
        if hr is not None:
            out.append(self._base(device, measured_at, reading_id, "HR", "heart_rate", hr, "bpm", q,
                                  {"activity": reading.get("activity", "resting"), "sensor": "optical_wrist"}))
        rr = self._num(reading, "resp_rate")
        if rr is not None:
            out.append(self._base(device, measured_at, reading_id, "RR", "respiratory_rate", rr, "breaths/min", q,
                                  {"method": "wearable_estimate"}))
        if not out:
            raise AdapterError("reading contains no supported fields (hr_bpm, resp_rate)")
        return out


class BloodPressureMonitorAdapter(DeviceAdapter):
    device_type = "blood_pressure_monitor"
    metrics = ("bp_systolic", "bp_diastolic", "heart_rate")
    example = {"sys": 118, "dia": 76, "pulse": 62, "cuff": "upper_arm", "error_code": None}

    def to_observations(self, reading, *, device, measured_at, reading_id):
        s, d = self._num(reading, "sys"), self._num(reading, "dia")
        if s is None or d is None:
            raise AdapterError("blood pressure reading requires 'sys' and 'dia'")
        q = "questionable" if reading.get("error_code") else "valid"
        ctx = {"cuff": reading.get("cuff", "upper_arm"), "panel_id": reading_id, "activity": "resting"}
        out = [self._base(device, measured_at, reading_id, "SYS", "bp_systolic", s, "mmHg", q, ctx),
               self._base(device, measured_at, reading_id, "DIA", "bp_diastolic", d, "mmHg", q, ctx)]
        p = self._num(reading, "pulse")
        if p is not None:
            out.append(self._base(device, measured_at, reading_id, "PR", "heart_rate", p, "bpm", q,
                                  {"activity": "resting", "sensor": "bp_cuff"}))
        return out


class PulseOximeterAdapter(DeviceAdapter):
    device_type = "pulse_oximeter"
    metrics = ("spo2", "heart_rate")
    example = {"spo2_pct": 98, "pulse_bpm": 63, "signal_quality": 0.92}

    def to_observations(self, reading, *, device, measured_at, reading_id):
        sp = self._num(reading, "spo2_pct")
        if sp is None:
            raise AdapterError("pulse oximeter reading requires 'spo2_pct'")
        sq = self._num(reading, "signal_quality")
        q = "valid" if sq is None or sq >= 0.6 else "questionable"
        out = [self._base(device, measured_at, reading_id, "SPO2", "spo2", sp, "%", q, {"signal_quality": sq})]
        pr = self._num(reading, "pulse_bpm")
        if pr is not None:
            out.append(self._base(device, measured_at, reading_id, "PR", "heart_rate", pr, "bpm", q,
                                  {"activity": "resting", "sensor": "pulse_oximeter"}))
        return out


class ThermometerAdapter(DeviceAdapter):
    device_type = "thermometer"
    metrics = ("body_temperature",)
    example = {"temp": 36.7, "unit": "C", "site": "oral"}

    def to_observations(self, reading, *, device, measured_at, reading_id):
        t = self._num(reading, "temp")
        unit = {"C": "degC", "F": "degF"}.get(reading.get("unit", "C"))
        if t is None or unit is None:
            raise AdapterError("thermometer reading requires 'temp' and unit 'C' or 'F'")
        return [self._base(device, measured_at, reading_id, "TEMP", "body_temperature", t, unit, "valid",
                           {"method": reading.get("site", "unspecified")})]


class GlucoseMonitorAdapter(DeviceAdapter):
    device_type = "glucose_monitor"
    metrics = ("blood_glucose",)
    example = {"glucose": 5.4, "unit": "mmol/L", "context": "fasting"}

    def to_observations(self, reading, *, device, measured_at, reading_id):
        g = self._num(reading, "glucose")
        unit = reading.get("unit", "mg/dL")
        if g is None or unit not in ("mg/dL", "mmol/L"):
            raise AdapterError("glucose reading requires 'glucose' and unit mg/dL or mmol/L")
        return [self._base(device, measured_at, reading_id, "GLU", "blood_glucose", g, unit, "valid",
                           {"meal_context": reading.get("context", "unspecified")})]


class EnvironmentalSensorAdapter(DeviceAdapter):
    device_type = "environmental_sensor"
    source_type = "environmental_sensor"
    metrics = ("cabin_co2", "cabin_o2", "cabin_temperature", "cabin_humidity", "air_tvoc", "air_pm25")
    example = {"module": "HAB-A", "co2_mmHg": 2.1, "o2_mmHg": 160.0, "temp_c": 22.4, "rh_pct": 45, "tvoc_mg_m3": 0.4, "pm25_ug_m3": 6}
    FIELDS = (("co2_mmHg", "cabin_co2", "mmHg"), ("o2_mmHg", "cabin_o2", "mmHg"), ("temp_c", "cabin_temperature", "degC"),
              ("rh_pct", "cabin_humidity", "%RH"), ("tvoc_mg_m3", "air_tvoc", "mg/m3"), ("pm25_ug_m3", "air_pm25", "ug/m3"))

    def to_observations(self, reading, *, device, measured_at, reading_id):
        loc = reading.get("module") or device.get("location")
        out = []
        for key, metric, unit in self.FIELDS:
            v = self._num(reading, key)
            if v is not None:
                out.append(self._base(device, measured_at, reading_id, metric.upper(), metric, v, unit, "valid",
                                      {}, astronaut=False, location=loc))
        if not out:
            raise AdapterError("environmental reading contains no supported fields")
        return out


class RadiationDosimeterAdapter(DeviceAdapter):
    device_type = "radiation_dosimeter"
    source_type = "environmental_sensor"
    metrics = ("radiation_dose_rate", "radiation_dose_cumulative")
    example = {"dose_rate_uGy_h": 15.2, "cumulative_mGy": 4.81, "mode": "area"}

    def to_observations(self, reading, *, device, measured_at, reading_id):
        personal = bool(device["astronaut_id"])
        loc = None if personal else (reading.get("module") or device.get("location"))
        ctx = {"dosimeter_mode": "personal" if personal else "area", "quantity": "absorbed_dose"}
        out = []
        r = self._num(reading, "dose_rate_uGy_h")
        if r is not None:
            out.append(self._base(device, measured_at, reading_id, "RATE", "radiation_dose_rate", r, "uGy/h", "valid", ctx,
                                  astronaut=personal, location=loc))
        c = self._num(reading, "cumulative_mGy")
        if c is not None:
            out.append(self._base(device, measured_at, reading_id, "CUM", "radiation_dose_cumulative", c, "mGy", "valid", ctx,
                                  astronaut=personal, location=loc))
        if not out:
            raise AdapterError("dosimeter reading requires dose_rate_uGy_h and/or cumulative_mGy")
        if personal:
            for o in out:
                o["source_type"] = "wearable"
        return out


ADAPTERS: dict[str, DeviceAdapter] = {a.device_type: a for a in (
    HeartRateWearableAdapter(), BloodPressureMonitorAdapter(), PulseOximeterAdapter(), ThermometerAdapter(),
    GlucoseMonitorAdapter(), EnvironmentalSensorAdapter(), RadiationDosimeterAdapter())}


def adapter_for(device_type: str) -> DeviceAdapter:
    try:
        return ADAPTERS[device_type]
    except KeyError:
        raise AdapterError(f"no adapter for device type '{device_type}'")
