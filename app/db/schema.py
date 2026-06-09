"""Database schema DDL — Parlant-style tables.

15 tables total:
- sessions, session_access_tokens (auth layer)
- messages, conversation_turns (event-sourced chat)
- dealer_profiles, profile_fields, profile_field_events (per-field profile)
- profile_corrections (correction audit trail)
- dealer_identities (dedup)
- flags (validation + escalation flags)
- admin_review_items (admin queue)
- logo_briefs, logo_jobs, logo_outputs, logo_issuances (logo pipeline)
- idempotency_records (API idempotency)

Follows LINHMKT schema exactly with minor adaptations for
Chatbot_dealer business logic (e.g. admin_review_items).
"""

SCHEMA_SQL = """
-- ============================================================
-- 1. Sessions + Auth
-- ============================================================

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    workflow_state TEXT NOT NULL,
    profile_id TEXT,
    session_token_hash TEXT NOT NULL,
    ip_hash TEXT,
    user_agent_hash TEXT,
    started_at TEXT NOT NULL,
    last_message_at TEXT,
    expires_at TEXT,
    closed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_profile_id ON sessions(profile_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status_updated ON sessions(status, last_message_at);

CREATE TABLE IF NOT EXISTS session_access_tokens (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_session_access_tokens_session
    ON session_access_tokens(session_id, status);

-- ============================================================
-- 2. Messages + Turns (event-sourced chat)
-- ============================================================

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    event_cursor INTEGER NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_id TEXT,
    source TEXT NOT NULL,
    message_type TEXT NOT NULL,
    text TEXT,
    raw_payload_json TEXT,
    voice_artifact_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session_cursor ON messages(session_id, event_cursor);
CREATE INDEX IF NOT EXISTS idx_messages_turn ON messages(turn_id);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    profile_id TEXT,
    active_rules_version TEXT NOT NULL,
    backend_turn_trace_json TEXT NOT NULL,
    dealer_profile_snapshot_json TEXT,
    field_status_summary_json TEXT,
    suggested_objective_json TEXT,
    matched_guideline_ids_json TEXT,
    active_journey_id TEXT,
    canned_response_ids_json TEXT,
    observations_json TEXT,
    model_id TEXT,
    backend_latency_ms INTEGER,
    turn_aggregation_latency_ms INTEGER,
    message_event_count INTEGER NOT NULL DEFAULT 0,
    final_reply_hash TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session_created ON conversation_turns(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_turns_profile_created ON conversation_turns(profile_id, created_at);

-- ============================================================
-- 3. Dealer Profiles (per-field model)
-- ============================================================

CREATE TABLE IF NOT EXISTS dealer_profiles (
    id TEXT PRIMARY KEY,
    canonical_key TEXT,
    review_status TEXT NOT NULL,
    logo_issued_status TEXT NOT NULL,
    created_from_session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    current_version INTEGER NOT NULL DEFAULT 1,
    confirmed_at TEXT,
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_profiles_canonical_key ON dealer_profiles(canonical_key);
CREATE INDEX IF NOT EXISTS idx_profiles_review_status ON dealer_profiles(review_status);

CREATE TABLE IF NOT EXISTS profile_fields (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    status TEXT NOT NULL,
    source_type TEXT NOT NULL,
    confidence REAL,
    affects_logo_brief INTEGER NOT NULL DEFAULT 0,
    evidence_message_ids_json TEXT NOT NULL DEFAULT '[]',
    validation_errors_json TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(profile_id, field_name)
);

CREATE INDEX IF NOT EXISTS idx_profile_fields_profile ON profile_fields(profile_id);

CREATE TABLE IF NOT EXISTS profile_field_events (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    old_raw_value TEXT,
    old_normalized_value TEXT,
    new_raw_value TEXT,
    new_normalized_value TEXT,
    source_type TEXT NOT NULL,
    evidence_message_id TEXT,
    validation_errors_json TEXT NOT NULL DEFAULT '[]',
    actor_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_field_events_profile_created
    ON profile_field_events(profile_id, created_at);
CREATE INDEX IF NOT EXISTS idx_field_events_field
    ON profile_field_events(profile_id, field_name, created_at);

-- ============================================================
-- 4. Profile Corrections (audit trail)
-- ============================================================

CREATE TABLE IF NOT EXISTS profile_corrections (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT NOT NULL,
    is_correction INTEGER NOT NULL DEFAULT 1,
    affects_logo_brief INTEGER NOT NULL DEFAULT 0,
    review_reset_required INTEGER NOT NULL DEFAULT 0,
    after_logo_issued INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- ============================================================
-- 5. Dealer Identities (dedup by phone + name)
-- ============================================================

CREATE TABLE IF NOT EXISTS dealer_identities (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    normalized_phone_or_zalo TEXT NOT NULL,
    normalized_dealer_name TEXT NOT NULL,
    canonical_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ============================================================
-- 6. Flags (validation + escalation)
-- ============================================================

CREATE TABLE IF NOT EXISTS flags (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    profile_id TEXT REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
    field_name TEXT,
    flag_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_flags_profile_status ON flags(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_flags_session_status ON flags(session_id, status);
CREATE INDEX IF NOT EXISTS idx_flags_name_status ON flags(flag_name, status);

-- ============================================================
-- 7. Admin Review Items
-- ============================================================

CREATE TABLE IF NOT EXISTS admin_review_items (
    id TEXT PRIMARY KEY,
    profile_id TEXT REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    flag_id TEXT REFERENCES flags(id) ON DELETE SET NULL,
    review_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_admin_review_status
    ON admin_review_items(status, review_type, priority);

-- ============================================================
-- 8. Logo Pipeline
-- ============================================================

CREATE TABLE IF NOT EXISTS logo_briefs (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    profile_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    dealer_name TEXT NOT NULL,
    logo_initials TEXT NOT NULL,
    slogan TEXT NOT NULL,
    phone_or_zalo TEXT NOT NULL,
    main_product TEXT NOT NULL,
    business_model_signal TEXT NOT NULL,
    color_accent TEXT,
    logo_style TEXT,
    design_specs_json TEXT NOT NULL DEFAULT '{}',
    source_field_ids_json TEXT NOT NULL DEFAULT '[]',
    confirmed_by_message_id TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logo_jobs (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    brief_id TEXT NOT NULL REFERENCES logo_briefs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    canonical_key TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    requested_count INTEGER NOT NULL DEFAULT 3,
    result_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_logo_jobs_session ON logo_jobs(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_logo_jobs_profile ON logo_jobs(profile_id, created_at);

CREATE TABLE IF NOT EXISTS logo_outputs (
    id TEXT PRIMARY KEY,
    logo_job_id TEXT NOT NULL REFERENCES logo_jobs(id) ON DELETE CASCADE,
    variant_no INTEGER NOT NULL,
    status TEXT NOT NULL,
    image_url TEXT,
    thumbnail_url TEXT,
    provider_asset_id TEXT,
    prompt_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(logo_job_id, variant_no)
);

CREATE TABLE IF NOT EXISTS logo_issuances (
    id TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE,
    profile_id TEXT NOT NULL REFERENCES dealer_profiles(id) ON DELETE CASCADE,
    logo_job_id TEXT NOT NULL REFERENCES logo_jobs(id) ON DELETE CASCADE,
    issued_count INTEGER NOT NULL DEFAULT 3,
    issued_at TEXT NOT NULL
);

-- ============================================================
-- 9. Idempotency Records (API dedup)
-- ============================================================

CREATE TABLE IF NOT EXISTS idempotency_records (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, method, path, idempotency_key)
);
"""
