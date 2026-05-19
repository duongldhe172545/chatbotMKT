# KẾ HOẠCH REFACTOR — CHATBOT EM LINH MKT v8

> **Mục tiêu:** Rewrite cấu trúc folder + schema mapping theo spec mới
> (CORE v3 + 6 file RULE_KICH_BAN), giữ Python/FastAPI/SQLite, drop
> `dealers.db`. Code cũ làm reference (KHÔNG copy nguyên).
>
> **Audience:** dev (Duong + Claude) cần biết phải làm gì, theo thứ tự
> nào, file nào ở đâu, mapping field cũ → mới.
>
> **Cross-ref spec (bump theo SYNC_LOG):**
> - `EM_LINH_MKT_CORE.md` v3.0.5 — nguyên tắc gốc
> - `RULE_KICH_BAN/0_GLOSSARY.md` v1.2 — thuật ngữ chung (đọc TRƯỚC khi sửa file khác)
> - `RULE_KICH_BAN/0_STRATEGY.md` v1.3 — 8 decision lớn D1-D8 + rationale
> - `RULE_KICH_BAN/KICH_BAN_1A_core.md` v0.2.0-draft — 17 slot Q&A
> - `RULE_KICH_BAN/KICH_BAN_1B_tone.md` v0.1.0-draft — 4 nhóm tone
> - `RULE_KICH_BAN/KICH_BAN_1C_edgecase.md` v0.1.2-draft — 12 edge case
> - `RULE_KICH_BAN/LUAT_2A_core.md` v0.2.2-draft — 8 rule core logic
> - `RULE_KICH_BAN/LUAT_2B_llm.md` v0.1.1-draft — 8 rule LLM engineering
> - `RULE_KICH_BAN/LUAT_2C_infra.md` v0.1.2-draft — 8 rule infrastructure

---

## VERSION

**Version:** v1.2
**Cập nhật:** 2026-05-15
**Author:** Duong + Claude

| Ngày | Version | Thay đổi |
|---|---|---|
| 2026-05-14 | v1.0 | Plan đầu — sau khi spec 6 file hoàn thành |
| 2026-05-15 | v1.1 | Model-agnostic: § 0.7 reverse (GIỮ gemini.py), § 0.9 dùng `LLM_FAST`/`LLM_QUALITY` thay Haiku/Sonnet, action 12 + risk row + folder structure cập nhật. Refer D8 trong 0_STRATEGY. |
| 2026-05-15 | v1.2 | Spec consistency: cross-ref `EM_LINH_MKT_CORE.md` bump v3.0.0 → v3.0.1 (đồng bộ với SYNC_LOG). Nội dung kế hoạch không đổi. |
| 2026-05-15 | v1.3 | Spec consistency BATCH 2 (audit lần 2): (a) cross-ref header bump các spec lên version sau batch (CORE v3.0.3, 1C v0.1.2, 2A v0.2.2, 2B v0.1.1, 2C v0.1.2, GLOSSARY v1.2, STRATEGY v1.3), thêm pointer GLOSSARY + STRATEGY trong block; (b) § 2.3 Flag enum mapping thêm column "Nhóm" (Behavior/Abuse/Data quality/LLM guard) để align với 2A F2A.3 + GLOSSARY § 4. Nội dung 4 phase + 24 action items không đổi. |
| 2026-05-15 | v1.4 | Spec consistency BATCH 4: (1) § PHẦN 5 thêm 4 task bootstrap **#0a/#0b/#0c/#0d** trước task #1 — `.env.example`, `requirements.txt` rewrite, `pytest.ini` + `.gitignore`, `.pre-commit-config.yaml` (optional). Lý do: dev cần artifact này TRƯỚC khi start Phase 1 action #4 schema Pydantic. (2) Cross-ref header bump CORE v3.0.5 (sau batch 4). |

---

## MỤC LỤC

