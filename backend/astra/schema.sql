-- ASTRA relational schema (SQLite). Foreign keys are enforced (PRAGMA foreign_keys=ON).
-- JSON columns hold extensible metadata only; relationships are explicit tables.

CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- ---------------------------------------------------------------- knowledge
CREATE TABLE IF NOT EXISTS evidence_sources (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, publisher TEXT, document_id TEXT, url TEXT, year INTEGER,
  source_type TEXT NOT NULL, verification_status TEXT NOT NULL, accessed_date TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS hazard_definitions (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, monitoring_role TEXT
);
CREATE TABLE IF NOT EXISTS hazard_sources (
  hazard_id TEXT NOT NULL REFERENCES hazard_definitions(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES evidence_sources(id),
  PRIMARY KEY (hazard_id, source_id)
);
CREATE TABLE IF NOT EXISTS risk_definitions (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, nasa_risk_title TEXT, description TEXT NOT NULL,
  body_systems TEXT NOT NULL, measurement_methods TEXT NOT NULL, symptoms TEXT NOT NULL,
  limitations TEXT NOT NULL, evidence_status TEXT NOT NULL, approval_status TEXT NOT NULL,
  privacy TEXT NOT NULL DEFAULT 'standard', specialized_assessment_note TEXT
);
CREATE TABLE IF NOT EXISTS risk_hazard_relationships (
  risk_id TEXT NOT NULL REFERENCES risk_definitions(id) ON DELETE CASCADE,
  hazard_id TEXT NOT NULL REFERENCES hazard_definitions(id) ON DELETE CASCADE,
  rationale TEXT NOT NULL,
  PRIMARY KEY (risk_id, hazard_id)
);
CREATE TABLE IF NOT EXISTS risk_sources (
  risk_id TEXT NOT NULL REFERENCES risk_definitions(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES evidence_sources(id),
  PRIMARY KEY (risk_id, source_id)
);
CREATE TABLE IF NOT EXISTS health_indicators (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, subject TEXT NOT NULL,
  value_type TEXT NOT NULL, canonical_unit TEXT NOT NULL, allowed_units TEXT NOT NULL,
  plausible_min REAL, plausible_max REAL, body_system TEXT, challenge_required INTEGER NOT NULL DEFAULT 0,
  privacy TEXT NOT NULL DEFAULT 'standard', clinician_only INTEGER NOT NULL DEFAULT 0,
  clinician_directed INTEGER NOT NULL DEFAULT 0,
  description TEXT, measurement_instructions TEXT, limitations TEXT, scale_labels TEXT
);
CREATE TABLE IF NOT EXISTS risk_indicators (
  risk_id TEXT NOT NULL REFERENCES risk_definitions(id) ON DELETE CASCADE,
  indicator_code TEXT NOT NULL REFERENCES health_indicators(code),
  PRIMARY KEY (risk_id, indicator_code)
);
CREATE TABLE IF NOT EXISTS countermeasures (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, approval_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_countermeasures (
  risk_id TEXT NOT NULL REFERENCES risk_definitions(id) ON DELETE CASCADE,
  countermeasure_id TEXT NOT NULL REFERENCES countermeasures(id) ON DELETE CASCADE,
  PRIMARY KEY (risk_id, countermeasure_id)
);
CREATE TABLE IF NOT EXISTS countermeasure_sources (
  countermeasure_id TEXT NOT NULL REFERENCES countermeasures(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES evidence_sources(id),
  PRIMARY KEY (countermeasure_id, source_id)
);
CREATE TABLE IF NOT EXISTS symptom_vocabulary (
  code TEXT PRIMARY KEY, label TEXT NOT NULL, risk_ids TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medical_protocols (
  id TEXT NOT NULL, version INTEGER NOT NULL, title TEXT NOT NULL, approval_status TEXT NOT NULL,
  disclaimer TEXT NOT NULL, applies_to_rules TEXT NOT NULL, applies_to_risks TEXT NOT NULL,
  verification_checklist TEXT NOT NULL, steps TEXT NOT NULL, escalation TEXT NOT NULL,
  source_id TEXT REFERENCES evidence_sources(id),
  PRIMARY KEY (id, version)
);
CREATE TABLE IF NOT EXISTS assessment_rules (
  id TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL, rule_class TEXT NOT NULL,
  approval_status TEXT NOT NULL, active INTEGER NOT NULL, metrics TEXT NOT NULL,
  evaluation_method TEXT NOT NULL, params TEXT NOT NULL, context_filter TEXT NOT NULL,
  severity TEXT NOT NULL, risk_ids TEXT NOT NULL, protocol_id TEXT, source_id TEXT REFERENCES evidence_sources(id),
  effective_date TEXT, escalation TEXT NOT NULL, description TEXT NOT NULL, private INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (id, version)
);

-- ---------------------------------------------------------------- mission / people
CREATE TABLE IF NOT EXISTS missions (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, mission_type TEXT NOT NULL, start_utc TEXT NOT NULL,
  planned_duration_days INTEGER, comm_delay_seconds REAL NOT NULL DEFAULT 0,
  earth_link_status TEXT NOT NULL DEFAULT 'online', is_synthetic INTEGER NOT NULL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS mission_environments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mission_id TEXT NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  phase TEXT NOT NULL, location TEXT NOT NULL, gravity_g REAL, start_utc TEXT NOT NULL, end_utc TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS ix_menv_mission ON mission_environments(mission_id, start_utc);
CREATE TABLE IF NOT EXISTS astronauts (
  id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id), name TEXT NOT NULL,
  call_sign TEXT, crew_role TEXT, birth_year INTEGER, glucose_monitoring_enabled INTEGER NOT NULL DEFAULT 0,
  is_synthetic INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  crew TEXT NOT NULL DEFAULT 'Prime Crew'  -- crew within the mission; a CMO oversees astronauts of the same mission+crew
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('astronaut','medical_officer','flight_surgeon','admin')),
  astronaut_id TEXT REFERENCES astronauts(id), active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, device_type TEXT NOT NULL, adapter TEXT NOT NULL, model TEXT, serial TEXT,
  mission_id TEXT NOT NULL REFERENCES missions(id), astronaut_id TEXT REFERENCES astronauts(id),
  location TEXT, api_key_hash TEXT, status TEXT NOT NULL DEFAULT 'disconnected',
  is_simulated INTEGER NOT NULL DEFAULT 1, hardware_validated INTEGER NOT NULL DEFAULT 0,
  last_seen_at TEXT, battery_pct REAL, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assessment_schedule (
  id INTEGER PRIMARY KEY AUTOINCREMENT, astronaut_id TEXT NOT NULL REFERENCES astronauts(id) ON DELETE CASCADE,
  task_code TEXT NOT NULL, title TEXT NOT NULL, metric_codes TEXT NOT NULL, interval_hours REAL NOT NULL,
  required INTEGER NOT NULL DEFAULT 1, clinician_directed INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  UNIQUE (astronaut_id, task_code)
);

-- ---------------------------------------------------------------- observations
CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL CHECK (subject_type IN ('astronaut','environment')),
  astronaut_id TEXT REFERENCES astronauts(id),
  mission_id TEXT NOT NULL REFERENCES missions(id),
  location TEXT,
  metric_code TEXT NOT NULL REFERENCES health_indicators(code),
  value_num REAL, value_text TEXT, value_bool INTEGER, value_json TEXT,
  unit TEXT NOT NULL,
  original_value TEXT NOT NULL, original_unit TEXT NOT NULL,
  measured_at TEXT NOT NULL, received_at TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type IN ('manual','medical_device','wearable','environmental_sensor','clinician','simulator')),
  device_id TEXT REFERENCES devices(id),
  quality TEXT NOT NULL CHECK (quality IN ('valid','questionable','unverified')),
  context TEXT NOT NULL DEFAULT '{}',
  notes TEXT,
  entered_by TEXT,
  payload_hash TEXT NOT NULL,
  batch_id TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  sim_run_id TEXT,
  is_private INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_obs_ast_metric_time ON observations(astronaut_id, metric_code, measured_at);
CREATE INDEX IF NOT EXISTS ix_obs_mission_metric_time ON observations(mission_id, metric_code, measured_at);
CREATE INDEX IF NOT EXISTS ix_obs_sim ON observations(sim_run_id);

CREATE TABLE IF NOT EXISTS sleep_records (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id),
  sleep_start TEXT NOT NULL, sleep_end TEXT NOT NULL, computed_duration_min REAL NOT NULL,
  reported_duration_min REAL, interruption_note TEXT, quality INTEGER, awakenings INTEGER,
  restfulness INTEGER, fatigue_after_waking INTEGER, scheduled_opportunity_min REAL,
  observation_id TEXT REFERENCES observations(id), source_type TEXT NOT NULL,
  is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sleep_ast ON sleep_records(astronaut_id, sleep_end);
CREATE TABLE IF NOT EXISTS mood_assessments (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id), assessed_at TEXT NOT NULL,
  mood INTEGER, stress INTEGER, fatigue INTEGER, sleep_rating INTEGER, workload INTEGER,
  connectedness INTEGER, note_for_medical TEXT, private_note TEXT, skipped TEXT NOT NULL DEFAULT '[]',
  is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mood_ast ON mood_assessments(astronaut_id, assessed_at);
CREATE TABLE IF NOT EXISTS exercise_records (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id), exercise_type TEXT NOT NULL,
  category TEXT NOT NULL, start_at TEXT NOT NULL, duration_min REAL, intensity TEXT,
  completion_status TEXT NOT NULL CHECK (completion_status IN ('completed','partial','skipped','planned')),
  performance_notes TEXT, observation_id TEXT REFERENCES observations(id), source_type TEXT NOT NULL,
  is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ex_ast ON exercise_records(astronaut_id, start_at);
CREATE TABLE IF NOT EXISTS nutrition_records (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id), recorded_at TEXT NOT NULL,
  record_type TEXT NOT NULL CHECK (record_type IN ('water','meal','snack')), water_ml REAL,
  description TEXT, energy_kcal REAL, appetite INTEGER, digestion_symptoms TEXT,
  source_type TEXT NOT NULL, is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_nut_ast ON nutrition_records(astronaut_id, recorded_at);
CREATE TABLE IF NOT EXISTS medication_records (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id), medication TEXT NOT NULL,
  dose_text TEXT, route TEXT, administered_at TEXT NOT NULL, approved_instruction_ref TEXT NOT NULL,
  recorded_by TEXT NOT NULL, notes TEXT, is_synthetic INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medical_history (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id),
  entry_type TEXT NOT NULL CHECK (entry_type IN ('allergy','condition','examination','prior_event','clinician_observation','procedure')),
  title TEXT NOT NULL, details TEXT, recorded_by TEXT NOT NULL, recorded_at TEXT NOT NULL,
  is_private INTEGER NOT NULL DEFAULT 1, is_synthetic INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------- baselines and assessment
CREATE TABLE IF NOT EXISTS health_baselines (
  id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL REFERENCES astronauts(id),
  metric_code TEXT NOT NULL REFERENCES health_indicators(code), context_key TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL, status TEXT NOT NULL CHECK (status IN ('draft','approved','retired')),
  source TEXT NOT NULL CHECK (source IN ('pre_mission','in_flight_window','clinician_entered')),
  mean REAL, sd REAL, n INTEGER NOT NULL DEFAULT 0, ref_low REAL, ref_high REAL, ref_approved_by TEXT,
  period_start TEXT, period_end TEXT, establishment_days INTEGER,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT, notes TEXT,
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  UNIQUE (astronaut_id, metric_code, context_key, version)
);
CREATE INDEX IF NOT EXISTS ix_base_lookup ON health_baselines(astronaut_id, metric_code, status);
CREATE TABLE IF NOT EXISTS baseline_observations (
  baseline_id TEXT NOT NULL REFERENCES health_baselines(id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
  PRIMARY KEY (baseline_id, observation_id)
);
CREATE TABLE IF NOT EXISTS health_assessments (
  id TEXT PRIMARY KEY, astronaut_id TEXT REFERENCES astronauts(id), mission_id TEXT NOT NULL REFERENCES missions(id),
  created_at TEXT NOT NULL, trigger TEXT NOT NULL, status TEXT NOT NULL,
  indicators TEXT NOT NULL, findings TEXT NOT NULL, baseline_comparisons TEXT NOT NULL,
  limitations TEXT NOT NULL, risk_ids TEXT NOT NULL, next_step TEXT NOT NULL,
  medical_review INTEGER NOT NULL, evidence_refs TEXT NOT NULL, rule_versions TEXT NOT NULL,
  is_private INTEGER NOT NULL DEFAULT 0, is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_asm_ast ON health_assessments(astronaut_id, created_at);
CREATE TABLE IF NOT EXISTS assessment_observations (
  assessment_id TEXT NOT NULL REFERENCES health_assessments(id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
  PRIMARY KEY (assessment_id, observation_id)
);

-- ---------------------------------------------------------------- response
CREATE TABLE IF NOT EXISTS medical_events (
  id TEXT PRIMARY KEY, astronaut_id TEXT REFERENCES astronauts(id), mission_id TEXT NOT NULL REFERENCES missions(id),
  title TEXT NOT NULL, category TEXT NOT NULL, risk_id TEXT REFERENCES risk_definitions(id),
  state TEXT NOT NULL CHECK (state IN ('DETECTED','VERIFYING','ACTIVE','ESCALATED','MONITORING','RESOLVED')),
  severity TEXT NOT NULL, protocol_id TEXT, protocol_version INTEGER,
  opened_at TEXT NOT NULL, updated_at TEXT NOT NULL, resolved_at TEXT,
  is_private INTEGER NOT NULL DEFAULT 0, is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_evt_state ON medical_events(state, opened_at);
CREATE TABLE IF NOT EXISTS medical_event_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL REFERENCES medical_events(id) ON DELETE CASCADE,
  from_state TEXT, to_state TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medical_event_actions (
  id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES medical_events(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL CHECK (action_type IN ('checklist_item','protocol_step','note','observation_link','escalation','notification','report')),
  description TEXT NOT NULL, performed_by TEXT NOT NULL, performed_at TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_evt_actions ON medical_event_actions(event_id, performed_at);
CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY, astronaut_id TEXT REFERENCES astronauts(id), mission_id TEXT NOT NULL REFERENCES missions(id),
  assessment_id TEXT REFERENCES health_assessments(id), medical_event_id TEXT REFERENCES medical_events(id),
  severity TEXT NOT NULL CHECK (severity IN ('INFORMATION','REASSESSMENT','MEDICAL_REVIEW','URGENT')),
  category TEXT NOT NULL CHECK (category IN ('health','environment','data')),
  rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL, rule_class TEXT NOT NULL,
  title TEXT NOT NULL, explanation TEXT NOT NULL, baseline_context TEXT NOT NULL DEFAULT '{}',
  related_symptoms TEXT NOT NULL DEFAULT '[]', next_step TEXT NOT NULL, protocol_id TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  ack_status TEXT NOT NULL DEFAULT 'unacknowledged', ack_by TEXT, ack_at TEXT,
  escalation_status TEXT NOT NULL DEFAULT 'not_escalated', escalated_at TEXT,
  resolution_status TEXT NOT NULL DEFAULT 'open', resolved_by TEXT, resolved_at TEXT, resolution_note TEXT,
  dedup_key TEXT NOT NULL, occurrence_count INTEGER NOT NULL DEFAULT 1,
  is_private INTEGER NOT NULL DEFAULT 0, is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_alert_open ON alerts(resolution_status, created_at);
CREATE INDEX IF NOT EXISTS ix_alert_dedup ON alerts(dedup_key, resolution_status);
CREATE TABLE IF NOT EXISTS alert_observations (
  alert_id TEXT NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
  PRIMARY KEY (alert_id, observation_id)
);
CREATE TABLE IF NOT EXISTS medical_reports (
  id TEXT PRIMARY KEY, event_id TEXT REFERENCES medical_events(id) ON DELETE CASCADE,
  astronaut_id TEXT REFERENCES astronauts(id), mission_id TEXT NOT NULL REFERENCES missions(id),
  created_at TEXT NOT NULL, created_by TEXT NOT NULL, content TEXT NOT NULL, rendered_text TEXT NOT NULL,
  content_hash TEXT NOT NULL, sync_status TEXT NOT NULL DEFAULT 'local',
  is_private INTEGER NOT NULL DEFAULT 1, is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT
);
CREATE TABLE IF NOT EXISTS environment_events (
  id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id), event_type TEXT NOT NULL,
  severity TEXT NOT NULL, location TEXT, started_at TEXT NOT NULL, ended_at TEXT, peak_value REAL, unit TEXT,
  description TEXT NOT NULL, rule_id TEXT, alert_id TEXT REFERENCES alerts(id),
  is_synthetic INTEGER NOT NULL DEFAULT 0, sim_run_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_envevt ON environment_events(mission_id, started_at);
CREATE TABLE IF NOT EXISTS environment_event_observations (
  event_id TEXT NOT NULL REFERENCES environment_events(id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
  PRIMARY KEY (event_id, observation_id)
);

-- ---------------------------------------------------------------- audit and sync
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, actor_role TEXT,
  action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT, details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_audit_at ON audit_log(at);
CREATE TABLE IF NOT EXISTS sync_queue (
  id TEXT PRIMARY KEY, item_type TEXT NOT NULL, item_id TEXT NOT NULL, payload TEXT NOT NULL,
  payload_hash TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, priority INTEGER NOT NULL DEFAULT 5,
  status TEXT NOT NULL CHECK (status IN ('pending','in_flight','delivered','acknowledged','failed','conflict')),
  attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, last_attempt_at TEXT, next_attempt_at TEXT,
  delivered_at TEXT, acknowledged_at TEXT, acknowledged_by TEXT, last_error TEXT, is_private INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_sync_status ON sync_queue(status, next_attempt_at);
-- Simulated ground-segment inbox (stands in for the flight-surgeon ground system in the prototype).
CREATE TABLE IF NOT EXISTS ground_inbox (
  idempotency_key TEXT PRIMARY KEY, item_type TEXT NOT NULL, item_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, received_at TEXT NOT NULL, acknowledged_at TEXT
);
CREATE TABLE IF NOT EXISTS telemetry_batches (
  idempotency_key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at TEXT NOT NULL
);
