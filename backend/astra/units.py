"""Explicit unit handling.

Every observation keeps its ORIGINAL value and unit; a canonical value is
stored alongside it for analysis. Unknown or unsupported units are rejected —
values are never silently re-interpreted.
"""
from __future__ import annotations

from typing import Callable

MMHG_PER_KPA = 7.500617
GLUCOSE_MGDL_PER_MMOLL = 18.016  # glucose molar mass 180.16 g/mol

# (from_unit, to_unit) -> converter
_CONVERSIONS: dict[tuple[str, str], Callable[[float], float]] = {
    ("degF", "degC"): lambda f: (f - 32.0) * 5.0 / 9.0,
    ("degC", "degF"): lambda c: c * 9.0 / 5.0 + 32.0,
    ("mmol/L", "mg/dL"): lambda v: v * GLUCOSE_MGDL_PER_MMOLL,
    ("mg/dL", "mmol/L"): lambda v: v / GLUCOSE_MGDL_PER_MMOLL,
    ("kPa", "mmHg"): lambda v: v * MMHG_PER_KPA,
    ("mmHg", "kPa"): lambda v: v / MMHG_PER_KPA,
    ("h", "min"): lambda v: v * 60.0,
    ("min", "h"): lambda v: v / 60.0,
    ("L", "mL"): lambda v: v * 1000.0,
    ("mL", "L"): lambda v: v / 1000.0,
    ("mGy/d", "uGy/h"): lambda v: v * 1000.0 / 24.0,
    ("uGy/h", "mGy/d"): lambda v: v * 24.0 / 1000.0,
    ("uGy", "mGy"): lambda v: v / 1000.0,
    ("mGy", "uGy"): lambda v: v * 1000.0,
}

UNIT_LABELS = {
    "bpm": "beats/min", "mmHg": "mmHg", "kPa": "kPa", "%": "%", "degC": "°C", "degF": "°F",
    "mg/dL": "mg/dL", "mmol/L": "mmol/L", "breaths/min": "breaths/min", "min": "min", "h": "h",
    "count": "count", "score_1_5": "level (1–5)", "score_0_10": "0–10", "score_0_3": "0–3",
    "ms": "ms", "s": "s", "kg": "kg", "score": "score", "mL": "mL", "L": "L", "kcal": "kcal",
    "%RH": "% RH", "mg/m3": "mg/m³", "ug/m3": "µg/m³", "uGy/h": "µGy/h", "mGy/d": "mGy/day",
    "mGy": "mGy", "uGy": "µGy", "bool": "yes/no", "category": "category", "structured": "record",
}


class UnitError(ValueError):
    pass


def convert(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return float(value)
    fn = _CONVERSIONS.get((from_unit, to_unit))
    if fn is None:
        raise UnitError(f"no conversion from '{from_unit}' to '{to_unit}'")
    return float(fn(float(value)))


def to_canonical(value: float, unit: str, canonical_unit: str, allowed_units: list[str]) -> float:
    if unit not in allowed_units:
        raise UnitError(f"unsupported unit '{unit}'; allowed: {', '.join(allowed_units)}")
    return convert(value, unit, canonical_unit)
