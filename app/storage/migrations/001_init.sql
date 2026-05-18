-- ============================================================
-- Em Linh MKT v8 — Schema khởi tạo (migration 001)
-- Refer: F2C.1 (LUAT_2C_infra.md) + KE_HOACH_REFACTOR § PHẦN 2.4
-- Paradigm: 3 bảng riêng (KHÔNG nhúng JSON blob)
-- ============================================================

-- Bật WAL mode cho concurrent read (refer STRATEGY phụ lục "SQLite không Postgres")
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- Bảng 1: sessions — state machine + history (Scope 3)
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id              TEXT PRIMARY KEY,                           -- uuid v4
    stage                   TEXT NOT NULL DEFAULT 'GREETING',            -- GREETING/ASKING/CONFIRMING/DONE
    current_slot            TEXT,                                       -- vd "2.3"
    slot_attempts           TEXT NOT NULL DEFAULT '{}',                 -- JSON {slot_id: {consecutive, total}}
    deferred_slots          TEXT NOT NULL DEFAULT '{}',                 -- JSON {slot_id: {defer_at_turn, recheck_after_n_slots}}
    skipped_slots           TEXT NOT NULL DEFAULT '[]',                 -- JSON list
    flags                   TEXT NOT NULL DEFAULT '[]',                 -- JSON list of 15 flag enum
    detected_dealer_type    TEXT,                                       -- lua_lo/khoe/lo/ban/unknown
    dealer_type_history     TEXT NOT NULL DEFAULT '[]',                 -- JSON [(turn, type), ...]
    confirmation_status     TEXT NOT NULL DEFAULT 'PENDING',            -- PENDING/CONFIRMED/EDITED
    review_status           TEXT NOT NULL DEFAULT 'RAW',                -- RAW/UNDER_REVIEW/APPROVED/REJECTED
    history                 TEXT NOT NULL DEFAULT '[]',                 -- JSON list message {role, content, ts}
    turn_count              INTEGER NOT NULL DEFAULT 0,
    paused_for              TEXT,                                       -- NULL / "defensive" / "tam_su"
    address_form            TEXT NOT NULL DEFAULT 'anh',                -- anh / chị
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at               TEXT,                                       -- NULL nếu active
    channel                 TEXT NOT NULL DEFAULT 'web',                -- web / zalo / fb
    ip_address              TEXT,                                       -- cho rate limit
    user_agent              TEXT
);

CREATE INDEX IF NOT EXISTS idx_session_stage ON sessions(stage);
CREATE INDEX IF NOT EXISTS idx_session_updated ON sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_session_ip ON sessions(ip_address);

-- ============================================================
-- Bảng 2: dealer_profile_raw — data dealer cung cấp (Scope 1 + 2)
-- 28 trường = 6 REQUIRED + 16 OPTIONAL + 6 RAW SIGNAL (Scope 1)
--          + 12 auto-derive (Scope 2)
-- ============================================================
CREATE TABLE IF NOT EXISTS dealer_profile_raw (
    session_id              TEXT PRIMARY KEY,                           -- FK sessions.session_id

    -- ----------------------------------------------------------------
    -- Scope 1: chatbot thu trực tiếp qua 17 slot
    -- ----------------------------------------------------------------

    -- REQUIRED (6) — slot 1.1, 1.2, 1.3, 2.1, 2.2, 4.0
    dealer_name             TEXT,
    owner_name              TEXT,
    address                 TEXT,
    phone_or_zalo           TEXT,
    main_product            TEXT,
    brandkit_consent        TEXT,                                       -- "yes" / "no"

    -- OPTIONAL (16) — slot 2.1-2.6, 3.1-3.4, 4.2
    category_stack          TEXT NOT NULL DEFAULT '[]',                 -- JSON list ≥1 item
    business_model_signal   TEXT,
    est_team_size           INTEGER,
    team_stability_signal   TEXT,
    supplier_brands         TEXT NOT NULL DEFAULT '[]',                 -- JSON list
    customer_segment_signal TEXT,
    zalo                    TEXT,
    facebook                TEXT,
    primary_contact_channel TEXT,
    fb_marketing_status     TEXT,
    customer_old_percentage TEXT,
    customer_storage_method TEXT,
    customer_pain           TEXT,                                       -- Text dài raw (open question 3.3)
    payment_terms_signal    TEXT,
    color_accent            TEXT,
    feng_shui_signal        TEXT,

    -- RAW SIGNAL (6) — mining từ câu trả lời slot, cho Backend Scoring chấm C1-C9
    local_dominance_signal          TEXT,                               -- C6 (slot 1.2 bán kính)
    supplier_negotiation_signal     TEXT,                               -- C8 (slot 2.4 backup)
    community_network_signal        TEXT,                               -- C9 (slot 2.6 network)
    motivation_signal               TEXT,                               -- C5 (slot 3.3 động lực)
    warranty_responsibility_signal  TEXT,                               -- C4 NEW (slot 3.5 bảo hành)
    usp_signal                      TEXT,                               -- bonus slogan (slot 3.3)

    -- ----------------------------------------------------------------
    -- Scope 2: chatbot auto-derive (parse + LLM gen)
    -- ----------------------------------------------------------------
    province                TEXT,                                       -- parse từ address
    district                TEXT,                                       -- parse từ address
    province_specialty      TEXT,                                       -- lookup 50/63 tỉnh có specialty
    main_category           TEXT,                                       -- enum chuẩn hóa từ main_product
    dealer_type             TEXT,                                       -- enum: dai_ly/chu_xuong/tho_doi/nha_thau_nho/s_dich_vu/khac
    brand_name_short        TEXT,                                       -- LLM rút gọn (vd "Thanh Tùng")
    initials_full           TEXT,                                       -- vd "NKTT"
    initial_single          TEXT,                                       -- vd "T"
    contact_name            TEXT,                                       -- default = owner_name
    contact_role            TEXT NOT NULL DEFAULT 'Chủ cửa hàng',
    hotline                 TEXT,                                       -- default = phone_or_zalo
    slogan_options          TEXT NOT NULL DEFAULT '[]',                 -- JSON list 5 phương án LLM gen

    -- ----------------------------------------------------------------
    -- Metadata
    -- ----------------------------------------------------------------
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Index cho cross-session detect dealer return (refer CORE § K.3)
CREATE INDEX IF NOT EXISTS idx_dealer_phone ON dealer_profile_raw(phone_or_zalo);
CREATE INDEX IF NOT EXISTS idx_dealer_province ON dealer_profile_raw(province);

-- ============================================================
-- Bảng 3: admin_queue — escalation + review (F2C.8)
-- 13 trigger flag (HIGH/MEDIUM/LOW priority)
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_queue (
    queue_id                TEXT PRIMARY KEY,                           -- uuid v4
    session_id              TEXT NOT NULL,
    trigger                 TEXT NOT NULL,                              -- flag name (15 enum)
    priority                TEXT NOT NULL,                              -- HIGH / MEDIUM / LOW
    status                  TEXT NOT NULL DEFAULT 'PENDING',            -- PENDING / IN_REVIEW / APPROVED / REJECTED
    assigned_to             TEXT,                                       -- admin username
    notes                   TEXT,
    profile_snapshot        TEXT,                                       -- JSON snapshot dealer_profile_raw
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at             TEXT,

    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON admin_queue(status, priority, created_at);

-- ============================================================
-- HẾT migration 001
-- Scope 4 (c1..c9, c_score, tier, batch, dealer_id) KHÔNG có ở đây —
-- Backend Scoring service riêng quản (refer STRATEGY D7).
-- ============================================================
