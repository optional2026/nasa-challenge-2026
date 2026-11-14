// Formatting helpers and the semantic status vocabulary.

export type Tone = "ok" | "attn" | "review" | "urgent" | "none" | "info";

export const SEVERITY_TONE: Record<string, Tone> = {
  INFORMATION: "info", REASSESSMENT: "attn", MEDICAL_REVIEW: "review", URGENT: "urgent",
};

export const STATUS_INFO: Record<string, { tone: Tone; label: string; meaning: string }> = {
  NO_CONCERN_IDENTIFIED: { tone: "ok", label: "No current concern identified", meaning: "Recent measurements are consistent with this astronaut's approved baselines." },
  INFORMATION: { tone: "info", label: "Information", meaning: "There is something worth knowing; no action is required." },
  REASSESSMENT_RECOMMENDED: { tone: "attn", label: "Reassessment recommended", meaning: "Verify or repeat a measurement following the reassessment procedure." },
  MEDICAL_REVIEW_RECOMMENDED: { tone: "review", label: "Medical review", meaning: "A finding should be reviewed by the Crew Medical Officer or flight surgeon." },
  URGENT_PROCEDURE: { tone: "urgent", label: "Urgent procedure", meaning: "Open the Medical Response Center and follow the approved procedure now." },
  INSUFFICIENT_DATA: { tone: "none", label: "Not enough data", meaning: "Measurements are missing, stale or have no approved baseline. Missing data is never treated as healthy." },
};

export const SEVERITY_LABEL: Record<string, string> = {
  INFORMATION: "Information", REASSESSMENT: "Reassess", MEDICAL_REVIEW: "Medical review", URGENT: "Urgent",
};

export const UNIT: Record<string, string> = {
  bpm: "bpm", mmHg: "mmHg", "%": "%", degC: "°C", degF: "°F", "mg/dL": "mg/dL", "mmol/L": "mmol/L",
  "breaths/min": "/min", min: "min", h: "h", score_1_5: "/5", score_0_10: "/10", score_0_3: "/3", ms: "ms",
  mL: "mL", kcal: "kcal", "%RH": "% RH", "mg/m3": "mg/m³", "ug/m3": "µg/m³", "uGy/h": "µGy/h", mGy: "mGy",
  count: "", kg: "kg", s: "s", score: "", category: "", bool: "", structured: "",
};

export function unit(u?: string | null) { return u ? (UNIT[u] ?? u) : ""; }

export function fmtValue(v: any, u?: string, metric?: string): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "object") return v.summary || v.test || JSON.stringify(v);
  if (typeof v === "string") return v.replace(/_/g, " ");
  if (metric === "sleep_duration" || metric === "sleep_opportunity") return `${Math.floor(v / 60)} h ${Math.round(v % 60)} min`;
  const digits = u === "degC" || u === "mGy" ? 2 : u === "%" || u === "bpm" ? 0 : u === "mmHg" ? (Math.abs(v) < 20 ? 2 : 0) : Math.abs(v) < 10 ? 2 : 1;
  return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function fmtTime(iso?: string | null, withDate = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const date = d.toISOString().slice(5, 10);
  const time = d.toISOString().slice(11, 16);
  return withDate ? `${date} ${time} UTC` : `${time} UTC`;
}

export function ago(iso?: string | null): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export function humanize(code?: string | null): string {
  if (!code) return "";
  const s = code.replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const ROLE_LABEL: Record<string, string> = {
  astronaut: "Astronaut", medical_officer: "Crew Medical Officer", flight_surgeon: "Flight surgeon (ground)", admin: "Administrator",
};