- [Executive summary](#executive-summary)
- [PHẦN 0 — Phân tích phản biện](#phần-0--phân-tích-phản-biện)
- [PHẦN 1 — Khảo sát code hiện tại](#phần-1--khảo-sát-code-hiện-tại)
- [PHẦN 2 — Schema mapping (v7 cũ → v8 mới)](#phần-2--schema-mapping)
- [PHẦN 3 — Cấu trúc folder mới](#phần-3--cấu-trúc-folder-mới)
- [PHẦN 4 — 4 phase migration](#phần-4--4-phase-migration)
- [PHẦN 5 — Action items Phase 1](#phần-5--action-items-phase-1-mvp)
- [PHẦN 6 — Risk + mitigation](#phần-6--risk--mitigation)
- [PHẦN 7 — Open questions cần Duong quyết](#phần-7--open-questions)

---

## Executive summary

Chạy 4 phase: **Phase 1 (MVP — 6-8 ngày dev) → Phase 2 (đủ 17 slot + 4
nhóm tone — 8-12 ngày) → Phase 3 (guards + edge case — 5-7 ngày) →
Phase 4 (Redis + monitoring — 5-7 ngày)**. Total ≈ 24-34 ngày dev cho
1 dev full-time, giảm còn 15-20 ngày nếu có Claude code song song.

**Critical path Phase 1** = MVP chạy được:
1. Schema mới (Pydantic + SQL DDL fresh)
2. State machine + 4 stage + smart advance
3. 17 slot definitions, 1 biến thể câu hỏi
4. **3 extractor REQUIRED** (slot 1.1, 1.2, 4.0) — giảm scope từ 6 xuống 3
5. Ack generator tone "Bận" default
6. Sanity check 5-point
7. Card render đủ 5 phần
8. Conversation orchestrator ≤ 300 dòng

**Phase 1 deliberate cuts** (vs plan ban đầu): chỉ làm 3 REQUIRED slot
(không phải 6) → MVP chạy được sớm hơn 3-4 ngày để feedback loop nhanh.

**Branching strategy:** tạo branch `refactor/v8` từ `main`. Code cũ ở
`main` vẫn deploy được (an toàn). Phase 1 xong → merge khi Duong OK.

**Backup strategy:** trước khi xóa code cũ, zip toàn bộ `app/` cũ thành
`_legacy_v7.zip` (gitignore), drop `dealers.db` → archive thành
`_legacy_dealers_v7.db.zip`.

---

## PHẦN 0 — Phân tích phản biện

Em đã đọc kỹ Plan agent + spec 6 file + code cũ. Đây là những điểm em
phản biện so với plan agent ban đầu, và đề xuất adjust:

### 0.1 Plan agent đề xuất 6 REQUIRED Phase 1 — em đề xuất 3

**Plan agent:** Phase 1 làm hết 6 REQUIRED slot (1.1, 1.2, 1.3, 2.1, 2.2, 4.0).

**Em phản biện:**
- Mỗi extractor = 1 tool schema + 1 ack template + validation logic →
  effort 0.5-1 ngày/slot
- 6 slot Phase 1 = 3-6 ngày chỉ riêng extractor → trễ MVP feedback loop
- Slot 1.3 (phone) phức tạp: phải digits-only validate + retry 3 tone +
  province specialty hook
- Slot 2.1 (main_product) phải auto-derive `main_category` (Scope 2) +
  có "đa ngành" handler
- Slot 2.2 (business_model_signal) phải suy `dealer_type` enum

**Đề xuất:** Phase 1 chỉ 3 slot REQUIRED nhỏ nhất:
- **1.1** (owner_name + dealer_name) — text str đơn giản
- **1.2** (address) — text str, chưa cần address parser LLM
- **4.0** (brandkit_consent) — yes/no enum

→ Đủ chạy end-to-end happy case, validate flow, không bị tắc ở chi tiết
phức tạp. Slot 1.3, 2.1, 2.2 đẩy sang đầu Phase 2.

### 0.2 Plan agent giữ `app/playbook/*.md` làm reference — em đề xuất bỏ

**Plan agent:** "playbook/*.md giữ làm reference docs, không load runtime".

**Em phản biện:** File 1B (tone library) + 1C (edge case) đã thay thế
hết nội dung playbook cũ. Giữ playbook gây CONFUSE — dev đọc cả 2 sẽ
không biết theo cái nào.

**Đề xuất:** Move `app/playbook/` toàn bộ sang `_legacy_v7/playbook/`
(gitignore root) hoặc xoá hẳn. SYNC_LOG đã có cross-ref tracking đầy đủ.

### 0.3 Plan agent đề xuất `app/slots/handlers/` — em ủng hộ nhưng giới hạn

**Plan agent:** tạo sub-folder `slots/handlers/` cho 3 slot phức tạp
(1.2 address, 3.3 open question, 4.0 consent).

**Em ủng hộ** vì 3 slot này có chain logic riêng (1.2 → call
address_parser sau extract; 3.3 → multi-signal mining; 4.0 → parse
yes/no + branching closing path).

**Bổ sung:** Slot 1.3 (phone) cũng phức tạp (validate digits + province
specialty hook) → cần handler riêng `slot_1_3_phone.py` ở Phase 2.

### 0.4 Plan agent đề xuất scheduler Phase 4 — em đề xuất lazy timeout Phase 1

**Plan agent:** scheduler timeout worker chỉ ở Phase 4 (cần infra).

**Em phản biện:** F2A.1 nói SESSION_TIMEOUT_S = 1h là rule cốt lõi.
Nếu Phase 1-3 không có timeout → session active forever → DB bloat.

**Đề xuất:** Phase 1 dùng **lazy timeout check**:
- Mỗi khi dealer gửi message mới → check `now - session.updated_at`
- Nếu > 1h → mark TIMEOUT, tạo session mới
- Không cần background scheduler

Phase 4 mới chuyển sang background scheduler (proactive sweep).

### 0.5 Plan agent đề xuất Prometheus + Grafana Phase 4 — em đề xuất downgrade

**Plan agent:** Phase 4 = Prometheus + Grafana + alerts.

**Em phản biện:** Overkill cho dự án pilot. Spec F2C.6 là long-term
target, MVP chưa cần Grafana.

**Đề xuất:** Phase 4 = **structured logging + admin dashboard simple
HTML** (đủ xem realtime). Prometheus + Grafana dời sang Phase 5 nếu cần
scale.

### 0.6 Plan agent map 17 file extractor riêng — em đề xuất pattern khác

**Plan agent:** `app/llm/extractors/slot_*.py` 17 file.

**Em phản biện:** Maintenance hell. Mỗi slot chỉ là 1 dict schema +
1 validator → không đáng 17 file riêng.

**Đề xuất:**
```
app/llm/extractors/
├── __init__.py
├── schemas.py        # SLOT_TOOL_SCHEMAS: dict[slot_id, ToolSchema]
├── validators.py     # validate_phone, validate_address, validate_enum
├── runner.py         # extract_with_tool(slot_id, message)
└── handlers/         # CHỈ slot có chain logic
    ├── slot_1_2.py   # address → address_parser
    ├── slot_2_1.py   # main_product → main_category derive
    ├── slot_3_3.py   # open question multi-signal
    └── slot_4_0.py   # consent yes/no
```

→ 3-4 file thay vì 17. Đơn giản hơn nhiều.

### 0.7 LLM vendor — em phản biện plan agent: GIỮ gemini.py, model-agnostic

**Plan agent (cũ):** "Bỏ `app/llm/gemini.py` vì Backend Scoring tách riêng."

**Em phản biện:** Plan agent nhầm 2 chuyện riêng:

1. **Backend Scoring** (chấm C1-C9) tách project riêng → đúng. Chatbot
   không gọi Scoring inline. Chuyện này KHÔNG liên quan vendor LLM của
   chatbot.
2. **Vendor LLM của chatbot** (cho intent/extract/ack/...) — chatbot vẫn
   cần gọi LLM. Hiện tại pilot quyết định dùng **Gemini API** cho rẻ →
   `app/llm/gemini.py` GIỮ làm adapter.

**Quyết định:** spec **model-agnostic** (refer **D8** trong
`RULE_KICH_BAN/0_STRATEGY.md`):

- `app/llm/base.py` — `LLMProvider` interface (giữ)
- `app/llm/claude.py` — Anthropic adapter (giữ — fallback nếu Gemini fail)
- `app/llm/gemini.py` — Google adapter (giữ — primary pilot)
- `app/llm/client.py` — route theo tier: `LLM_FAST` (intent/extract) vs
  `LLM_QUALITY` (ack Khoe/Lo, slogan, defensive). Mapping cụ thể trong
  config:
  - `LLM_FAST=gemini-2.5-flash` (pilot) hoặc `claude-haiku-4-5` (fallback)
  - `LLM_QUALITY=gemini-2.5-pro` (pilot) hoặc `claude-sonnet-4-6` (fallback)
- Không hardcode tên model trong module business — chỉ trong config.

### 0.8 Frontend chat.js — em đề xuất scope cụ thể (không "đổi vài label")

**Plan agent:** "static/chat.js đổi tên field render card".

**Em phản biện:** Card spec mới 5 phần với 22 field — khác hẳn card cũ
3 phần với 11 field v6. Frontend phải:

- **Drop field cũ** không còn trong schema: `customer_base_estimate`,
  `pain_points` (array), `main_pain_point`, `dl0_priority`,
  `recommended_group`
- **Đổi label** sang tiếng Việt thuần: "Brandkit" → "bộ thương hiệu",
  "Namecard" → "danh thiếp"
- **Thêm field mới**: `warranty_responsibility_signal`,
  `local_dominance_signal`, `motivation_signal`, etc.
- **Bỏ hết C-code** (nếu có hiển thị): C1/C2/.../Tier/Score
- **Card 5 phần**: Danh thiếp / Công việc + Kênh / Khách cũ + Vướng /
  Bộ thương hiệu / Trong 3 ngày tới

→ Effort frontend = M (Phase 2-3, không phải S).

### 0.9 LLM client routing — em chi tiết hơn plan agent (model-agnostic)

**Plan agent:** "Haiku cho intent/STT/address/auto-derive, Sonnet cho ack".

**Em chi tiết — dùng tier abstraction (refer D8):**

| Task | Tier | Reason |
|---|---|---|
| Intent classify Layer 2 (F2B.3) | `LLM_FAST` | Cheap, deterministic temp=0 |
| Extractor (F2B.2) | `LLM_FAST` | Strict tool schema, temp=0.1 |
| STT brand correct (F2B.5) | `LLM_FAST` | Simple fuzzy match |
| Address parser Layer 2 (F2B.6) | `LLM_FAST` | Whitelist 63 tỉnh |
| Auto-derive brand_short/initials (F2B.7) | `LLM_FAST` | Pattern thuần, không cần sáng tạo |
| Slogan options (F2B.7) | `LLM_QUALITY` | Cần sáng tạo, 5 phương án đa dạng |
| Ack generator (F2B.4) — Khoe/Lo | `LLM_QUALITY` | Insight cụ thể + cam kết bảo mật |
| Ack generator — Bận/Lửa Lò | `LLM_FAST` | Ngắn, đơn giản |
| Defensive/tâm sự handler | `LLM_QUALITY` | Cần empathy + judgement |

**Vendor mapping hiện tại (pilot):**

- `LLM_FAST` → `gemini-2.5-flash` (rẻ ~$0.075/M input token)
- `LLM_QUALITY` → `gemini-2.5-pro`

→ Routing trong `app/llm/client.py`, **không hardcode model name** trong
module business. Đổi vendor chỉ sửa config.

### 0.10 Test strategy — Plan agent chưa đầy đủ

**Plan agent:** mention `tests/test_*.py` cho acceptance test.

**Em đề xuất test pyramid rõ:**

```
tests/
├── unit/                          # Test pure function, no IO
│   ├── test_validators.py         # phone/address/enum validators
│   ├── test_slot_definitions.py   # SLOT_PRIORITY_ORDER, REQUIRED_SLOTS
│   ├── test_intent_markers.py     # Layer 1 regex
│   ├── test_dealer_type_score.py  # F2A.6 score algorithm
│   └── test_sanity_5_point.py     # F2A.7 each check
├── integration/                   # Test với mock LLM + in-memory DB
│   ├── test_state_machine.py      # F2A.4 ADVANCE/RETRY/SKIP/PAUSE
│   ├── test_extractor_runner.py   # F2B.2 tool call → validate → save
│   ├── test_guard_pipeline.py     # F2B.8 4 guard chain
│   └── test_session_lifecycle.py  # F2A.1 stage transitions
└── e2e/                           # Full flow với real LLM (chậm, ít)
    ├── test_phase1_happy.py       # 3 REQUIRED → CONFIRMED → DONE
    └── test_phase2_full_17_slot.py
```

**Phase 1 target test coverage**: 70%+ on `app/core/` + `app/slots/`
+ `app/models/`. LLM module mock trong unit test.

### 0.11 Backup + branching strategy

**Plan agent:** chưa nói.

**Em đề xuất:**

1. **Tạo branch refactor**: `git checkout -b refactor/v8` từ main
2. **Zip code cũ trước khi xóa**: `_legacy_v7.zip` (gitignore)
3. **Export dealers.db cũ ra JSON**: `tools/export_legacy_db.py` →
   `data/_legacy_dealers_export.json` (cho admin xem nếu cần)
4. **Drop dealers.db**: sau khi export
5. **Tag main**: `git tag v7-last-stable` trước refactor
6. **Phase 1 xong + Duong OK → merge refactor/v8 → main**

### 0.12 Cấu trúc folder em điều chỉnh nhẹ so với Plan agent

**Plan agent đề xuất 13 sub-folder trong `app/`.** Một số em gộp:

- `app/concurrency/` (chỉ 2 file) → gộp vào `app/cache/` (vì cùng Redis backend)
- `app/admin/` (chỉ 2 file) → gộp vào `app/api/admin/` (cùng theme)
- `app/data/` (loaders + version) → giữ riêng (clear separation)

**Folder layout em đề xuất** (xem PHẦN 3 chi tiết).

---

## PHẦN 1 — Khảo sát code hiện tại

### 1.1 Thống kê

```
app/                  — 35 .py file, ~5500 dòng code
├── api/              — 4 file (chat.py, admin.py, auth.py, labels_route.py)
├── core/             — 18 file (conversation 1354 dòng, replier, extractor, prompts 586, v7_turns, intent_detect, ...)
├── llm/              — 4 file (base, claude, gemini, call_logger)
├── models/           — 1 file (schema.py — 22 v7 field + 11 v6 legacy)
├── storage/          — 2 file (base, sqlite_store)
└── playbook/         — 9 .md file (4 active + 5 _legacy)

static/               — 6 file (HTML/CSS/JS)
data/                 — dealers.db (sẽ drop)
tools/                — ngrok.exe (giữ)
```

### 1.2 3 nhóm module sau refactor

#### A — Tái sử dụng (chỉ adapt schema/rename) — 17 file

| File cũ | Action | Map sang |
|---|---|---|
| `app/main.py` | Adapt: wire data loaders + DI | `app/main.py` (giữ) |
| `app/config.py` | Mở rộng thresholds | `app/config.py` (giữ) |
| `app/middleware.py` (RequestID) | Giữ nguyên | `app/middleware.py` |
| `app/logging_setup.py` | Mở rộng structured JSON | `app/logging_setup.py` |
| `app/labels.py` (CATEGORY_LABEL) | Move sang data file | `data/main_category_enum.json` |
| `app/api/chat.py` | Adapt: idempotency → Redis Phase 4 | `app/api/chat.py` |
| `app/api/admin.py` | Mở rộng: queue endpoints | `app/api/admin.py` + `app/api/admin_queue.py` |
| `app/api/auth.py` (HTTP Basic) | Giữ nguyên | `app/api/auth.py` |
| `app/api/labels_route.py` | Giữ — đọc từ data file | `app/api/labels_route.py` |
| `app/llm/base.py` (LLMProvider interface) | Giữ | `app/llm/base.py` |
| `app/llm/claude.py` (Anthropic adapter) | Tách retry → utils. Giữ làm fallback vendor | `app/llm/claude.py` |
| `app/llm/gemini.py` (Google adapter) | Tách retry → utils. Pilot primary | `app/llm/gemini.py` |
| `app/llm/call_logger.py` (cost/timing log) | Giữ — feed monitoring | `app/llm/call_logger.py` |
| `app/storage/base.py` (StorageAdapter abstract) | Giữ | `app/storage/base.py` |
| `app/core/intent_detect.py` (regex markers) | Refactor 7 intent enum | `app/core/regex_markers.py` |
| `app/core/address_form.py` (anh/chị detect) | Giữ — sub-module helper | `app/core/address_form.py` |
| `app/core/edit_parser.py` | Giữ nguyên | `app/core/edit_parser.py` |
| `app/core/province_specialty.py` | Convert → JSON data | `data/province_specialty.json` |

#### B — Phải viết lại hoàn toàn (paradigm đổi) — 11 file

| File cũ | Vì sao đổi | Map sang spec |
|---|---|---|
| `app/core/conversation.py` (1354 dòng) | Monolithic, trộn 6 concern | Tách: `stages.py`, `state_machine.py`, `session.py`, `conversation.py` (orchestrator ≤300 dòng) — F2A.1, F2A.4 |
| `app/core/v7_turns.py` (16 turn) | Spec mới 17 slot, slot 3.5 NEW, hardcoded vocab "BRANDKIT"/"Namecard" cần đổi | `app/slots/definitions.py`, `app/slots/templates.py` — F2A.5 |
| `app/core/extractor.py` | 1 prompt extract all field → spec mới 1 tool/slot | `app/llm/extractors/*` — F2B.2 |
| `app/core/replier.py` (Goal model) | Abstraction cũ, trộn defensive + ack | `app/llm/ack_generator.py` + `defensive_handler.py` — F2B.4 |
| `app/core/prompts.py` (586 dòng) | Spec mới sys prompt ≤ 600 token | `app/llm/system_prompt.py` (≤ 200 dòng) — F2B.1 |
| `app/core/chat_replier.py` (wrapper LLM cũ) | Bỏ — không còn dùng | (DROP) |
| `app/core/opener_enforcer.py` (A/B/C/D opener) | Spec mới detect 4 dealer type khác | `app/core/dealer_type.py` — F2A.6 |
| `app/core/reply_guards.py` (ad-hoc guards) | Refactor thành package | `app/guards/*` — F2B.8 |
| `app/models/schema.py` (33 cột mix v6+v7) | Spec mới 4 scope rõ — drop v6 legacy + Scope 4 | `app/models/schema.py` (rewrite — chỉ Scope 1+2+3) |
| `app/storage/sqlite_store.py` (33 cột) | Schema mới fresh, 10 cột sessions thêm | `app/storage/sqlite_store.py` + `migrations/001_init.sql` — F2C.1 |
| `app/core/concurrency.py` (in-memory RLock) | Spec Redis lock TTL | `app/cache/session_lock.py` (in-memory Phase 1, Redis Phase 4) — F2C.3 |

#### C — Module mới (spec mới có, code cũ thiếu) — 17 module

| Spec rule | Module mới cần tạo |
|---|---|
| F2A.6 dealer type detect | `app/core/dealer_type.py` |
| F2A.7 sanity 5-point | `app/core/sanity.py`, `app/core/validators.py` |
| F2A.1 session lifecycle + lazy timeout | `app/core/session.py` |
| F2B.5 STT brand correct | `app/llm/brand_correction.py` (Phase 3) |
| F2B.6 address parser LLM | `app/llm/address_parser.py` |
| F2B.7 auto-derive | `app/llm/auto_derive.py` |
| F2B.8 4 guard | `app/guards/{injection,hallucinate,drift,pii_leak}.py` |
| F2C.2 rate limit + abuse | `app/guards/rate_limit.py`, `abuse_detector.py` |
| F2C.4 fallback safe ack | `app/llm/fallback.py` + `app/utils/retry.py` |
| F2C.5 cache | `app/cache/llm_cache.py` + `data_loaders.py` |
| F2C.7 data files | `data/*.json` (9 file) + `app/data/loaders.py` |
| F2C.8 admin queue | `app/api/admin_queue.py` + `app/admin/queue.py` |
| F2A.1 scheduler (Phase 4) | `app/scheduler/timeout_worker.py` |
| F2A.6 dealer type score algo | `app/core/dealer_type_score.py` |
| F2A.4 smart advance | `app/core/state_machine.py` |
| F2A.2 intent Layer 2 | `app/llm/intent_classifier.py` |
| F2A.8 greeting/closing engine | `app/core/greeting.py` + `app/core/closing.py` |

#### D — Module xóa hoàn toàn — 5 file

| File | Lý do |
|---|---|
| `app/core/chat_replier.py` | Wrapper cũ không dùng |
| `app/playbook/` (toàn bộ folder) | Spec 1B/1C thay thế |
| `data/dealers.db` (+ wal/shm) | User chọn drop |
| `dealers.db` ở root (0 byte) | File rỗng leftover |

---

## PHẦN 2 — Schema mapping (v7 cũ → v8 mới)

### 2.1 Profile field mapping

#### A — Field GIỮ (rename hoặc giữ nguyên)

| Field v7 cũ | Field v8 mới | Scope mới | Note |
|---|---|---|---|
| `dealer_name` | `dealer_name` | 1 | giữ |
| `owner_name` | `owner_name` | 1 | giữ |
| `phone_or_zalo` | `phone_or_zalo` | 1 | giữ |
| `address` | `address` | 1 | giữ |
| `category_stack` | `category_stack` | 1 | giữ |
| `main_product` | `main_product` | 1 | REQUIRED mới (cũ Optional) |
| `business_model_signal` | `business_model_signal` | 1 | REQUIRED mới |
| `est_team_size` | `est_team_size` | 1 | giữ |
| `team_stability_signal` | `team_stability_signal` | 1 | giữ |
| `supplier_brands` | `supplier_brands` | 1 | giữ |
| `customer_segment_signal` | `customer_segment_signal` | 1 | giữ |
| `zalo` | `zalo` | 1 | giữ |
| `facebook` | `facebook` | 1 | giữ |
| `primary_contact_channel` | `primary_contact_channel` | 1 | giữ |
| `fb_marketing_status` | `fb_marketing_status` | 1 | giữ |
| `customer_old_percentage` | `customer_old_percentage` | 1 | giữ |
| `customer_storage_method` | `customer_storage_method` | 1 | giữ |
| `customer_pain` | `customer_pain` | 1 | giữ (text dài raw) |
| `usp_signal` | `usp_signal` | 1 | giữ |
| `payment_terms_signal` | `payment_terms_signal` | 1 | giữ |
| `brandkit_consent` | `brandkit_consent` | 1 | giữ — REQUIRED |
| `color_accent` | `color_accent` | 1 | giữ |
| `feng_shui_signal` | `feng_shui_signal` | 1 | giữ |
| `province` | `province` | **2** | đổi scope: auto-derive từ address |
| `district` | `district` | **2** | đổi scope: auto-derive |
| `province_specialty` | `province_specialty` | **2** | lookup table |
| `main_category` | `main_category` | **2** | enum auto-derive từ main_product |
| `dealer_type` | `dealer_type` | **2** | enum: `dai_ly`/`chu_xuong`/`tho_doi`/`nha_thau_nho` |
| `confirmation_status` | `confirmation_status` | **3** | state nội bộ |
| `review_status` | `review_status` | **3** | state nội bộ |
| `flags` | `flags` | **3** | state nội bộ (đổi enum values — xem dưới) |

#### B — Field BỎ (drop hoàn toàn)

| Field v7 cũ | Lý do bỏ |
|---|---|
| `customer_base_estimate` | v6 legacy — không trong spec mới |
| `pain_points` (list[str]) | v6 — thay bằng `customer_pain` (text dài) |
| `main_pain_point` | v6 legacy |
| `dl0_priority` | v6 — không trong spec mới |
| `recommended_group` | v6 — không trong spec mới |
| `product_portfolio_signal` | v7 — redundant với `category_stack` |
| `slogan` (str) | thay bằng `slogan_options` (list 5) |

#### C — Field MỚI (spec mới có, code cũ chưa có)

| Field mới | Scope | Slot fill | Note |
|---|---|---|---|
| `local_dominance_signal` | 1 | slot 1.2 | raw signal C6 — bán kính khách |
| `supplier_negotiation_signal` | 1 | slot 2.4 | raw signal C8 — backup nguồn |
| `community_network_signal` | 1 | slot 2.6 | raw signal C9 — thợ/đối tác giới thiệu |
| `motivation_signal` | 1 | slot 3.3 | raw signal C5 — động lực |
| `warranty_responsibility_signal` | 1 | **slot 3.5 (NEW)** | raw signal C4 — bảo hành ai chịu |
| `brand_name_short` | 2 | LLM auto-derive từ dealer_name | vd "Thanh Tùng" |
| `initials_full` | 2 | regex auto-derive | vd "NKTT" |
| `initial_single` | 2 | LLM auto-derive | vd "T" |
| `contact_name` | 2 | `= owner_name` | default |
| `contact_role` | 2 | `"Chủ cửa hàng"` | fix |
| `hotline` | 2 | `= phone_or_zalo` | default |
| `slogan_options` | 2 | LLM gen 5 phương án | list[str] len=5 |

### 2.2 Session state mapping

| v7 cũ | v8 mới | Note |
|---|---|---|
| `v7_turn` | `current_slot` | rename |
| `v7_turn_attempts` | `slot_attempts` | rename |
| `v7_completed_turns` | (DROP) | logic dùng skipped_slots + extract success |
| `skipped_fields` | `skipped_slots` | rename |
| `field_attempts` | (merge với `slot_attempts`) | dedup |
| `skipped_at_filled_count` | (DROP) | spec mới không cho re-ask sau skip |
| `skipped_retried` | (DROP) | dito |
| `last_opener_group` (A/B/C/D) | (DROP) — thay bằng `detected_dealer_type` | spec mới 4 nhóm khác |
| `current_question_idx` | (DROP) | `current_slot` đủ |
| (MỚI) | `detected_dealer_type` | F2A.6: lua_lo/khoe/lo/ban/unknown |
| (MỚI) | `dealer_type_history` | list[(turn, type)] cho re-detect |
| (MỚI) | `turn_count` | int — re-detect turn 3/8/13 |
| (MỚI) | `paused_for` | None/"defensive"/"tam_su" |

### 2.3 Flag enum mapping (15 flag — sync với 2A F2A.3 + GLOSSARY § 4)

| Flag v7 cũ | Flag v8 mới | Nhóm | Note |
|---|---|---|---|
| `prompt_injection` | `prompt_injection` | Abuse | giữ — detect injection pattern |
| `abusive_language` | `abusive_language` | Abuse | giữ — dealer chửi cá nhân |
| `garbage_input` | `garbage_input` | Abuse | giữ — gibberish lặp |
| (MỚI) | `dealer_declined` | Behavior | OPTIONAL slot skip ("không biết") |
| (MỚI) | `required_missing` | Behavior | REQUIRED skip sau 3 retry |
| (MỚI) | `consent_unclear` | Behavior | brandkit_consent null sau retry |
| (MỚI) | `multiple_refusal_in_row` | Behavior | 3 OPTIONAL refuse liên tiếp → rút gọn mode |
| (MỚI) | `dealer_too_defensive` | Abuse | defensive ≥3 lần |
| (MỚI) | `address_blacklist` | Abuse | chính trị / tôn giáo / vùng miền |
| (MỚI) | `sanity_check_failed` | Data quality | F2A.7 5-point check fail |
| (MỚI) | `phone_invalid_after_retry` | Data quality | phone sai format 3 lần |
| (MỚI) | `voice_quality_poor` | Data quality | STT empty/noise lặp |
| (MỚI) | `brand_not_in_whitelist` | Data quality | brand lạ → admin review |
| (MỚI) | `hallucinate` | LLM guard | LLM bịa data dealer chưa cho |
| (MỚI) | `pii_leak` | LLM guard | bot share data dealer khác |

**Tổng: 4 Behavior + 5 Abuse + 4 Data quality + 2 LLM guard = 15 flag.**

### 2.4 DB schema mới (F2C.1)

```sql
-- migrations/001_init.sql

CREATE TABLE IF NOT EXISTS sessions (
    session_id              TEXT PRIMARY KEY,
    stage                   TEXT NOT NULL,                -- GREETING/ASKING/CONFIRMING/DONE
    current_slot            TEXT,                          -- vd "2.3"
    slot_attempts           TEXT NOT NULL DEFAULT '{}',    -- JSON dict
    skipped_slots           TEXT NOT NULL DEFAULT '[]',    -- JSON list
    flags                   TEXT NOT NULL DEFAULT '[]',    -- JSON list (Scope 3)
    detected_dealer_type    TEXT,                          -- enum 5 value
    dealer_type_history     TEXT NOT NULL DEFAULT '[]',    -- JSON list
    confirmation_status     TEXT NOT NULL DEFAULT 'PENDING',
    review_status           TEXT NOT NULL DEFAULT 'RAW',
    history                 TEXT NOT NULL DEFAULT '[]',    -- JSON list message
    turn_count              INTEGER NOT NULL DEFAULT 0,
    paused_for              TEXT,                          -- None/"defensive"/"tam_su"
    address_form            TEXT NOT NULL DEFAULT 'anh',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    closed_at               TEXT,                          -- null nếu active
    channel                 TEXT DEFAULT 'web',
    ip_address              TEXT,
    user_agent              TEXT
);

CREATE INDEX idx_session_stage ON sessions(stage);
CREATE INDEX idx_session_updated ON sessions(updated_at);
CREATE INDEX idx_session_ip ON sessions(ip_address);

CREATE TABLE IF NOT EXISTS dealer_profile_raw (
    session_id          TEXT PRIMARY KEY,
    -- Scope 1 — Identity
    dealer_name         TEXT,
    owner_name          TEXT,
    address             TEXT,
    phone_or_zalo       TEXT,
    -- Scope 1 — Business
    category_stack      TEXT NOT NULL DEFAULT '[]',
    main_product        TEXT,
    business_model_signal TEXT,
    est_team_size       INTEGER,
    team_stability_signal TEXT,
    supplier_brands     TEXT NOT NULL DEFAULT '[]',
    customer_segment_signal TEXT,
    -- Scope 1 — Channels
    zalo                TEXT,
    facebook            TEXT,
    primary_contact_channel TEXT,
    fb_marketing_status TEXT,
    -- Scope 1 — Customer Gold Mine
    customer_old_percentage TEXT,
    customer_storage_method TEXT,
    customer_pain       TEXT,
    payment_terms_signal TEXT,
    warranty_responsibility_signal TEXT,  -- NEW slot 3.5
    -- Scope 1 — RAW SIGNALS (mining)
    local_dominance_signal TEXT,           -- NEW slot 1.2
    supplier_negotiation_signal TEXT,      -- NEW slot 2.4
    community_network_signal TEXT,         -- NEW slot 2.6
    motivation_signal TEXT,                -- NEW slot 3.3
    usp_signal          TEXT,
    -- Scope 1 — Brandkit
    brandkit_consent    TEXT,
    color_accent        TEXT,
    feng_shui_signal    TEXT,
    -- Scope 2 — Auto-derived
    province            TEXT,
    district            TEXT,
    province_specialty  TEXT,
    main_category       TEXT,
    dealer_type         TEXT,
    brand_name_short    TEXT,
    initials_full       TEXT,
    initial_single      TEXT,
    contact_name        TEXT,
    contact_role        TEXT NOT NULL DEFAULT 'Chủ cửa hàng',
    hotline             TEXT,
    slogan_options      TEXT NOT NULL DEFAULT '[]',
    -- Metadata
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX idx_dealer_phone ON dealer_profile_raw(phone_or_zalo);

-- Admin queue (F2C.8) — Phase 3
CREATE TABLE IF NOT EXISTS admin_queue (
    queue_id            TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    trigger             TEXT NOT NULL,
    priority            TEXT NOT NULL,         -- HIGH/MEDIUM/LOW
    status              TEXT NOT NULL DEFAULT 'PENDING',
    assigned_to         TEXT,
    notes               TEXT,
    profile_snapshot    TEXT,                  -- JSON
    created_at          TEXT NOT NULL,
    resolved_at         TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_queue_status ON admin_queue(status, priority, created_at);
```

**Lưu ý:** không có cột Scope 4 (c_score, tier, dealer_id, batch...) —
backend Scoring là service riêng.

---

## PHẦN 3 — Cấu trúc folder mới

```
d:\Chatbot_dealer/
├── _legacy_v7.zip                       # ★ backup code cũ (gitignore)
├── _legacy_dealers_export.json          # ★ backup DB cũ (gitignore)
│
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI entry (adapt từ cũ)
│   ├── config.py                        # ENV, thresholds, model routing
│   ├── middleware.py                    # RequestID (giữ)
│   ├── logging_setup.py                 # structured JSON
│   │
│   ├── api/                             # HTTP routes
│   │   ├── chat.py                      # POST /api/chat
│   │   ├── admin.py                     # /admin/* base
│   │   ├── admin_queue.py               # ★ F2C.8 — /admin/queue
│   │   ├── auth.py                      # HTTP Basic
│   │   └── labels_route.py
│   │
│   ├── core/                            # Business logic
│   │   ├── conversation.py              # ★ orchestrator ≤ 300 dòng
│   │   ├── session.py                   # ★ Session dataclass + lazy timeout
│   │   ├── stages.py                    # F2A.1 — Stage enum + transitions
│   │   ├── state_machine.py             # F2A.4 — smart advance
│   │   ├── intent.py                    # F2A.2 Layer 1 dispatcher
│   │   ├── regex_markers.py             # F2A.2 — 7 intent marker list
│   │   ├── dealer_type.py               # F2A.6 — detect 4 nhóm
│   │   ├── sanity.py                    # F2A.7 — 5-point check
│   │   ├── validators.py                # phone/address/enum validators
│   │   ├── address_form.py              # anh/chị detect (giữ)
│   │   ├── address_blacklist.py         # F2A.7 — blacklist check
│   │   ├── greeting.py                  # F2A.8 — render greeting
│   │   ├── closing.py                   # F2A.8 — render closing
│   │   ├── card_renderer.py             # render confirmation card
│   │   └── edit_parser.py               # parse edit cmd (giữ)
│   │
│   ├── slots/                           # 17 slot config + per-slot logic
│   │   ├── definitions.py               # F2A.5 — SLOT_PRIORITY_ORDER, REQUIRED list
│   │   ├── templates.py                 # 17 slot × 3 biến thể câu hỏi
│   │   ├── retry_tones.py               # F2A.5 — 3 tone retry REQUIRED
│   │   └── handlers/                    # CHỈ slot có chain logic
│   │       ├── slot_1_2.py              # address → address_parser
│   │       ├── slot_1_3.py              # phone validate + specialty hook
│   │       ├── slot_2_1.py              # main_product → main_category derive
│   │       ├── slot_3_3.py              # open question multi-signal
│   │       └── slot_4_0.py              # consent yes/no branching
│   │
│   ├── llm/                             # LLM clients + per-task
│   │   ├── client.py                    # ★ unified routing LLM_FAST/LLM_QUALITY
│   │   ├── base.py                      # LLMProvider abstract (giữ)
│   │   ├── claude.py                    # Anthropic adapter (fallback vendor)
│   │   ├── gemini.py                    # Google adapter (pilot primary)
│   │   ├── call_logger.py               # cost/timing log (giữ)
│   │   ├── system_prompt.py             # F2B.1 — build ≤ 600 token
│   │   ├── extractors/                  # F2B.2
│   │   │   ├── __init__.py              # EXTRACTORS_PER_SLOT
│   │   │   ├── schemas.py               # 17 tool schema dict
│   │   │   ├── runner.py                # extract_with_tool(slot_id, msg)
│   │   │   └── validators.py            # validate sau extract
│   │   ├── intent_classifier.py         # F2B.3 — Layer 2 LLM
│   │   ├── ack_generator.py             # F2B.4 — per dealer_type
│   │   ├── defensive_handler.py         # trả lời defensive
│   │   ├── tam_su_handler.py            # engage tâm sự
│   │   ├── brand_correction.py          # F2B.5 — STT brand
│   │   ├── address_parser.py            # F2B.6 — province/district
│   │   ├── auto_derive.py               # F2B.7 — brand_short/initials/slogan
│   │   ├── fallback.py                  # F2C.4 — safe ack
│   │   └── templates/                   # prompt MD files
│   │       ├── sys_prompt.md
│   │       └── ack_prompts/{lua_lo,khoe,lo,ban}.md
│   │
│   ├── guards/                          # F2B.8 + F2C.2
│   │   ├── injection.py                 # prompt injection regex
│   │   ├── hallucinate.py               # value_appears_in_message
│   │   ├── drift.py                     # forbidden vocab + auto-rewrite
│   │   ├── pii_leak.py                  # cross-session PII
│   │   ├── rate_limit.py                # F2C.2 IP/msg rate
│   │   └── abuse_detector.py            # F2C.2 score aggregation
│   │
│   ├── cache/                           # F2C.3 + F2C.5
│   │   ├── client.py                    # in-memory (P1) / Redis (P4) interface
│   │   ├── session_lock.py              # F2C.3 lock + queue
│   │   ├── llm_cache.py                 # LLM result cache
│   │   └── data_loaders.py              # JSON data file in-memory load
│   │
│   ├── scheduler/                       # F2A.1, F2C.1 (Phase 4)
│   │   ├── timeout_worker.py            # session 1h sweep
│   │   └── confirming_nudge.py          # 3p nudge
│   │
│   ├── admin/                           # F2C.8
│   │   └── queue.py                     # queue trigger logic
│   │
│   ├── storage/                         # DB layer
│   │   ├── base.py                      # StorageAdapter (giữ)
│   │   ├── sqlite_store.py              # rewrite schema F2C.1
│   │   └── migrations/
│   │       └── 001_init.sql             # fresh schema
│   │
│   ├── models/                          # Pydantic
│   │   ├── schema.py                    # rewrite F2A.3 (Scope 1+2+3)
│   │   ├── intents.py                   # Intent enum
│   │   ├── actions.py                   # ADVANCE/RETRY/SKIP/PAUSE
│   │   └── api.py                       # ChatRequest/Response
│   │
│   └── utils/
│       ├── retry.py                     # F2C.4 call_with_retry
│       ├── normalize.py                 # text normalize cho Layer 1
│       └── hash_utils.py                # cache key
│
├── data/                                # F2C.7 JSON data
│   ├── _legacy_dealers_export.json      # ★ backup DB cũ
│   ├── province_list.json               # 63 tỉnh
│   ├── province_specialty.json          # 50 tỉnh có specialty
│   ├── brand_list.json                  # whitelist brand
│   ├── stt_corrections.json
│   ├── address_blacklist.json
│   ├── main_category_enum.json
│   ├── dealer_type_enum.json
│   ├── common_words_filter.json
│   └── forbidden_vocab.json
│
├── chatbot.db                           # ★ DB mới (auto-create)
├── static/                              # Frontend (adapt)
│   ├── index.html
│   ├── chat.js                          # ★ update field card
│   ├── admin.html
│   ├── admin.js                         # ★ thêm Queue tab Phase 3
│   ├── admin.css
│   └── style.css
│
├── tests/                               # Test pyramid
│   ├── unit/
│   │   ├── test_validators.py
│   │   ├── test_slot_definitions.py
│   │   ├── test_intent_markers.py
│   │   ├── test_dealer_type_score.py
│   │   └── test_sanity_5_point.py
│   ├── integration/
│   │   ├── test_state_machine.py
│   │   ├── test_extractor_runner.py
│   │   ├── test_guard_pipeline.py
│   │   └── test_session_lifecycle.py
│   └── e2e/
│       ├── test_phase1_happy.py
│       └── test_phase2_full_17_slot.py
│
├── tools/
│   ├── ngrok.exe                        # giữ
│   ├── export_legacy_db.py              # ★ export dealers.db cũ
│   └── seed_data.py                     # ★ load JSON data ban đầu
│
├── EM_LINH_MKT_CORE.md                  # spec (giữ root)
├── RULE_KICH_BAN/                       # spec (giữ root)
├── SYNC_LOG.md                          # version log
├── KE_HOACH_REFACTOR.md                 # ★ file này
├── requirements.txt                     # update — thêm prometheus_client (P4), redis (P4)
├── Procfile / railway.json              # giữ deploy Railway
├── README.md
├── SECURITY.md
└── .gitignore                           # update — thêm _legacy_v7.zip
```

**Mapping rule spec → file** (compact):

| Spec rule | File chính |
|---|---|
| F2A.1 Stages | `app/core/stages.py` + `app/core/session.py` |
| F2A.2 Intent | `app/core/intent.py` + `regex_markers.py` + `app/llm/intent_classifier.py` |
| F2A.3 Schema 4 scope | `app/models/schema.py` + `app/storage/sqlite_store.py` |
| F2A.4 Smart advance | `app/core/state_machine.py` |
| F2A.5 Slot priority + retry | `app/slots/definitions.py` + `retry_tones.py` |
| F2A.6 Dealer type | `app/core/dealer_type.py` |
| F2A.7 Sanity | `app/core/sanity.py` + `validators.py` + `address_blacklist.py` |
| F2A.8 Greeting/Closing | `app/core/greeting.py` + `closing.py` + `data/province_specialty.json` |
| F2B.1 System prompt | `app/llm/system_prompt.py` + `templates/sys_prompt.md` |
| F2B.2 Extractor | `app/llm/extractors/*` |
| F2B.3 Intent LLM | `app/llm/intent_classifier.py` |
| F2B.4 Ack gen | `app/llm/ack_generator.py` |
| F2B.5 STT brand | `app/llm/brand_correction.py` |
| F2B.6 Address parser | `app/llm/address_parser.py` |
| F2B.7 Auto-derive | `app/llm/auto_derive.py` |
| F2B.8 Guards | `app/guards/{injection,hallucinate,drift,pii_leak}.py` |
| F2C.1 Session storage | `app/storage/sqlite_store.py` + `migrations/001_init.sql` |
| F2C.2 Spam guard | `app/guards/rate_limit.py` + `abuse_detector.py` |
| F2C.3 Concurrency | `app/cache/session_lock.py` |
| F2C.4 Timeout/retry | `app/utils/retry.py` + `app/llm/fallback.py` |
| F2C.5 Cache | `app/cache/*` |
| F2C.6 Monitoring | `app/logging_setup.py` (structured log) |
| F2C.7 Data files | `data/*.json` + `app/cache/data_loaders.py` |
| F2C.8 Admin queue | `app/admin/queue.py` + `app/api/admin_queue.py` |

---

## PHẦN 4 — 4 phase migration

### PHASE 1 — MVP (6-8 ngày dev)

**Mục tiêu:** dealer chat web → greeting → 3 REQUIRED slot (1.1, 1.2,
4.0) → card → CONFIRMED → DONE. End-to-end happy case chạy được.

**Scope IN:**
- `app/models/schema.py` (Scope 1+2+3, 22+12+13 field — DROP Scope 4)
- `app/storage/sqlite_store.py` + `migrations/001_init.sql`
- `app/core/stages.py` + `state_machine.py` (4 stage, simplified)
- `app/core/session.py` (Session class + lazy timeout)
- `app/slots/definitions.py` (17 slot, REQUIRED 6 list)
- `app/slots/templates.py` (1 biến thể câu hỏi / slot — đủ MVP)
- `app/core/intent.py` Layer 1 regex (7 intent enum)
- `app/llm/system_prompt.py` (≤ 600 token)
- `app/llm/extractors/` cho 3 slot (1.1, 1.2, 4.0)
- `app/llm/ack_generator.py` (tone "ban" default, `LLM_FAST`)
- `app/llm/fallback.py` (safe ack)
- `app/core/sanity.py` 5-point check
- `app/core/validators.py` (phone, address)
- `app/core/greeting.py` (1 biến thể), `closing.py` (1 biến thể)
- `app/core/card_renderer.py` (5 phần)
- `app/core/conversation.py` orchestrator ≤ 300 dòng
- `app/cache/data_loaders.py` + 3 file data (province_list,
  province_specialty, main_category_enum)
- `app/utils/retry.py` (call_with_retry generic)
- Frontend `static/chat.js` adapt field card mới
- Test e2e `test_phase1_happy.py`

**Scope OUT (đẩy Phase 2-3):**
- Dealer type detection (default "ban" tone cho mọi dealer)
- 4 dealer type ack templates (chỉ "ban" Phase 1)
- 17 slot full extractor (chỉ 3)
- 3 biến thể câu hỏi/slot (chỉ 1)
- Address parser LLM Layer 2 (chỉ regex)
- Auto-derive slogan/initials/brand_short
- STT brand correction
- 4 guard (chỉ basic injection regex)
- Rate limit + abuse
- Admin queue
- Redis (in-memory)
- Monitoring/Prometheus
- Scheduler (lazy timeout)

**KPI Phase 1:**
- 1 dealer chạy đủ end-to-end happy case
- 3 REQUIRED slot extract HIGH
- Sanity check pass
- Card render đúng 5 phần
- Profile save DB đúng schema
- KHÔNG có vocab cấm trong bot output

**Deliverable:** branch `refactor/v8`, working demo URL.

---

### PHASE 2 — Đủ 17 slot + 4 dealer type (8-12 ngày)

**Mục tiêu:** bot hoạt động đầy đủ, detect dealer type, ack đa dạng.

**Scope IN:**
- 14 extractor còn lại (slot 1.3 đến 4.2)
- `app/llm/extractors/handlers/` cho slot phức tạp (1.3, 2.1, 3.3, 4.0)
- `app/core/dealer_type.py` F2A.6 (detect turn 3/8/13)
- `app/core/dealer_type_score.py` (score algorithm)
- `app/llm/ack_generator.py` mở rộng 4 type (lua_lo/khoe/lo/ban)
- `app/llm/templates/ack_prompts/{lua_lo,khoe,lo,ban}.md`
- `app/llm/intent_classifier.py` Layer 2 (LLM fallback)
- `app/llm/address_parser.py` (Layer 1 regex + Layer 2 LLM, 63 tỉnh)
- `app/llm/auto_derive.py` (brand_short, initials, slogan)
- `app/slots/templates.py` mở rộng 3 biến thể / slot
- `app/slots/retry_tones.py` (3 tone retry REQUIRED)
- `app/llm/defensive_handler.py` + `tam_su_handler.py`
- `app/core/greeting.py` mở rộng 3 biến thể
- `app/core/closing.py` mở rộng 3 biến thể + hook đặc sản
- Frontend admin.html basic profile view
- Test integration đủ 17 slot
- Data files mới: `brand_list.json`, `common_words_filter.json`,
  `stt_corrections.json`, `dealer_type_enum.json`

**KPI Phase 2:**
- 17 slot extract HIGH ≥ 80%
- Dealer type detect đúng ≥ 80% với manual test 20 dealer
- Ack đa dạng (không paste cứng — 3 lần ack cùng dealer type ≠ y hệt)
- Slot REQUIRED retry max 3 lần đúng
- Province specialty hook đúng 50/63 tỉnh

---

### PHASE 3 — Guards + Edge case + Admin queue (10 round, COMPLETE 2026-05-19)

**Mục tiêu:** chống abuse/injection, xử 12 edge case File 1C đầy đủ,
admin review queue 13 trigger. **Quality first — KHÔNG defer case nào.**

**Scope DONE 10 round:**

| R | Module | Status |
|---|---|---|
| R1 | data/address_blacklist.json + data/forbidden_vocab.json + app/core/address_blacklist.py | ✅ |
| R2 | app/guards/injection.py + hallucinate.py + drift.py (Layer 1 regex) | ✅ |
| R3 | app/admin/queue.py — 13 trigger + UPSERT fix bug critical | ✅ |
| R4 | Defensive 3 cấp + Refusal lặp + Escalation L3 + Phone retry exhausted | ✅ |
| R5 | 3-scenario integration test thật (clean / defensive L3 / mix abuse) | ✅ |
| R6 | Garbage input + Brand unknown + Address blacklist L1 detection | ✅ |
| R7 | Abuse cá nhân 3 cấp + Address blacklist 3 cấp escalation | ✅ |
| R8 | Tâm sự kéo dài 5 cấp (L1/L2/L3) — refer 1C § 3 | ✅ |
| R9 | Wire address_form auto-detect anh/chị + edit_parser CONFIRMING + cleanup file rác | ✅ |
| R10 | Test end-to-end 5 scenario thật + commit Phase 3 close | ⏳ |

**12 edge case File 1C status:**
- ✅ Defensive lặp (§ 2) — R4
- ✅ Tâm sự kéo dài (§ 3) — R8
- ✅ Refusal lặp (§ 4) — R4
- ✅ Abuse cá nhân (§ 5) — R7
- ✅ Troll/inject (§ 6) — R2 Layer 1 (Layer 2 LLM defer Phase 4)
- ✅ Garbage input (§ 7) — R6
- ⏳ Voice fail (§ 8) — phụ thuộc STT MVP, defer Phase 4 (cùng voice channel)
- ⏳ Im lặng kéo dài (§ 9) — phụ thuộc background scheduler, defer Phase 4
- ✅ Address blacklist (§ 10) — R7 3 cấp
- ✅ Brand unknown (§ 11) — R6
- ✅ Phone invalid (§ 12) — R4
- ✅ Escalation L3 (§ 13) — R4 + R7 (flag ESCALATION + queue HIGH)

**Items defer Phase 4 (có lý do kỹ thuật rõ):**
- `app/guards/pii_leak.py` — phụ thuộc multi-session DB scan + Redis cache (avoid N+1 query) → Phase 4 cùng Redis.
- `app/llm/intent_classifier.py` Layer 2 LLM — Layer 1 regex đã cover 90% case. Layer 2 nâng accuracy nhưng cần test thật benchmark trước.
- `app/llm/auto_derive.py` mở rộng (brand_short, initials, slogan) — phụ thuộc LLM_QUALITY thinking_budget settings + cost analysis.
- Voice STT MVP — kênh hoàn toàn mới, defer cùng Zalo Mini App integration.
- Background scheduler — phụ thuộc Redis + Celery/RQ.

**Files mới Phase 3 (15 file):**
- `app/admin/__init__.py` + `queue.py`
- `app/core/abuse_detector.py`, `address_blacklist.py`, `brand_check.py`, `edge_cases.py`, `garbage_detector.py`
- `app/guards/__init__.py` + `drift.py` + `hallucinate.py` + `injection.py`
- `data/address_blacklist.json`, `brand_list.json`, `forbidden_vocab.json`
- `tools/test_phase3_scenarios.py` + 4 quick_test scripts
- 7 unit test file mới + integration tests

**KPI Phase 3 (verified):**
- Injection detect: live test 3 turn → flag PROMPT_INJECTION + queue HIGH ✓
- Hallucinate: LLM bịa → null field + flag ✓
- Drift auto-rewrite: BRANDKIT → "bộ thương hiệu", scoring vocab REMOVE ✓
- Admin queue trigger 13/13 rule (escalation HIGH + abuse + address_bl + sanity_fail + 4 MEDIUM + 2 LOW)
- 10/12 edge case test pass (2 còn defer kỹ thuật — voice + im lặng)
- Tests: 830 pass

---

### PHASE 4 — Infrastructure + Edge case còn lại + Quality enhancements (8-10 ngày)

**Mục tiêu:** scale production + close 2 edge case defer + tinh chỉnh quality.

**Scope IN — chia 4 round:**

**R1: Im lặng kéo dài + Background scheduler (1C § 9)**
- `app/scheduler/timeout_worker.py` — sweep session timeout 1h
- `app/scheduler/confirming_nudge.py` — sau bot Card render, im 3 phút → nhắc "anh duyệt giúp em với ạ?"; im 10 phút → soft-close
- Redis pub/sub cho real-time event (hoặc Celery beat đơn giản)

**R2: Voice STT MVP + Voice fail handler (1C § 8)**
- `app/voice/stt_client.py` — Google Speech-to-Text API
- `app/llm/brand_correction.py` — STT brand correct ("xinhpha" → "Xingfa"), refer brand_list.json
- `data/stt_corrections.json` — common STT errors mapping
- Voice fail 3 lần → flag VOICE_QUALITY_POOR + suggest text channel

**R3: PII leak guard + Layer 2 intent classifier (LLM fallback)**
- `app/guards/pii_leak.py` — cross-session check (load all profiles → compare phone/address/name xuất hiện trong bot reply)
- `app/llm/intent_classifier.py` Layer 2 — call LLM_FAST khi regex Layer 1 fail
- Cache LLM intent result Redis TTL 1h (refer F2C.5)

**R4: Redis + Rate limit + Logging + Monitoring**
- `app/cache/client.py` Redis backend (thay in-memory dict)
- `app/cache/session_lock.py` Redis lock TTL 30s (chống concurrent write)
- `app/guards/rate_limit.py` Redis-backed IP/msg limit
- `app/cache/llm_cache.py` cache intent/STT/address/slogan TTL 24h-7d
- `app/logging_setup.py` structured JSON + correlation_id
- (Optional) Prometheus exporter + Grafana

**Auto-derive mở rộng** (cùng R4 nếu time cho phép):
- `app/llm/auto_derive.py` thêm: brand_name_short, initials_full, initial_single, slogan_options (LLM gen 5 phương án)

**KPI Phase 4:**
- Im lặng 1h → auto soft-close ✓ + flag
- Voice fail 3 lần → flag VOICE_QUALITY_POOR
- Cache hit rate ≥ 50% (intent + STT + address)
- Load test 100 concurrent dealer no race condition
- IP rate limit chặn brute force (vd 30 msg/phút/IP)
- 12/12 edge case test pass (đủ File 1C)

---

## PHẦN 5 — Action items Phase 1 (MVP)

| # | Task | File path | Spec | Effort | Owner |
|---|---|---|---|---|---|
| **0a** | **Bootstrap: `.env.example`** (GEMINI_API_KEY, ANTHROPIC_API_KEY, ADMIN_USER, ADMIN_PASS, DATABASE_URL, LLM_FAST=gemini-2.5-flash, LLM_QUALITY=gemini-2.5-pro) | `.env.example` | — | XS | Claude |
| **0b** | **Bootstrap: `requirements.txt` rewrite** (google-generativeai, anthropic, pydantic>=2, fastapi, uvicorn, pytest, pytest-asyncio, httpx) | `requirements.txt` | — | XS | Claude |
| **0c** | **Bootstrap: `pytest.ini` + `.gitignore` rules** (test discovery + ignore chatbot.db*, .env, __pycache__/, _legacy_*) | `pytest.ini` + `.gitignore` | — | XS | Claude |
| **0d** | **Bootstrap: `.pre-commit-config.yaml` (optional)** — black + isort + flake8 cơ bản. Defer nếu Duong không muốn | `.pre-commit-config.yaml` | — | XS | Duong duyệt |
| 1 | Tạo branch `refactor/v8` + tag v7-last-stable | git | — | XS | Duong |
| 2 | Backup code cũ → `_legacy_v7.zip` + DB cũ export | `tools/export_legacy_db.py` | — | S | Claude |
| 3 | Drop `dealers.db`, tạo `chatbot.db` schema mới | `app/storage/migrations/001_init.sql` | F2C.1 | M | Claude |
| 4 | Schema Pydantic mới (Scope 1+2+3, drop v6) | `app/models/schema.py` | F2A.3 | M | Claude |
| 5 | Stage enum + transitions table | `app/core/stages.py` | F2A.1 | S | Claude |
| 6 | Session class + lazy timeout check | `app/core/session.py` | F2A.1 | S | Claude |
| 7 | 17 slot definitions + REQUIRED list | `app/slots/definitions.py` | F2A.5 | S | Claude |
| 8 | 17 slot templates (1 biến thể MVP) | `app/slots/templates.py` | F2A.5 + File 1A | M | Claude |
| 9 | Intent Layer 1 regex (7 intent) | `app/core/intent.py` + `regex_markers.py` | F2A.2 | M | Claude |
| 10 | State machine smart advance | `app/core/state_machine.py` | F2A.4 | L | Claude |
| 11 | System prompt builder ≤ 600 token | `app/llm/system_prompt.py` + `templates/sys_prompt.md` | F2B.1 | S | Claude |
| 12 | LLM client unified routing `LLM_FAST`/`LLM_QUALITY` + vendor adapter (gemini.py primary, claude.py fallback) | `app/llm/client.py` | F2B.1 + D8 | M | Claude |
| 13 | Extractor schemas + runner (3 slot Phase 1) | `app/llm/extractors/{schemas,runner,validators}.py` | F2B.2 | M | Claude |
| 14 | Ack generator tone "ban" default | `app/llm/ack_generator.py` | F2B.4 | M | Claude |
| 15 | Fallback safe ack + retry utility | `app/llm/fallback.py` + `app/utils/retry.py` | F2C.4 | S | Claude |
| 16 | Sanity 5-point + validators | `app/core/sanity.py` + `validators.py` | F2A.7 | M | Claude |
| 17 | Greeting + Closing engine (1 biến thể) | `app/core/greeting.py` + `closing.py` | F2A.8 | S | Claude |
| 18 | Card renderer 5 phần | `app/core/card_renderer.py` | File 1A § 6 | M | Claude |
| 19 | Data loaders + 3 JSON file (province_list, province_specialty, main_category_enum) | `app/cache/data_loaders.py` + `data/*.json` | F2C.7 | S | Claude |
| 20 | Conversation orchestrator ≤ 300 dòng | `app/core/conversation.py` | F2A.1 + F2A.4 | M | Claude |
| 21 | API chat.py adapt + frontend chat.js field map | `app/api/chat.py` + `static/chat.js` | — | M | Claude |
| 22 | Wire main + config + logging | `app/main.py`, `app/config.py`, `app/logging_setup.py` | — | S | Claude |
| 23 | Test pyramid Phase 1 (unit + e2e happy case) | `tests/unit/*` + `tests/e2e/test_phase1_happy.py` | acceptance | M | Claude |
| 24 | Update SYNC_LOG.md với version v0.1.0 cho code | `SYNC_LOG.md` | — | XS | Claude |

**Effort total Phase 1:** ≈ 6-8 ngày dev (1 dev FT) hoặc 3-4 ngày
(Claude code song song).

**Effort guide:** XS=<2h, S=0.5-1d, M=1-2d, L=2-4d.

---

## PHẦN 6 — Risk + mitigation

### Risk 1 — Spec quá chi tiết, dev miss

| Risk | Mitigation |
|---|---|
| 6 file spec ~3000 dòng — dev nhồi 1 lúc không hết | Mỗi rule có "Pointer implementation" → dev đọc rule khi code module đó, không cần memorize hết |
| Acceptance test trong spec là VÍ DỤ — dev có thể over-fit case | Mỗi test có DISCLAIMER "không khóa cứng, engine cover shape tương tự" — dev viết test với multiple cases |

### Risk 2 — LLM cost spike

| Risk | Mitigation |
|---|---|
| 17 extractor + ack + intent + address + auto-derive → nhiều LLM call/turn | Phase 1 cache TTL trong session → cùng message không gọi lại; Phase 4 Redis cache cross-session |
| `LLM_QUALITY` ack đắt hơn `LLM_FAST` nhiều lần (Sonnet vs Haiku 5x, Gemini Pro vs Flash ~10x) | Route theo dealer_type: Bận/Lửa Lò → `LLM_FAST`, Khoe/Lo → `LLM_QUALITY` |
| Test/dev gọi LLM thật → cost | Mock LLM trong unit + integration test, chỉ real LLM trong e2e |

### Risk 3 — Schema migration sai

| Risk | Mitigation |
|---|---|
| Drop dealers.db cũ → admin mất data | Export JSON trước → archive vào `_legacy_dealers_export.json` |
| Schema mới miss field → bug nghiêm trọng | SQL DDL trong file riêng (`migrations/001_init.sql`), Pydantic strict mode |
| Field mới (warranty_responsibility_signal) trong DB nhưng code chưa fill → null | NULL acceptable cho OPTIONAL — sanity check Phase 1 chỉ check REQUIRED |

### Risk 4 — Frontend break

| Risk | Mitigation |
|---|---|
| Card field cũ (customer_base_estimate, pain_points) frontend hiển thị → undefined | Drop frontend code cũ, viết lại render block Card 5 phần |
| WebSocket / event handler cũ không khớp API mới | API contract `app/models/api.py` strict — viết test trước khi đụng frontend |

### Risk 5 — Phase 1 trễ

| Risk | Mitigation |
|---|---|
| Estimate 6-8 ngày dev có thể vượt | Scope cut: 3 REQUIRED slot thay vì 6; 1 biến thể template thay vì 3; lazy timeout thay scheduler |
| Block bởi infra (Redis) | Phase 1-3 dùng in-memory adapter, infrastructure code defer Phase 4 |

### Risk 6 — Vocab leak (Scoring/Tier/C-code)

| Risk | Mitigation |
|---|---|
| LLM lỡ output "Tier A", "C-score 75" với dealer | Guard F2B.8 drift auto-rewrite (forbidden_vocab.json) — luôn ON |
| Frontend hiển thị mã C1-C9 trong card | Sanity check 5-point + card_renderer strict whitelist field |

### Risk 7 — Pre-commit hook / git config

| Risk | Mitigation |
|---|---|
| Refactor lớn → nhiều commit, dễ conflict | Branch `refactor/v8` tách biệt main, merge khi xong Phase 1 |
| .gitignore cần update | Add `_legacy_v7.zip`, `_legacy_dealers_export.json`, `chatbot.db-wal`, etc. |

---

## PHẦN 7 — Open questions

Trước khi bắt đầu code Phase 1, em cần Duong quyết:

### Q1: Branch strategy

Em đề xuất: tạo branch `refactor/v8`, code Phase 1 trên đó, demo OK
mới merge main. Anh OK chứ?

### Q2: Backup dealers.db cũ

Em export ra JSON trước khi drop — admin có thể xem nếu cần. Đồng ý?

### Q3: Phase 1 scope cut (3 REQUIRED thay 6)

Em đề xuất chỉ làm 3 slot REQUIRED đơn giản (1.1, 1.2, 4.0) cho Phase 1
MVP. Slot 1.3 (phone), 2.1 (main_product), 2.2 (business_model) đẩy
Phase 2. Anh OK hay muốn đủ 6 ngay?

### Q4: Bỏ playbook/* cũ?

Em đề xuất move sang `_legacy_v7.zip` và xóa khỏi repo (vì spec 1B/1C
thay thế hết). Anh OK chứ?

### Q5: Test framework

Em dùng `pytest` (chuẩn Python). Anh OK hay muốn cái khác?

### Q6: Frontend rewrite hay adapt?

`static/chat.js` cũ có thể adapt được, nhưng card render khác 100%.
Anh muốn:
- **(a) Adapt** chat.js cũ — giữ event handler, đổi block card
- **(b) Rewrite** chat.js — clean code mới (effort +1-2 ngày)

Em đề xuất **(a)** Phase 1, rewrite nếu cần Phase 2.

### Q7: Phase 4 — Redis vs in-memory production?

Production scale nhỏ (≤100 dealer/ngày) thì in-memory + SQLite WAL đủ.
Redis chỉ cần khi scale 1000+ dealer/ngày. Anh có ước tính scale không?

### Q8: Deploy Railway

Code cũ deploy Railway (Procfile + railway.json). Phase 1 vẫn deploy
Railway dev URL? Hay test local trước?

---

**Khi anh duyệt plan này + trả lời Q1-Q8 → em bắt đầu Phase 1 ngay
(action item #1).**
