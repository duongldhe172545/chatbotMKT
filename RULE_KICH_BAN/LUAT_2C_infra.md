# LUẬT 2C — Infrastructure (storage + concurrency + spam guard + monitoring)

> **Vai trò:** Spec TECHNICAL — non-LLM infrastructure: session lifecycle,
> spam guard, rate limit, cache, monitoring, data files, admin queue.
> Audience: backend / infra / SRE.
>
> **Cross-ref:**
> - ⬆ CORE — `EM_LINH_MKT_CORE.md` § K (recovery), § N (vận hành)
> - ↔ File 2A — `LUAT_2A_core.md` (state machine, schema)
> - ↔ File 2B — `LUAT_2B_llm.md` (LLM cache, guards)
> - ↔ File 1C — `KICH_BAN_1C_edgecase.md` § 13 (escalation queue)

---

## ⚠️ NHẮC LẠI

```
Infrastructure phục vụ correctness + reliability, KHÔNG được làm
mất data dealer. Mọi storage operation phải atomic + idempotent.

Concurrency: 1 dealer = 1 session = 1 connection lock. Không cho 2
worker xử cùng session đồng thời (gây race).
```

## ⚠️ DISCLAIMER

```
TẤT CẢ CONFIG VALUE + THRESHOLD + SCHEMA + SCRIPT EXAMPLE TRONG FILE
NÀY LÀ VÍ DỤ TƯỢNG TRƯNG — KHÔNG ĐƯỢC KHÓA CỨNG CASE.

Engine PHẢI cover MỌI shape tương tự với cùng yêu cầu kỹ thuật, không
phải match đúng số/key/path ví dụ. Threshold (rate limit, timeout, cache
TTL) là default suggest cho pilot — production có thể tune.

Ví dụ schema SQL / Redis pattern / metric name là gợi ý — implementation
thật có thể đổi tên cột / namespace / metric label miễn là đảm bảo
contract của rule.
```

---

## VERSION & CHANGELOG

**Version:** v0.1.5-draft
**Cập nhật:** 2026-05-18

| Ngày | Version | Thay đổi |
|---|---|---|
| 2026-05-18 | v0.1.5-draft | Refactor "không khoá case" đồng bộ KICH_BAN_1A v0.3.0 + LUAT_2A v0.2.5: (1) F2C.7 data files — bỏ `data/province_specialty.json` khỏi danh sách (vi phạm khoá case). Thêm note nguyên tắc "data file chỉ chứa LUẬT/ENUM hạt nhân, cấm lookup table mapping X → Y cụ thể". Bỏ sample data + watch_file cho province_specialty. (2) F2C.7 acceptance test — bỏ case "add tỉnh mới vào province_specialty.json". (3) F2C.5 cache table — bỏ "Province specialty" entry (in-memory load 1 lần). Thêm "Local hook (LLM)" Phase 2 — cache 7d Redis. (4) F2C.1 schema column `province_specialty` ghi DEPRECATED (giữ column backward compat, code không write). |
| 2026-05-15 | v0.1.4-draft | Spec consistency BATCH 4: (1) F2C.1 Schema refactor: 1 bảng `sessions` JSON blob → **3 bảng riêng** (`sessions` state machine + `dealer_profile_raw` 28 trường Scope 1+2 + `admin_queue`) — sync với KE_HOACH § 2.4 DDL canonical. Index `phone_or_zalo` cho cross-session detect. Schema bảng `sessions` mở rộng `deferred_slots` JSON + `paused_for` field. (2) F2C.8 admin_queue trigger 9 → **13** (thêm `hallucinate` HIGH, `pii_leak` HIGH, `brand_not_in_whitelist` MEDIUM, `voice_quality_poor` LOW). Note 2 flag KHÔNG trigger queue (`garbage_input` + `dealer_too_defensive` — bot tự handle). Sync `phone_invalid_after_retry` source pointer "F2A.5" → "File 1C § 12". |
| 2026-05-15 | v0.1.3-draft | Spec consistency BATCH 3: thêm § DISCLAIMER toàn cục — config value, threshold, schema, script example trong file là VÍ DỤ TƯỢNG TRƯNG, KHÔNG khóa cứng case. Production có thể tune threshold/cache TTL/metric name miễn đảm bảo contract của rule. |
| 2026-05-15 | v0.1.2-draft | Spec consistency BATCH 2: F2C.2 Spam guard pointer "CORE § J.7 (chống abuse)" → "CORE § K.5 (spam guard 4 layers)" — § J.7 không tồn tại trong CORE, § K.5 là nguyên tắc gốc thật. Áp dụng cùng 1 thay đổi ở 3 chỗ: heading line 185, Cross-ref line 303, bảng cuối line 1033. Thêm note hierarchy "CORE = nguyên tắc, 2C = detail rate limit + abuse score". |
| 2026-05-15 | v0.1.1-draft | Spec consistency: F2C.3 Concurrency thêm "Phase deployment" table — Phase 1-3 dùng in-memory adapter (cùng interface), Phase 4 chuyển Redis cho scale. Sync với STRATEGY phụ lục "Redis defer Phase 4" + KE_HOACH_REFACTOR § 0.4. Trước đây F2C.3 dùng `redis.set()` ngay từ đầu → dev có thể implement Redis nhầm Phase 1. |
| 2026-05-14 | v0.1.0-draft | Tạo file — 8 rule infrastructure đầy đủ |

---

## MỤC LỤC

