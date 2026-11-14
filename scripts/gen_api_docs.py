"""Generate docs/API.md and docs/openapi.json from the live route registry."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ASTRA_DATA_DIR", tempfile.mkdtemp())
from astra.app import openapi_doc  # noqa: E402

doc = openapi_doc()
(ROOT / "docs" / "openapi.json").write_text(json.dumps(doc, indent=2))
L = ["# ASTRA REST API", "", f"Version {doc['info']['version']}. Generated from the server's route registry (`scripts/gen_api_docs.py`).",
     "Interactive list: `/api/docs` · machine-readable: `/api/openapi.json` (also saved as `docs/openapi.json`).", "",
     "Authentication: `POST /api/v1/auth/login` returns a bearer token (12 h). Devices authenticate with `X-Device-Key`.",
     "Errors use one shape: `{\"error\": {\"code\", \"message\", \"details\"}}`. Validation errors return HTTP 422.", "",
     "Real-time: WebSocket `/ws?token=<session token>` streams events (`observations.created`, `assessment.created`, `alert.created`,",
     "`alert.updated`, `alert.acknowledged`, `alert.resolved`, `medical_event.created`, `medical_event.updated`, `environment.warning`,",
     "`device.status`, `simulator.status`, `sync.updated`, `notification`). Private behavioral-health events are delivered only to",
     "authorized connections (redacted for the Crew Medical Officer).", ""]
by_tag = {}
for path, ops in doc["paths"].items():
    for m, op in ops.items():
        by_tag.setdefault(op["tags"][0], []).append((path, m, op))
for tag in sorted(by_tag):
    L += [f"## {tag}", "", "| Method | Path | Summary | Auth | Roles |", "|---|---|---|---|---|"]
    for path, m, op in by_tag[tag]:
        auth = "none" if "security" not in op else ("bearer or device key" if len(op["security"]) > 1 else "bearer")
        L.append(f"| {m.upper()} | `{path}` | {op['summary']} | {auth} | {', '.join(op.get('x-roles', [])) or '—'} |")
    L.append("")
L += ["## Telemetry example (synthetic)", "", "```http", "POST /api/v1/telemetry", "X-Device-Key: <device key>",
      "Idempotency-Key: batch-2026-11-14-0001", "Content-Type: application/json", "", json.dumps({"observations": [{
          "observation_id": "OBS-0001", "astronaut_id": "AST-001", "mission_id": "MSN-ARES-T1", "metric_code": "heart_rate",
          "value": 78, "unit": "bpm", "measured_at": "2026-11-14T10:30:00Z", "source_type": "wearable", "device_id": "DEV-HRW-001",
          "quality": "valid", "context": {"activity": "resting", "position": "seated"}}]}, indent=2), "```", "",
      "Response: `processing_status` (complete | partial | rejected), `accepted[]` (accepted | duplicate), `rejected[]` with",
      "per-item `errors`, `validation_errors`, `assessments[]`, `alerts_created[]`, `alerts_updated[]`.", ""]
(ROOT / "docs" / "API.md").write_text("\n".join(L))
print("paths:", len(doc["paths"]))