- [F2C.1 — Session lifecycle + storage](#f2c1--session-lifecycle--storage)
- [F2C.2 — Spam guard (rate limit + abuse detection)](#f2c2--spam-guard)
- [F2C.3 — Concurrency control](#f2c3--concurrency-control)
- [F2C.4 — Timeout + retry policy](#f2c4--timeout--retry-policy)
- [F2C.5 — Cache (LLM + intent + address)](#f2c5--cache)
- [F2C.6 — Monitoring + alerting](#f2c6--monitoring--alerting)
- [F2C.7 — Data files (province, brand, etc.)](#f2c7--data-files)
- [F2C.8 — Admin queue + review workflow](#f2c8--admin-queue)
- [Cross-ref](#cross-ref)

---

## F2C.1 — Session lifecycle + storage

**Tham chiếu CORE:** § N (vận hành)
**Tham chiếu File 2A:** F2A.1 (stages), F2A.3 (schema)

### Yêu cầu

- 1 dealer = 1 session = 1 row trong DB
- Session có lifecycle: `CREATED → ACTIVE → TIMEOUT/DONE/ESCALATED`
- Mọi state change → atomic write (transaction)
- Backup snapshot mỗi 5 phút

### Schema 3 bảng (canonical: `migrations/001_init.sql` per KE_HOACH § 2.4)

> **Quyết định kiến trúc:** chia **3 bảng riêng** (sessions / dealer_profile_raw
> / admin_queue) — KHÔNG nhúng JSON blob để dễ index + query admin. Refer
> KE_HOACH_REFACTOR.md § PHẦN 2.4 cho DDL đầy đủ.

#### Bảng 1: `sessions` — state machine + history (Scope 3)

```sql
CREATE TABLE sessions (
    session_id              TEXT PRIMARY KEY,      -- uuid v4
    stage                   TEXT NOT NULL,         -- GREETING/ASKING/CONFIRMING/DONE
    current_slot            TEXT,                  -- vd "2.3"
    slot_attempts           TEXT NOT NULL DEFAULT '{}',  -- JSON dict {slot_id: {consecutive, total}}
    deferred_slots          TEXT NOT NULL DEFAULT '{}',  -- JSON dict (F2A.4 step 2.7)
    skipped_slots           TEXT NOT NULL DEFAULT '[]',  -- JSON list
    flags                   TEXT NOT NULL DEFAULT '[]',  -- JSON list (xem F2A.3 Scope 3 — 15 enum)
    detected_dealer_type    TEXT,                  -- lua_lo/khoe/lo/ban/unknown
    dealer_type_history     TEXT NOT NULL DEFAULT '[]',  -- JSON [(turn, type), ...]
    confirmation_status     TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/CONFIRMED/EDITED
    review_status           TEXT NOT NULL DEFAULT 'RAW',      -- RAW/UNDER_REVIEW/APPROVED/REJECTED
    history                 TEXT NOT NULL DEFAULT '[]',       -- JSON list message
    turn_count              INTEGER NOT NULL DEFAULT 0,
    paused_for              TEXT,                  -- None/"defensive"/"tam_su"
    address_form            TEXT NOT NULL DEFAULT 'anh',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    closed_at               TEXT,                  -- null nếu active
    channel                 TEXT DEFAULT 'web',
    ip_address              TEXT,
    user_agent              TEXT
);

CREATE INDEX idx_session_stage ON sessions(stage);
CREATE INDEX idx_session_updated ON sessions(updated_at);
CREATE INDEX idx_session_ip ON sessions(ip_address);
```

#### Bảng 2: `dealer_profile_raw` — data dealer cung cấp (Scope 1+2)

```sql
CREATE TABLE dealer_profile_raw (
    session_id          TEXT PRIMARY KEY,          -- FK sessions.session_id
    -- Scope 1: chatbot thu trực tiếp (6 REQUIRED + 16 OPTIONAL + 6 RAW signal)
    dealer_name         TEXT,
    owner_name          TEXT,
    address             TEXT,
    phone_or_zalo       TEXT,
    main_product        TEXT,
    brandkit_consent    TEXT,                      -- yes/no
    category_stack      TEXT NOT NULL DEFAULT '[]',
    business_model_signal TEXT,
    est_team_size       INTEGER,
    team_stability_signal TEXT,
    supplier_brands     TEXT NOT NULL DEFAULT '[]',
    customer_segment_signal TEXT,
    zalo                TEXT,
    facebook            TEXT,
    primary_contact_channel TEXT,
    fb_marketing_status TEXT,
    customer_old_percentage TEXT,
    customer_storage_method TEXT,
    customer_pain       TEXT,
    payment_terms_signal TEXT,
    warranty_responsibility_signal TEXT,           -- NEW slot 3.5
    color_accent        TEXT,
    feng_shui_signal    TEXT,
    -- 6 RAW signal cho 9 tiêu chí (mining)
    local_dominance_signal TEXT,                   -- C6 (slot 1.2)
    supplier_negotiation_signal TEXT,              -- C8 (slot 2.4)
    community_network_signal TEXT,                 -- C9 (slot 2.6)
    motivation_signal TEXT,                        -- C5 (slot 3.3)
    usp_signal          TEXT,                      -- bonus slogan
    -- Scope 2: chatbot auto-derive
    province            TEXT,
    district            TEXT,
    province_specialty  TEXT,  -- DEPRECATED 2026-05-18 (khoá case) — giữ column backward compat, code không write
    main_category       TEXT,
    dealer_type         TEXT,
    brand_name_short    TEXT,
    initials_full       TEXT,
    initial_single      TEXT,
    contact_name        TEXT,
    contact_role        TEXT NOT NULL DEFAULT 'Chủ cửa hàng',
    hotline             TEXT,
    slogan_options      TEXT NOT NULL DEFAULT '[]',  -- JSON list 5 phương án
    -- Metadata
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_dealer_phone ON dealer_profile_raw(phone_or_zalo);
```

#### Bảng 3: `admin_queue` — escalation + review (F2C.8)

```sql
CREATE TABLE admin_queue (
    queue_id            TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    trigger             TEXT NOT NULL,             -- flag name (15 enum)
    priority            TEXT NOT NULL,             -- HIGH/MEDIUM/LOW
    status              TEXT NOT NULL DEFAULT 'PENDING',
    assigned_to         TEXT,
    notes               TEXT,
    profile_snapshot    TEXT,                      -- JSON
    created_at          TEXT NOT NULL,
    resolved_at         TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_queue_status ON admin_queue(status, priority, created_at);
```

→ DDL chính thức: `app/storage/migrations/001_init.sql` (KE_HOACH § 2.4).
→ Scope 4 (`c1..c9, c_score, tier, batch, dealer_id`) **không** thuộc 3 bảng
  này — Backend Scoring service riêng quản, refer STRATEGY D7.

### Lifecycle transitions

```
CREATED (session_id gen, profile rỗng)
   ↓ first message từ dealer
ACTIVE (stage = GREETING)
   ↓ dealer ack greeting → stage = ASKING
   ↓ ASKING → CONFIRMING → DONE
   ↓
DONE (closed_at set, session inactive)
   |
   | OR
   ↓
TIMEOUT (session > 1 giờ không activity → soft-end)
   |
   | OR
   ↓
ESCALATED (flag escalation trigger → push admin queue)
```

### Atomic write pattern

```python
async def update_session(session_id: str, updates: dict):
    async with db.transaction():
        # 1. SELECT FOR UPDATE (lock row)
        session = await db.fetchrow(
            "SELECT * FROM sessions WHERE session_id = $1 FOR UPDATE",
            session_id,
        )

        # 2. Merge updates
        new_state = {**session, **updates, "updated_at": now()}

        # 3. UPDATE
        await db.execute(
            "UPDATE sessions SET ... WHERE session_id = $1",
            session_id,
        )

        # 4. Append to history if message
        if "message" in updates:
            await db.execute("INSERT INTO session_history ...")
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `SESSION_TIMEOUT_S` | 3600 (1h) | Inactive → TIMEOUT |
| `SESSION_BACKUP_INTERVAL_S` | 300 (5p) | Snapshot mỗi N giây |
| `MAX_HISTORY_PER_SESSION` | 200 turn | Sau N → archive |
| `SESSION_TABLE` | `sessions` | DB table |

### Acceptance test

✅ **PASS:**
- 1 dealer = 1 session_id, không duplicate
- Mọi update atomic — không có race condition
- TIMEOUT đúng sau 1h inactive
- Backup snapshot không miss

❌ **FAIL:**
- 2 worker update session đồng thời → state corrupt
- TIMEOUT không trigger sau 1h
- Crash giữa update → state partial (vi phạm atomic)

### Constraints

- Mọi update PHẢI trong transaction
- TIMEOUT trigger qua background scheduler
- Backup snapshot mỗi 5 phút (không pause khi DB lock)

### Pointer implementation

→ `app/storage/sqlite_store.py` § session CRUD
→ `app/core/session.py` § Session dataclass + lifecycle
→ `app/scheduler/timeout_worker.py` § background TIMEOUT trigger

### Cross-ref

- ⬆ CORE § N (vận hành)
- ⬅ File 2A § F2A.1 (stages), § F2A.3 (schema 4 scope)
- ➡ F2C.3 (concurrency lock pattern)
- ➡ F2C.6 (monitoring TIMEOUT rate)

---

## F2C.2 — Spam guard (rate limit + abuse detection)

**Tham chiếu CORE:** § K.5 (đại lý spam / không phải dealer thật)
**Tham chiếu File 1C:** § 5 (abuse), § 6 (troll)

> **Hierarchy note:** CORE § K.5 nêu nguyên tắc "spam guard 4 layers tự
> handle". Detail rate limit threshold + abuse score algorithm sống ở
> rule này — file con mở rộng CORE.

### Yêu cầu

Engine chống:
1. **Rate limit IP** — 1 IP không tạo > N session / hour
2. **Rate limit message** — 1 session không gửi > N message / minute
3. **Abuse detection** — flag dealer dựa trên pattern (spam, troll)
4. **CAPTCHA fallback** — sau N suspicious → require CAPTCHA (future)

### Rate limit rules

| Layer | Limit | Action |
|---|---|---|
| 1 IP / 1h | 5 sessions | Block tạo session mới, polite reject |
| 1 IP / 1h | 10 sessions (hard) | Block hoàn toàn 24h |
| 1 session / 1min | 30 messages | Throttle (delay response 5s) |
| 1 session / 1min | 60 messages (hard) | Force end session |
| 1 IP / 1 ngày | 50 sessions | Block IP 7 ngày |

### Algorithm

```python
async def check_rate_limit(ip: str, session_id: str | None):
    # IP rate limit
    ip_sessions_1h = await redis.get(f"ip:{ip}:sessions:1h") or 0
    if ip_sessions_1h >= 5:
        if ip_sessions_1h >= 10:
            return Block(reason="IP_HARD_LIMIT")
        return Block(reason="IP_SOFT_LIMIT")

    # Message rate limit (per session)
    if session_id:
        msg_count = await redis.get(f"session:{session_id}:msgs:1min") or 0
        if msg_count >= 30:
            if msg_count >= 60:
                return Block(reason="SESSION_HARD_LIMIT")
            return Throttle(delay_s=5)

    return Allow()
```

### Abuse detection (signal aggregation)

```python
ABUSE_SIGNALS = {
    "prompt_injection_attempts": {"weight": 5, "max": 10},
    "abusive_language_count":    {"weight": 3, "max": 9},
    "address_blacklist_count":   {"weight": 4, "max": 8},
    "garbage_input_count":       {"weight": 1, "max": 5},
    "rapid_message_burst":       {"weight": 2, "max": 6},
}

def calculate_abuse_score(session) -> int:
    score = 0
    for signal, conf in ABUSE_SIGNALS.items():
        count = getattr(session, signal, 0)
        score += min(count, conf["max"]) * conf["weight"]
    return score

if abuse_score >= ABUSE_THRESHOLD (=15):
    → force end session
    → IP added to "watch_list"
    → push admin queue
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `IP_LIMIT_SOFT_PER_H` | 5 | Soft block sau N session/h |
| `IP_LIMIT_HARD_PER_H` | 10 | Hard block 24h |
| `MSG_LIMIT_PER_MIN` | 30 | Throttle |
| `MSG_LIMIT_HARD_PER_MIN` | 60 | Force end |
| `ABUSE_THRESHOLD` | 15 | Score → force end |
| `WATCH_LIST_DURATION_D` | 7 | IP trong watch list bao lâu |

### Acceptance test

```
Case: 1 IP tạo 6 session trong 1h
   → 6th session: Block (IP_SOFT_LIMIT)
   → Bot ack: "Dạ em thấy IP của anh đã tạo nhiều session rồi —
              anh thử lại sau 1 giờ giúp em ạ."

Case: Session gửi 35 message / 1min
   → Throttle: delay 5s/response

Case: Dealer 3 lần prompt inject (5×3=15) → score=15 ≥ threshold
   → Force end session + watch_list IP
```

✅ **PASS:**
- IP limit chặn brute force tạo session
- Message rate limit chặn flood
- Abuse score aggregate đúng
- Watch list expire sau N ngày

❌ **FAIL:**
- 1 IP tạo 100 session/h mà không block
- Force end nhưng IP vẫn tạo session mới ngay
- Abuse score đếm sai (vd: 1 lần inject → score đột ngột >15)

### Constraints

- Redis dùng cho rate limit (không SQLite — slow)
- Watch list lưu DB (persistent) + Redis (fast lookup)
- KHÔNG block legitimate dealer (vd shared IP công ty) — có whitelist mechanism

### Pointer implementation

→ `app/guards/rate_limit.py` § `check_rate_limit`
→ `app/guards/abuse_detector.py` § `calculate_abuse_score`
→ `app/cache/redis_client.py` § rate limit counters

### Cross-ref

- ⬆ CORE § K.5 (spam guard 4 layers — nguyên tắc gốc)
- ⬅ File 1C § 5 (abuse), § 6 (troll)
- ➡ F2C.6 (monitoring abuse events)
- ➡ F2C.8 (admin queue khi escalate)

---

## F2C.3 — Concurrency control

**Tham chiếu File 2C:** F2C.1 (atomic write)
**Tham chiếu STRATEGY:** Phụ lục § "Vì sao Redis defer Phase 4"

### Phase deployment

| Phase | Backend | Rationale |
|---|---|---|
| **Phase 1-3** (pilot ≤ 100 dealer/ngày) | **In-memory** adapter cùng interface (Python `threading.Lock` + `collections.deque`) | Đủ cho 1 process FastAPI single-worker. Không cần infra mới |
| **Phase 4** (scale ≥ 500 dealer/ngày) | **Redis** `SET NX EX 30` (lock pattern dưới) | Multi-worker / multi-replica → cần distributed lock |

→ Code dùng interface chung `app/cache/session_lock.py:SessionLock` —
đổi backend chỉ sửa config, không sửa business logic. Refer
KE_HOACH_REFACTOR § 0.4 và § 0.9.

### Yêu cầu

- 1 session = 1 worker xử / 1 thời điểm
- 2 message liên tiếp cùng session → queue (FIFO)
- Worker crash → release lock auto (TTL lock)

### Lock pattern

```python
async def handle_message(session_id: str, message: str):
    lock_key = f"lock:session:{session_id}"

    # Acquire lock với TTL 30s (worker crash → auto release)
    acquired = await redis.set(lock_key, worker_id, ex=30, nx=True)

    if not acquired:
        # Đã có worker khác xử
        await redis.lpush(f"queue:session:{session_id}", message)
        return WaitingInQueue()

    try:
        # Xử message
        response = await process(session_id, message)

        # Check queue cho message tiếp theo
        next_msg = await redis.rpop(f"queue:session:{session_id}")
        if next_msg:
            await handle_message(session_id, next_msg)  # process tiếp

        return response
    finally:
        await redis.delete(lock_key)
```

### Race condition prevention

| Risk | Mitigation |
|---|---|
| 2 message cùng session đồng thời | Redis lock + queue |
| Update session khi đang process | DB SELECT FOR UPDATE |
| Worker crash giữa lock | Redis TTL 30s auto release |
| Race giữa state update + history append | Single transaction |

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `LOCK_TTL_S` | 30 | Lock auto release sau N giây |
| `QUEUE_MAX_LEN_PER_SESSION` | 10 | Queue max trước khi reject |
| `WORKER_POOL_SIZE` | 10 | Số worker xử đồng thời |
| `WORKER_TIMEOUT_S` | 25 | Worker timeout < LOCK_TTL |

### Acceptance test

```
Case: 2 message cùng session arrive cách nhau 100ms
  → Worker 1 acquire lock → process msg 1
  → Worker 2 lock fail → push msg 2 vào queue
  → Worker 1 done → pop queue → process msg 2

Case: Worker crash giữa process
  → Lock TTL expire sau 30s → next request acquire được lock
  → State có thể partial → engine detect và recover (next message)
```

✅ **PASS:**
- 2 message cùng session không xử đồng thời
- Worker crash → lock release
- Queue order FIFO

❌ **FAIL:**
- Lock không release sau worker crash → session stuck forever
- Queue overflow > 10 message → DOS protection failed
- 2 worker cùng acquire lock (impossible nếu Redis SET NX đúng)

### Constraints

- LOCK_TTL_S > WORKER_TIMEOUT_S (đảm bảo worker done trước lock expire)
- Queue per session, không global queue
- Worker pool có limit để chống resource exhaustion

### Pointer implementation

→ `app/concurrency/session_lock.py` § `acquire_session_lock`
→ `app/workers/message_processor.py` § worker pool

### Cross-ref

- ⬆ File 2C § F2C.1 (atomic write)
- ➡ F2C.4 (timeout — lock TTL relationship)

---

## F2C.4 — Timeout + retry policy

**Tham chiếu CORE:** § K (recovery)

### Yêu cầu

Các timeout layer trong system:

| Layer | Timeout | Action khi expire |
|---|---|---|
| **LLM call** | 30s | Retry 2 lần, sau đó fallback safe ack |
| **DB query** | 5s | Retry 1 lần, log error |
| **Redis** | 1s | Bypass cache, gọi source-of-truth |
| **Session inactive** | 1h | Soft-end TIMEOUT |
| **Confirming silence** | 10p sau nhắc | Soft-close (status=PENDING) |
| **Worker process** | 25s | Kill + push admin queue |
| **STT voice** | 10s | Ask dealer "có thể gõ chữ giúp em không" |

### Retry policy (exponential backoff)

```python
async def call_with_retry(fn, max_retries=2, base_delay=1.0):
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except (TimeoutError, ConnectionError) as e:
            if attempt == max_retries:
                raise  # final attempt fail
            delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
            await asyncio.sleep(delay)
```

### LLM fallback safe ack

Khi LLM call fail sau N retry → engine fallback safe ack (KHÔNG block dealer):

```python
FALLBACK_ACK = {
    "slot": "Dạ em ghi nhận rồi ạ. Mình tiếp tục nhé.",
    "greeting": "Dạ em chào anh ạ. Mình bắt đầu trò chuyện một chút nhé?",
    "closing": "Em cảm ơn anh đã dành thời gian. Hẹn gặp lại anh!",
    "confirming": "Dạ em đã ghi nhận đủ thông tin ạ. Anh duyệt giúp em với.",
}
```

→ Log error → admin notify → KHÔNG ép dealer wait.

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `LLM_TIMEOUT_S` | 30 | LLM call timeout |
| `LLM_RETRY_COUNT` | 2 | Số retry trước fallback |
| `LLM_BACKOFF_BASE_S` | 1.0 | Backoff base |
| `DB_TIMEOUT_S` | 5 | DB query timeout |
| `DB_RETRY_COUNT` | 1 | Retry DB |
| `REDIS_TIMEOUT_S` | 1 | Redis timeout |

### Acceptance test

```
Case: LLM call timeout 30s
  → Retry attempt 2 (delay 1s)
  → Retry attempt 3 (delay 2s)
  → Fail final → fallback safe ack
  → Bot vẫn respond dealer (không hang)
  → Log error + admin notify

Case: DB query slow > 5s
  → Retry 1 lần
  → Fail → log error, return 503 với polite message
```

✅ **PASS:**
- LLM fail 100% → dealer vẫn nhận fallback ack
- DB slow → retry + log
- Worker timeout không block infinitely

❌ **FAIL:**
- LLM timeout → dealer wait 30s+ không response
- DB query không có timeout → worker hang
- Fallback ack lộ "LLM lỗi" / technical detail

### Constraints

- Mọi external call có timeout
- Fallback ack KHÔNG lộ technical error
- Retry exponential backoff (không retry tức thời)

### Pointer implementation

→ `app/utils/retry.py` § `call_with_retry`
→ `app/llm/fallback.py` § `FALLBACK_ACK` + `get_fallback`
→ `app/db/timeout_wrapper.py` § DB timeout middleware

### Cross-ref

- ⬆ CORE § K (recovery)
- ➡ F2C.6 (monitoring timeout rate)

---

## F2C.5 — Cache (LLM + intent + address)

**Tham chiếu File 2B:** F2B.3 (intent cache), F2B.5 (STT cache), F2B.6 (address cache)

### Yêu cầu

Cache các operation đắt để:
1. Tiết kiệm LLM cost
2. Giảm latency
3. Consistent result (cùng input → cùng output)

### Cache layers

| Cache | Key | TTL | Store |
|---|---|---|---|
| **LLM intent classify** | `intent:{hash(message+context)}` | 1h | Redis |
| **STT brand correct** | `brand:{hash(text)}` | 24h | Redis |
| **Address parse** | `addr:{hash(raw)}` | 24h | Redis |
| **Slogan options** | `slogan:{dealer_name}:{main_product}` | 7d | Redis (vì same dealer name → same slogan) |
| **Local hook (LLM)** | `local_hook:{province}:{dealer_type}` | 7d | Redis — Phase 2 (LLM gen, cache để giảm cost) |
| **System prompt build** | `sys_prompt:{slot}:{dealer_type}` | 1h | In-memory |

### Cache invalidation

```python
# Per-session cache: invalidate khi session DONE
async def invalidate_session_cache(session_id: str):
    keys = await redis.keys(f"*:{session_id}:*")
    if keys:
        await redis.delete(*keys)

# Global cache: invalidate khi config/data update
# - Brand list: load lại khi BRAND_LIST update
# - Province list: load lại khi data/province_list.json change
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `CACHE_BACKEND` | Redis | Production |
| `CACHE_BACKEND_DEV` | In-memory dict | Dev local |
| `LLM_CACHE_TTL_H` | 1 | LLM result |
| `STT_CACHE_TTL_H` | 24 | STT correction |
| `ADDRESS_CACHE_TTL_H` | 24 | Address parse |
| `MAX_CACHE_KEY_LEN` | 250 | Redis limit |

### Acceptance test

```
Case: Cùng message "Tùng" classified intent 100 lần
  → Lần 1: gọi LLM, lưu cache
  → Lần 2-100: hit cache, không gọi LLM
  → Tiết kiệm 99% cost

Case: Address "Hà Nội" parse 50 session khác nhau
  → Lần 1: gọi LLM
  → Lần 2-50: hit cache (cùng raw text)
  → Consistent province=Hà Nội

Case: data/province_specialty.json update
  → Cache invalidate
  → Lần next request load lại từ file
```

✅ **PASS:**
- Cache hit rate ≥ 50% trong session
- Save 50%+ LLM cost
- Consistent result cùng input

❌ **FAIL:**
- Cache TTL quá dài (vd 30 ngày) → outdated
- Cache key collision (vd cache global cho intent personalized)
- Cache không invalidate khi data file update
- Cache Redis fail → engine crash (phải fallback gọi source-of-truth)

### Constraints

- TTL phù hợp với mức "tươi" của data
- Cache fail không block (fallback gọi source-of-truth)
- Cache key có namespace rõ ràng

### Pointer implementation

→ `app/cache/redis_client.py` § generic cache wrapper
→ `app/cache/llm_cache.py` § LLM-specific cache
→ `app/cache/data_loaders.py` § in-memory load với file-watch invalidation

### Cross-ref

- ⬅ File 2B § F2B.3, § F2B.5, § F2B.6 (specific caches)
- ➡ F2C.6 (monitor cache hit rate)

---

## F2C.6 — Monitoring + alerting

**Tham chiếu CORE:** § N (vận hành)

### Yêu cầu

Monitor 4 dimension:
1. **Health** — service up, DB up, Redis up
2. **Performance** — latency, throughput, cache hit rate
3. **Quality** — sanity check fail rate, guard trigger rate
4. **Business** — sessions/day, CONFIRMED rate, escalation rate

### Metrics

| Metric | Type | Alert threshold |
|---|---|---|
| `service.healthy` | gauge | < 100% trong 5p → page |
| `db.query.duration_p95` | histogram | > 1s → warning |
| `llm.call.duration_p95` | histogram | > 15s → warning |
| `llm.call.error_rate` | rate | > 5% trong 10p → page |
| `cache.hit_rate` | rate | < 30% trong 1h → review cache strategy |
| `sanity.fail_rate` | rate | > 10% trong 1h → review schema |
| `guard.injection.count` | counter | > 50/h → potential attack |
| `guard.hallucinate.count` | counter | > 20/h → review LLM prompt |
| `session.timeout_rate` | rate | > 30% → review UX |
| `session.confirmed_rate` | rate | < 50% → review flow |
| `session.escalated_rate` | rate | > 5% → review edge cases |

### Alert channels

| Severity | Channel | Example |
|---|---|---|
| **PAGE** | PagerDuty | Service down, DB unreachable |
| **WARNING** | Slack #alerts | LLM error rate spike, sanity fail spike |
| **INFO** | Log only | Cache miss spike (review only) |

### Logging

```python
# Structured logging
logger.info("session_event", extra={
    "session_id": session_id,
    "event": "STAGE_TRANSITION",
    "from_stage": "ASKING",
    "to_stage": "CONFIRMING",
    "dealer_type": "khoe",
    "turn_count": 14,
})

logger.warning("guard_triggered", extra={
    "session_id": session_id,
    "guard_type": "hallucinate",
    "field": "owner_name",
    "extracted": "Tùng Nguyễn Văn",
    "message": message[:200],
})
```

### Dashboard sections

1. **Realtime health** — service status, error rate now
2. **Today metrics** — sessions today, CONFIRMED today, escalation today
3. **Quality** — sanity fail rate trend, guard trigger trend
4. **LLM cost** — token usage / day, cost / dealer

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `METRICS_BACKEND` | Prometheus | Production |
| `LOG_LEVEL` | INFO | Production |
| `LOG_LEVEL_DEV` | DEBUG | Dev |
| `DASHBOARD_REFRESH_S` | 30 | Auto refresh |
| `ALERT_DEDUP_WINDOW_S` | 300 | Cùng alert trong 5p chỉ ping 1 lần |

### Acceptance test

```
Case: LLM error rate spike đến 10% trong 5p
  → Alert: "WARNING: llm.call.error_rate = 10%, threshold 5%"
  → Page on-call

Case: 60 prompt injection / h
  → Alert: "WARNING: guard.injection.count = 60/h, threshold 50"
  → Notify security channel + review attacker IP

Case: Session CONFIRMED rate drop từ 70% → 30%
  → Alert: "WARNING: session.confirmed_rate = 30%"
  → Review recent deploys, conversation flow
```

✅ **PASS:**
- Alert fire đúng threshold
- Logging structured đủ context để debug
- Dashboard real-time
- Cost tracking per dealer

❌ **FAIL:**
- Service down nhưng không alert (no monitoring)
- Alert spam vì không dedup
- Log không có session_id → impossible debug
- Cost không track → bill shock

### Constraints

- Mọi error/warning PHẢI structured logging
- Mỗi metric có alert threshold rõ
- Dashboard hiển thị business + technical metrics song song

### Pointer implementation

→ `app/monitoring/metrics.py` § Prometheus exporters
→ `app/monitoring/alerts.py` § alert rules
→ `app/logging/structured.py` § structured logger
→ `dashboards/grafana/em_linh_mkt.json` § Grafana dashboard

### Cross-ref

- ⬆ CORE § N (vận hành)
- ⬅ F2C.2 (rate limit metrics)
- ⬅ F2C.4 (timeout metrics)
- ⬅ F2C.5 (cache metrics)
- ⬅ F2B.8 (guard metrics)

---

## F2C.7 — Data files (province, brand, etc.)

**Tham chiếu File 2A:** F2A.8 (Closing — local hook LLM gen), F2A.7 (address blacklist)
**Tham chiếu File 2B:** F2B.5 (brand list), F2B.6 (province list)

### Yêu cầu

Tách data ra file JSON riêng, không hardcode trong code. Cho phép
admin update mà không deploy lại.

**Nguyên tắc bắt buộc — "không khoá case, chỉ khoá luật":**
- Data file CHỈ chứa LUẬT/ENUM hạt nhân (vd 63 tỉnh validation,
  brand whitelist, forbidden vocab security).
- CẤM data file kiểu lookup table mapping "X → Y cụ thể" (vd province →
  đặc sản, keyword → category code) — ép bot phản xạ máy móc.
- Suy luận case-by-case → LLM gen với context (refer F2A.8 § 7.4).

### Data files

| File | Format | Mô tả | Size |
|---|---|---|---|
| `data/province_list.json` | JSON array | 63 tỉnh Việt Nam (LUẬT validation) | ~3 KB |
| `data/brand_list.json` | JSON array | Brand whitelist (LUẬT enum) | ~2 KB |
| `data/stt_corrections.json` | JSON dict | STT wrong → right (LUẬT — đây là phonetic fix pattern, không phải case) | ~3 KB |
| `data/address_blacklist.json` | JSON array | Chính trị/tôn giáo/vùng miền (LUẬT security) | ~1 KB |
| `data/main_category_enum.json` | JSON array | Enum main_category (code + name, KHÔNG keywords) | ~500 B |
| `data/dealer_type_enum.json` | JSON array | Enum dealer_type (code + label) | ~500 B |
| `data/common_words_filter.json` | JSON array | Filter words cho initials gen | ~1 KB |
| `data/forbidden_vocab.json` | JSON array | Vocab cấm dùng với dealer (LUẬT security) | ~2 KB |

> **REMOVED 2026-05-18 (refer SYNC_LOG):**
> `data/province_specialty.json` — vi phạm "không khoá case". Thay
> bằng LLM gen hook địa phương (F2A.8 § 7.4).

### Load pattern

```python
# In-memory load 1 lần khi service start
PROVINCE_LIST = json.load(open("data/province_list.json"))
BRAND_LIST = json.load(open("data/brand_list.json"))
# ...

# File watcher cho hot reload (dev mode) — chỉ với data thực sự cần
# update runtime (vd brand_list update khi có hãng mới ra mắt)
if ENV == "dev":
    watch_file("data/brand_list.json",
               on_change=lambda: reload(BRAND_LIST))
```

### Sample data files

**`data/brand_list.json`**:
```json
[
  "Xingfa", "Schüco", "Reynaers", "Việt Pháp", "PMI",
  "Liming", "Hyundai", "TOSTEM", "Kingsun",
  "Saint-Gobain", "Viglacera", "Đông Á",
  "Inovar", "An Cường",
  "Austdoor", "Đài Loan Door"
]
```

**`data/address_blacklist.json`**:
```json
[
  "bác hồ", "tô lâm", "trọng tổng", "nguyễn xuân phúc",
  "ba đình lăng", "lăng bác",
  "đức phật", "allah", "chúa trời", "thánh tôn",
  "bắc kỳ", "nam kỳ", "trung kỳ"
]
```

### Versioning

```
Mỗi data file có version trong frontmatter (JSON đầu):
{
  "_meta": {
    "version": "1.2.0",
    "updated_at": "2026-05-14",
    "updated_by": "duong"
  },
  "data": [...]  // hoặc cấu trúc tuỳ file
}
```

→ Track version trong SYNC_LOG.md khi update.

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `DATA_DIR` | `data/` | Folder data |
| `HOT_RELOAD_DEV` | True | Dev hot reload data file |
| `HOT_RELOAD_PROD` | False | Prod cần restart |

### Acceptance test

```
Case: Brand list update (vd thêm "EuroAlu")
  → Hot reload (dev) hoặc restart (prod)
  → STT correct + extractor accept brand mới

Case: Data file corrupted JSON
  → Service start fail với error rõ
  → Fallback: dùng version cũ trong git history
```

✅ **PASS:**
- Data tách khỏi code
- Hot reload dev mode hoạt động
- Versioning rõ ràng
- Fallback khi file corrupt

❌ **FAIL:**
- Hardcode 63 tỉnh trong code → muốn sửa phải deploy
- Hot reload data mà cache không invalidate → outdated
- Data file corrupt → service không start, không có log rõ

### Constraints

- Tất cả data list (province, brand, blacklist, ...) trong data/
- Versioning bắt buộc
- Validate JSON khi service start, fail-fast nếu corrupt

### Pointer implementation

→ `app/data/loaders.py` § load + validate
→ `data/*.json` § data files
→ `app/data/version_tracker.py` § version log

### Cross-ref

- ⬆ CORE § F (domain — brand list nguồn)
- ⬅ F2A.7 (address blacklist), F2A.8 (province specialty)
- ⬅ F2B.5 (brand correct), F2B.6 (province parse)
- ➡ F2C.5 (cache invalidation khi data update)

---

## F2C.8 — Admin queue + review workflow

**Tham chiếu CORE:** § N (vận hành)
**Tham chiếu File 1C:** § 13 (escalation queue)
**Tham chiếu File 2A:** F2A.7 (sanity check fail → admin review)

### Yêu cầu

Khi engine không tự xử được → push session vào admin queue. Admin
review thủ công và tự action:
1. Approve profile (sau khi check/sửa)
2. Reject (data invalid)
3. Manual contact dealer (qua kênh khác)

### Queue trigger

| Trigger | Source | Priority | Note |
|---|---|---|---|
| `escalation` (L3) | File 1C § 13 | HIGH | Soft-end + admin review |
| `sanity_check_failed` | F2A.7 | HIGH | Save block |
| `hallucinate` (≥ 2) | F2B.8 G2 | HIGH | Security — LLM bịa data |
| `pii_leak` (≥ 1) | F2B.8 G4 | HIGH | Security — bot share data dealer khác |
| `abusive_language` (L2) | File 1C § 5 | HIGH | Dealer chửi cá nhân |
| `prompt_injection` (≥ 3) | File 1C § 6 | HIGH | Inject attempt lặp |
| `address_blacklist` (L2) | File 1C § 10 | HIGH | Chính trị/tôn giáo — security review |
| `consent_unclear` | F2A.1 (CONFIRMING timeout) | MEDIUM | brandkit_consent null |
| `required_missing` | F2A.5 | MEDIUM | REQUIRED slot SKIP sau 3 total + DEFER |
| `phone_invalid_after_retry` | File 1C § 12 | MEDIUM | Phone sai format 3 lần |
| `brand_not_in_whitelist` | File 1C § 11 | MEDIUM | Brand lạ — admin bổ sung whitelist |
| `multiple_refusal_in_row` | File 1C § 4 | LOW | 3 OPTIONAL refuse — đề xuất rút gọn |
| `voice_quality_poor` (≥ 3) | File 1C § 8 | LOW | STT fail nhiều lần |

**Lưu ý 2 flag KHÔNG trigger queue (chỉ log):**
- `garbage_input` — bot tự handle qua spam guard 4 layers (F2C.2)
- `dealer_too_defensive` — soft-end qua escalation L3 (đã trigger `escalation`)

### Schema bảng `admin_queue`

```sql
CREATE TABLE admin_queue (
    queue_id        TEXT PRIMARY KEY,        -- uuid
    session_id      TEXT NOT NULL,           -- ref sessions
    trigger         TEXT NOT NULL,           -- flag tên (escalation, sanity_check_failed, etc.)
    priority        TEXT NOT NULL,           -- HIGH/MEDIUM/LOW
    status          TEXT DEFAULT 'PENDING',  -- PENDING/IN_REVIEW/APPROVED/REJECTED
    assigned_to     TEXT,                    -- admin user id
    notes           TEXT,                    -- admin notes
    profile_snapshot TEXT,                   -- JSON profile tại thời điểm queue
    created_at      TIMESTAMP,
    resolved_at     TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_queue_status ON admin_queue(status, priority, created_at);
```

### Workflow admin

```
1. New entry → status=PENDING, priority assigned
2. Admin pull queue (filter priority + assignment)
3. Admin click → status=IN_REVIEW (lock)
4. Admin xem profile_snapshot + history
5. Admin action:
   a. Approve → status=APPROVED
                  + update sessions.review_status=APPROVED
                  + dealer_id assigned (xem Scope 4 — admin gen)
                  + notify dealer (Zalo/SMS): "Hồ sơ anh đã duyệt..."
   b. Reject → status=REJECTED + notes lý do
                + update sessions.review_status=REJECTED
                + KHÔNG notify dealer (silent reject)
   c. Manual contact → status=APPROVED (sau khi gọi xong) + notes
                       + dealer_id assigned thủ công
```

### Notification

```
Admin notify channels:
- Slack #em_linh_mkt_queue (real-time)
- Email daily digest (sáng 9h)
- Dashboard counter (always visible)

Dealer notify (sau APPROVE):
- Zalo (nếu có Zalo): "Anh ơi, hồ sơ cửa hàng anh đã duyệt..."
- SMS (nếu chỉ có phone): "Em Linh: hồ sơ anh duyệt rồi..."
- KHÔNG email (chưa thu)
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `QUEUE_SLA_HIGH_H` | 4 | HIGH phải resolve trong 4h |
| `QUEUE_SLA_MED_H` | 24 | MEDIUM trong 24h |
| `QUEUE_SLA_LOW_H` | 72 | LOW trong 72h |
| `MAX_ASSIGN_PER_ADMIN` | 20 | 1 admin cùng lúc ≤ N |
| `AUTO_REASSIGN_AFTER_H` | 12 | Quá N giờ chưa action → reassign |

### Acceptance test

```
Case: Session sanity fail (phone "abc")
  → push admin queue priority HIGH
  → admin pull → IN_REVIEW
  → admin sửa phone thủ công → APPROVED
  → dealer notify Zalo

Case: 10 admin queue HIGH trong 1 giờ
  → SLA tracking
  → Alert nếu > SLA threshold

Case: Admin assign 25 case → vượt max
  → Lock không cho assign thêm cho admin đó
```

✅ **PASS:**
- Queue priority đúng
- SLA tracked
- Admin workflow rõ ràng
- Dealer notify sau APPROVE

❌ **FAIL:**
- HIGH priority bị skip, LOW xử trước
- Admin override KHÔNG audit
- Reject mà notify dealer (gây bối rối)
- Queue overflow > 10000 entries không alert

### Constraints

- Mọi escalation PHẢI vào queue (không silent drop)
- Priority có SLA bắt buộc
- Audit log mọi admin action

### Pointer implementation

→ `app/admin/queue.py` § queue CRUD
→ `app/admin/notifier.py` § Slack + email + Zalo notify
→ `app/admin/dashboard/` § UI admin

### Cross-ref

- ⬆ CORE § N (vận hành)
- ⬅ File 1C § 13 (escalation queue)
- ⬅ F2A.7 (sanity check fail → queue)
- ⬅ F2C.2 (abuse → queue)
- ⬅ F2C.6 (monitoring queue size)

---

## Cross-ref

| Rule File 2C | Cross-ref CORE | Cross-ref File 1A/B/C + 2A/B |
|---|---|---|
| F2C.1 Session storage | § N | F2A.1, F2A.3 |
| F2C.2 Spam guard | § K.5 | File 1C § 5/6, F2B.8 |
| F2C.3 Concurrency | — | F2C.1 |
| F2C.4 Timeout/retry | § K | F2A.1, F2C.6 |
| F2C.5 Cache | — | F2B.3/5/6, F2C.7 |
| F2C.6 Monitoring | § N | All |
| F2C.7 Data files | § F | F2A.7/8, F2B.5/6 |
| F2C.8 Admin queue | § N | File 1C § 13, F2A.7 |
