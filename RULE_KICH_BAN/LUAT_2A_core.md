# LUẬT 2A — Core Logic (state machine + intent + schema)

> **Vai trò:** Spec TECHNICAL — cách engine **thực thi** flow từ File 1A.
> Audience: developer / engineer / architect.
>
> **Cross-ref:**
> - ⬆ CORE — `EM_LINH_MKT_CORE.md` (nguyên tắc gốc)
> - ↔ File 1A — `KICH_BAN_1A_core.md` (script behavioral)
> - ↔ File 2B — `LUAT_2B_llm.md` (LLM prompt + extractor + guards)
> - ↔ File 2C — `LUAT_2C_infra.md` (spam guard + concurrency + storage)

---

## VERSION & CHANGELOG

**Version:** v0.2.5-draft
**Cập nhật:** 2026-05-18

| Ngày | Version | Thay đổi |
|---|---|---|
| 2026-05-18 | v0.2.5-draft | Refactor "không khoá case" đồng bộ KICH_BAN_1A v0.3.0: (1) F2A.3 Scope 2 — bỏ `province_specialty: str` (vi phạm khoá case). (2) F2A.8 viết lại hoàn toàn — BỎ `PROVINCE_SPECIALTY_TABLE` 50 entries, BỎ 3-tier fallback logic specialty match/province only/no province. Thay = LLM gen local_hook (Phase 2) hoặc rỗng (Phase 1). (3) F2A.8 acceptance test mới: PASS = "không chứa hard-code đặc sản", FAIL = "có mapping cứng". (4) F2A.8 constraints thêm "KHÔNG hardcode mapping tỉnh → đặc sản". (5) Pointer implementation thêm `app/llm/local_hook.py` (Phase 2), bỏ `data/province_specialty.json`. |
| 2026-05-15 | v0.2.4-draft | Spec consistency BATCH 4: (1) F2A.4 list action 5 → **6** (thêm `DEFER`), text "1 trong 4" → "1 trong 6 hành động". Sync output tuple `{ADVANCE, RETRY, PARTIAL_RETRY, DEFER, SKIP, PAUSE}`. (2) F2A.4 algorithm step 2.7 mới — branch DEFER cho slot REQUIRED khi `consecutive_attempts >= 2` (refer D11 STRATEGY). Step 2.8 mới — re-check deferred slots khi mood dealer ok. (3) F2A.4 tham số config thêm `MAX_RETRY_CONSECUTIVE=2`, `DEFER_RECHECK_AFTER_N_SLOTS=2`, `MAX_DEFER_PER_SLOT=1`. (4) F2A.1 stage transition tuple sync 6 action. (5) F2A.5 retry algorithm refactor — track `consecutive_attempts` + `total_attempts` riêng, DEFER khi 2 consecutive, SKIP khi 3 total. (6) F2A.7 sanity 5-point thêm bảng `SLOT_TO_REQUIRED_FIELDS` mapping (fix undefined function). (7) F2A.1 Cross-ref bullet line ~616 "CORE § B.2" → "§ J.1 + § G" (batch 2 chỉ fix 2/3 chỗ). (8) F2A.2 edge case table fix broken 3-cột markdown. (9) F2A.3 + F2A.7 cross-ref "schema 3 scope" → "4 scope". (10) F2A.3 Scope 4 "Gemini chấm" → "LLM_QUALITY chấm" (batch 2 sót). |
| 2026-05-15 | v0.2.3-draft | Spec consistency BATCH 3: F2A.4 algorithm thêm action thứ 5 `PARTIAL_RETRY` + step 2.6 — slot multi-field (1.1, 1.2, 2.1, 2.4, 2.5, 2.6, 3.3) khi dealer fill 1 phần → ack + hỏi field còn thiếu, KHÔNG count `slot_attempts`. Sync với GLOSSARY § Action + 1A § 1.5 + § 4 slot 1.1 PARTIAL handler. Trước đây engine sẽ count retry sai khi dealer fill 1/2 field → dealer bực ("em vừa cho rồi mà"). |
| 2026-05-15 | v0.2.2-draft | Spec consistency BATCH 2: (1) F2A.4 algorithm thêm step 2.5 — branch sớm slot 4.0 consent=no → mark skip 4.1/4.2 + đi CONFIRMING (sync File 1A slot 4.0 handler). (2) F2A.3 Scope 3 + Scope 4 model-agnostic: "Backend Scoring (Gemini chấm)" → "(`LLM_QUALITY` chấm — pilot Gemini 2.5 Pro)" (refer D8 STRATEGY). (3) F2A.3 docstring `# OPTIONAL (~14 field)` → `# OPTIONAL (16 field) + RAW SIGNAL (6) = 22`. (4) F2A.7 ADDRESS_BLACKLIST — bỏ pointer "CORE § J.6" (CORE không có section đó), thêm note hierarchy "CORE § E.5 nguyên tắc + 2A spec detail". (5) F2A.1 pointer CORE "§ B.2 (workflow)" → "§ J.1 (workflow voice-first) + § G (khung chạy)" — § B.2 thực sự là rule tone default. |
| 2026-05-15 | v0.2.1-draft | Spec consistency: F2A.3 Scope 3 mở rộng `flags` enum 6 → **15 flag** chia 4 nhóm (behavior 4 + abuse 5 + data quality 4 + LLM guard 2) — sync với 1C edge cases + 2C F2C.8 admin queue triggers + KE_HOACH_REFACTOR § 2.3. Trước đây enum thiếu 9 flag gây Pydantic validation error khi 1C/2C trigger. |
| 2026-05-14 | v0.2.0-draft | Hoàn thành 8 rule: F2A.1 Stages, F2A.2 Intent, F2A.5 Slot priority + retry, F2A.6 Dealer type detection, F2A.7 Sanity check, F2A.8 Greeting/Closing engine |
| 2026-05-14 | v0.1.0-draft | Tạo file — viết khung + mẫu 2 rule (F2A.3 schema + F2A.4 smart advance) |

---

## MỤC LỤC

- [F2A.1 — Stages + transitions](#f2a1--stages--transitions) ⏳
- [F2A.2 — Intent detection](#f2a2--intent-detection) ⏳
- [F2A.3 — Schema 4 scope](#f2a3--schema-4-scope) ✓
- [F2A.4 — Smart advance state machine](#f2a4--smart-advance-state-machine) ✓
- [F2A.5 — Slot priority + Required/Optional retry](#f2a5) ⏳
- [F2A.6 — Dealer type detection](#f2a6) ⏳
- [F2A.7 — Sanity check before save](#f2a7) ⏳
- [F2A.8 — Greeting + Closing engine](#f2a8) ⏳
- [Cross-ref](#cross-ref)

---

## F2A.3 — Schema 4 scope

**Tham chiếu CORE:** § H.1 Hồ sơ RAW — schema chia 4 scope
**Tham chiếu File 1A:** § 4 (mỗi slot có "Fill field" mapping)

### Yêu cầu

Profile data chia **4 scope** rõ ràng, mỗi scope có quy tắc lưu trữ +
generate khác nhau:

| Scope | Bên gen | Storage | Mutability |
|---|---|---|---|
| **1. CHATBOT thu trực tiếp** | Chatbot (qua 17 slot) | `dealer_profile_raw` | Dealer xác nhận tại CONFIRMING → freeze |
| **2. CHATBOT auto-derive** | Chatbot (parse/lookup/AI gen) | `dealer_profile_raw` | Tự gen sau khi nhóm 1 đủ |
| **3. State nội bộ** | Chatbot (state machine) | `dealer_profile_raw` | Update mỗi turn |
| **4. KHÔNG phải chatbot gen** | Backend Scoring / Designer team | Bảng RIÊNG (không trong `dealer_profile_raw`) | Chatbot CHỈ đọc, KHÔNG ghi |

### Algorithm — quyết định scope cho field

```
Input: field_name
Output: scope (1/2/3/4)

1. Check field_name trong WHITELIST:
   - Trong list "dealer-input" → Scope 1
   - Trong list "chatbot-derive" → Scope 2
   - Trong list "internal-state" → Scope 3
   - Trong list "external-system" → Scope 4
   - Không thuộc list nào → REJECT, log error

2. Apply rule theo scope:
   - Scope 1: validate input (regex / enum) trước khi save
   - Scope 2: trigger gen sau khi Scope 1 đủ field cần
   - Scope 3: update mỗi turn, không cần validate dealer
   - Scope 4: KHÔNG ghi vào dealer_profile_raw, lưu hoặc passthrough
     sang bảng khác
```

### Schema mapping (refer CORE § H.1)

**Scope 1 — CHATBOT thu (17 slot → 22 field):**

```python
# REQUIRED (6 field)
dealer_name: str          # slot 1.1
owner_name: str           # slot 1.1
address: str              # slot 1.2
phone_or_zalo: str        # slot 1.3
main_product: str         # slot 2.1
brandkit_consent: Literal["yes", "no"]  # slot 4.0

# OPTIONAL (16 field) + RAW SIGNAL (6 field) = 22 trường, "không biết" → null + flag dealer_declined
category_stack: list[str]                       # slot 2.1
business_model_signal: str | None               # slot 2.2
est_team_size: int | None                       # slot 2.3
team_stability_signal: str | None               # slot 2.3
supplier_brands: list[str]                      # slot 2.4
customer_segment_signal: str | None             # slot 2.4
primary_contact_channel: str | None             # slot 2.5
zalo: str | None                                # slot 2.5
facebook: str | None                            # slot 2.6
fb_marketing_status: str | None                 # slot 2.6
customer_old_percentage: str | None             # slot 3.1
customer_storage_method: str | None             # slot 3.2
customer_pain: str | None                       # slot 3.3 (text dài raw)
payment_terms_signal: str | None                # slot 3.4
color_accent: str | None                        # slot 4.2
feng_shui_signal: str | None                    # slot 4.2

# RAW SIGNAL cho 9 tiêu chí (mining từ slot)
local_dominance_signal: str | None              # slot 1.2 (C6)
supplier_negotiation_signal: str | None         # slot 2.4 (C8)
community_network_signal: str | None            # slot 2.6 (C9)
motivation_signal: str | None                   # slot 3.3 (C5)
usp_signal: str | None                          # slot 3.3 (bonus)
warranty_responsibility_signal: str | None      # slot 3.5 (C4)
```

**Scope 2 — CHATBOT auto-derive:**

```python
# Parse từ address
province: str | None             # parse từ address
district: str | None             # parse từ address
# REMOVED 2026-05-18: province_specialty (vi phạm "không khoá case",
# refer SYNC_LOG + File 1A § 7.4)

# Chuẩn hóa enum
main_category: Literal["cua_cuon", "cua_nhom_kinh", "cua_thep",
                       "tu_bep", "solar", "bao_tri", "vlxd"] | None
dealer_type: Literal["dai_ly", "chu_xuong", "tho_doi",
                     "nha_thau_nho"] | None

# AI auto-derive từ dealer_name
brand_name_short: str | None     # rút gọn (vd "Thanh Tùng" từ "Nhôm Kính Thanh Tùng")
initials_full: str | None        # chữ cái đầu (vd "NKTT")
initial_single: str | None       # 1 chữ biểu trưng (vd "T")

# Default
contact_name: str | None         # = owner_name
contact_role: str                # = "Chủ cửa hàng"
hotline: str | None              # = phone_or_zalo

# AI gen 5 phương án
slogan_options: list[str]        # 5 phương án (dealer chọn ở ứng dụng nhỏ)
```

**Scope 3 — State nội bộ:**

```python
# Status
confirmation_status: Literal["PENDING", "CONFIRMED", "EDITED"]
review_status: Literal["RAW", "UNDER_REVIEW", "APPROVED", "REJECTED"]

# Flags (multi-select) — full enum sync với File 1C edge cases + File 2C admin queue triggers
flags: list[Literal[
    # Behavior flags (4)
    "dealer_declined",            # đại lý từ chối slot OPTIONAL ("không biết") — File 1C
    "required_missing",           # slot REQUIRED skip sau 3 retry — F2A.5
    "consent_unclear",            # brandkit_consent không rõ sau retry — slot 4.0
    "multiple_refusal_in_row",    # 3 OPTIONAL refuse liên tiếp → rút gọn mode — File 1C § 4

    # Abuse / safety flags (5)
    "prompt_injection",           # detect injection pattern — File 1C § 6
    "abusive_language",           # dealer chửi cá nhân — File 1C § 5
    "garbage_input",              # gibberish lặp — File 1C § 7
    "dealer_too_defensive",       # defensive ≥ 3 lần — File 1C § 2
    "address_blacklist",          # address chính trị/tôn giáo — File 1C § 10

    # Data quality flags (4)
    "sanity_check_failed",        # F2A.7 5-point check fail
    "phone_invalid_after_retry",  # phone sai format 3 lần — File 1C § 12
    "voice_quality_poor",         # STT empty/noise lặp — File 1C § 8
    "brand_not_in_whitelist",     # brand lạ → admin review — File 1C § 11

    # LLM guard flags (2)
    "hallucinate",                # LLM bịa data dealer chưa cho — F2B.8 G2
    "pii_leak",                   # bot share data dealer khác — F2B.8 G4
]]
# Tổng: 4 + 5 + 4 + 2 = 15 flag. Khi thêm flag mới: bump version + update GLOSSARY § 4 + KE_HOACH_REFACTOR § 2.3

# State machine
current_slot: str | None         # slot đang chờ data (vd "2.3")
slot_attempts: dict[str, int]    # retry count per slot
skipped_slots: list[str]         # slot đã skip (mark advance)
detected_dealer_type: Literal[
    "lua_lo", "khoe", "lo", "ban", "unknown"
] | None                         # detect sau turn 3
```

**Scope 4 — KHÔNG phải chatbot gen:**

```python
# Backend Scoring (`LLM_QUALITY` chấm — pilot Gemini 2.5 Pro, vendor mapping ở config)
# Service RIÊNG, KHÔNG LƯU TRONG dealer_profile_raw.
# Chatbot xuất raw signal, Backend Scoring tự đọc + gen các trường này:
c1..c9: Literal[0, 1, 2]                # điểm từng tiêu chí
confidence_c1..c9: Literal["LOW", "MEDIUM", "HIGH"]
c_score: float                           # 0-100
tier: Literal["A", "B", "C", "D"]
batch: Literal[1, 2, 3]
dealer_id: str                           # cấp sau human review
dealer_status: str                       # default "Active"
admin_area_code: str                     # lookup từ address
editor_name: str                         # default "Em Linh MKT bot"
note: str                                # auto summary

# Designer team / ứng dụng nhỏ — KHÔNG LƯU TRONG dealer_profile_raw
logo_png: str                            # URL file gen sau
tvc_duration: int                        # default 8s
tvc_ratio: str                           # default "16:9"
```

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine PHẢI xử mọi case có shape tương tự,
> KHÔNG khóa cứng vào field cụ thể trong example.**

**Pattern test:** Engine phải reject field không thuộc whitelist 4 scope.

**Case ví dụ:**

```
Input: extractor LLM trả về field "dealer_revenue" (không trong schema)
Output: REJECT field, log warning, KHÔNG ghi vào dealer_profile_raw

Input: extractor trả "c_score: 75" (Scope 4)
Output: REJECT, log warning "chatbot KHÔNG được gen scoring fields"

Input: extractor trả "brand_name_short: 'Thanh Tùng'"
Output: ACCEPT, ghi vào dealer_profile_raw (Scope 2 — chatbot auto-derive)

Input: extractor trả "phone_or_zalo: 'abc123'"
Output: validate format → digits-only? KHÔNG → REJECT, hỏi lại slot 1.3
```

**Tổng quát hóa:**
- Engine validate MỌI field extracted theo schema (whitelist + type +
  enum + format)
- Field không thuộc Scope 1/2/3 → REJECT
- Field thuộc Scope 4 mà extractor cố ghi → REJECT + log warning
- Format invalid (vd phone không digits) → REJECT + retry slot

✅ **PASS:**
- Schema strict — chỉ field trong whitelist được lưu
- Validate format trước khi save (phone digits, enum chuẩn)
- Scope 4 fields KHÔNG bao giờ xuất hiện trong `dealer_profile_raw`

❌ **FAIL:**
- Extractor "bịa" thêm field tự đặt → engine ghi vào DB → DB schema vỡ
- Phone "abc" → save không validate → DB chứa data bẩn
- Scope 4 fields (c_score, tier) ghi vào `dealer_profile_raw` → conflict
  với Backend Scoring

### Constraints (KHÔNG được vi phạm)

- KHÔNG cho phép field ngoài whitelist
- KHÔNG ghi Scope 4 fields vào `dealer_profile_raw`
- Validate format trước save (phone, enum, length)
- Scope 1 REQUIRED missing → flag `required_missing`, KHÔNG block save

### Pointer implementation

→ `app/models/schema.py` § `DealerProfileRaw` Pydantic class
→ `app/storage/sqlite_store.py` § schema migration + INSERT

### Cross-ref

- ⬆ CORE § H.1 (schema 4 scope) — sync sau batch 2 spec consistency, thêm
  "auto-derive" tách riêng cho rõ
- ⬅ File 1A § 4 (mỗi slot fill field nào)
- ➡ F2A.4 (smart advance dùng schema field)
- ➡ F2A.7 (sanity check validate schema)
- ➡ File 2B § extractor schema (LLM tool input_schema)

---

## F2A.4 — Smart advance state machine

**Tham chiếu CORE:** § G.4 Logic Required/Optional + Smart advance
**Tham chiếu File 1A:** § 1.4 Quy ước Required/Optional + § 4 slot Q&A

### Yêu cầu

Sau mỗi message từ đại lý, state machine quyết định 1 trong **6 hành động**:

- `ADVANCE` — chuyển sang slot tiếp theo
- `RETRY` — hỏi lại slot hiện tại tone giảm dần (consecutive +1, total +1)
- `PARTIAL_RETRY` — slot multi-field, dealer fill 1 phần — ack + hỏi field
  còn thiếu, **KHÔNG đếm `slot_attempts`** (refer step 2.6)
- `DEFER` — slot REQUIRED sau 2 lần liên tiếp chưa fill → tạm gác, đi slot
  khác. Engine sẽ re-check sau N slot và hỏi lần 3 nếu mood dealer ok hơn.
  Đếm vào `total_attempts` + `defer_count`. Refer step 2.7 + § 1.6 trong 1A.
- `SKIP` — bỏ slot hiện tại, qua slot kế (OPTIONAL "không biết" / REQUIRED
  đã hết 3 lần total)
- `PAUSE` — tạm dừng flow để xử intent đặc biệt (defensive/tâm sự)

### Algorithm

```
Input:  session, latest_message
Output: (next_slot_to_ask, action ∈ {ADVANCE, RETRY, PARTIAL_RETRY, DEFER, SKIP, PAUSE})

1. Detect intent của message (xem F2A.2):
   - defensive (hỏi ngược)  → return (current_slot, PAUSE_DEFENSIVE)
   - tâm sự (chuyện đời)     → return (current_slot, PAUSE_TAM_SU)
   - refusal (từ chối):
     • slot REQUIRED → RETRY (tone nhẹ hơn, max 3 lần)
     • slot OPTIONAL → SKIP NGAY, advance qua next slot
   - "không biết" / "không có":
     • slot REQUIRED → RETRY với option dễ hơn (lượt 3 có offer fallback)
     • slot OPTIONAL → SKIP NGAY (ack tôn trọng), advance
   - bình thường → tiếp bước 2

2. Extract field từ message → merge vào profile (theo F2A.3 schema rules)

2.5. **Branch sớm — slot 4.0 consent path** (refer File 1A § 4 Slot 4.0):
   - if current_slot == "4.0" và extracted brandkit_consent == "no":
       → mark skipped_slots += ["4.1", "4.2"]
       → set stage = CONFIRMING (skip thẳng tới render Card 4 phần,
          không hỏi logo/màu)
       → render Closing path consent=no ở stage DONE (refer 1A § 7)
   - else: tiếp bước 2.6

2.6. **PARTIAL fill cho slot multi-field** (slot 1.1, 1.2, 2.1, 2.4, 2.5,
     2.6, 3.3 — các slot mà File 1A § 4 ghi fill ≥ 2 field):
   - Mỗi slot có `required_fields_in_slot` (vd slot 1.1 = ["owner_name",
     "dealer_name"]; slot 2.1 = ["main_product"] — `category_stack` là OPTIONAL)
   - Sau extract: tính `filled = extracted ∩ required_fields_in_slot`
                  và `missing = required_fields_in_slot − filled`
   - Case A — full fill (`missing == []`): tiếp bước 3 bình thường.
   - Case B — partial fill (`filled ≠ []` và `missing ≠ []`):
       → **KHÔNG count** vào `slot_attempts` (dealer đã chia sẻ 1 phần,
         không phải retry full)
       → set action = `PARTIAL_RETRY`
       → ack field đã cho + hỏi NGAY field còn thiếu (refer File 1A § 4
         partial fill template cho mỗi slot)
       → stay current_slot
   - Case C — empty fill (`filled == []`) và slot REQUIRED:
       → bình thường RETRY tone giảm dần (tiếp bước 3)
   - Case D — empty fill và slot OPTIONAL:
       → SKIP NGAY (tiếp bước 3)

2.7. **Branch DEFER cho slot REQUIRED — kiên nhẫn 2-lần-liên-tiếp**
     (refer 1A § 1.6):
   - Nếu `current_slot ∈ REQUIRED_SLOTS` và `filled = []`:
       a. Detect dealer pattern (test/nghịch vs refusal thật vs confusion):
          - intent == `refusal` (rõ ràng từ chối) → bỏ qua check consecutive,
            xuống bước 3 (sẽ DEFER hoặc SKIP)
          - intent == `khong_biet` ("không biết / không nhớ") → coi như
            partial (kiên nhẫn), xuống bước 3
          - default (test/silence/garbage/confusion) → kiên nhẫn, xuống bước 3
       b. consecutive_attempts[current_slot] += 1
          total_attempts[current_slot] += 1
       c. Nếu `consecutive_attempts >= MAX_RETRY_CONSECUTIVE` (=2)
          và `total_attempts < MAX_RETRY_TOTAL` (=3):
              → action = DEFER
              → deferred_slots[current_slot] = {
                    "defer_at_turn": turn_count,
                    "recheck_after_n_slots": DEFER_RECHECK_AFTER_N_SLOTS (=2)
                }
              → consecutive_attempts[current_slot] = 0  (reset for re-check)
              → ADVANCE sang slot kế (skip tạm)
              → return (next_slot, DEFER)
       d. Nếu `total_attempts >= MAX_RETRY_TOTAL` (=3) (đã pass cả lần re-check):
              → action = SKIP + flag `required_missing` + admin warning
              → return (next_slot_after_skip, SKIP)
       e. Else (consecutive < 2 và total < 3):
              → action = RETRY (tone giảm dần theo bảng 1A § 4)
              → return (current_slot, RETRY)

2.8. **Re-check deferred slots** (chạy đầu mỗi turn, trước step 1):
   - Với mỗi slot trong `deferred_slots`:
       Nếu `turn_count - defer_at_turn >= recheck_after_n_slots`
       và dealer mood ok (intent gần nhất ∈ {`affirmative`, `normal`}
       và không phải `refusal`/`abusive_language`):
           → unmark deferred (xóa khỏi `deferred_slots`)
           → set `current_slot` = slot deferred
           → render câu hỏi lần 3 với tone "tha thiết + offer fallback" (1A § 4)
           → consecutive_attempts vẫn 0 (lần 3 = consecutive=1)

3. Đánh giá slot status:
   - slot REQUIRED vừa fill HIGH → ADVANCE
   - slot OPTIONAL vừa fill → ADVANCE
   - slot REQUIRED còn empty/LOW (sau bước 2.7 đã xử lý xong REQUIRED ở đây
     ít khi vào — chỉ vào nếu intent=`refusal` bỏ qua check consecutive):
       → DEFER nếu chưa hết total; SKIP + flag `required_missing` nếu hết
   - slot OPTIONAL còn empty:
       → SKIP NGAY (không retry), ghi field=null + flag `dealer_declined`

4. Chọn next_slot (cho ADVANCE/SKIP):
   - List slot missing
   - Filter: bỏ slot đã skipped_slots
   - Sort theo SLOT_PRIORITY_ORDER (17 slot, từ 1.1 → 4.2)
   - Trả slot đầu tiên trong list filtered
   - Nếu list rỗng (tất cả slot done) → set stage = CONFIRMING
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `MAX_RETRY_TOTAL` | 3 | Tổng số lần hỏi 1 slot REQUIRED / session — sau N → SKIP + flag `required_missing` |
| `MAX_RETRY_CONSECUTIVE` | 2 | Số lần hỏi LIÊN TIẾP tối đa — sau N → DEFER (gác slot, đi slot khác). Tránh dealer bực vì hỏi dồn dập (refer 1A § 1.6) |
| `MAX_RETRY_OPTIONAL` | 0 | OPTIONAL không retry — SKIP NGAY |
| `DEFER_RECHECK_AFTER_N_SLOTS` | 2 | Sau N slot khác mới re-check slot deferred (để mood dealer ok hơn) |
| `MAX_DEFER_PER_SLOT` | 1 | 1 slot chỉ được DEFER 1 lần / session (tránh defer loop vô hạn) |
| `REQUIRED_SLOTS` | `["1.1", "1.2", "1.3", "2.1", "2.2", "4.0"]` | 6 slot bắt buộc retry |
| `SLOT_PRIORITY_ORDER` | `["1.1","1.2","1.3","2.1","2.2","2.3","2.4","2.5","2.6","3.1","3.2","3.3","3.4","3.5","4.0","4.1","4.2"]` | Trật tự ưu tiên 17 slot |
| `SESSION_PAUSE_THRESHOLD` | 10 phút | Sau N im → KHÔNG nhắc |
| `SESSION_TIMEOUT` | 1 giờ | Sau N → soft-end |

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine PHẢI xử mọi case có shape tương tự,
> KHÔNG khóa cứng vào câu/turn cụ thể trong example.**

**Pattern test:** Slot OPTIONAL khi đại lý nói "không biết" → SKIP NGAY,
KHÔNG retry. Slot REQUIRED khi đại lý không cho → RETRY max 3 lần với
tone giảm dần.

**Case ví dụ minh họa:**

```
Bot ask slot 4.2 (color_accent — OPTIONAL):
  "Anh thích màu nào, có hợp mệnh phong thủy không ạ?"

Turn N+1: Dealer "anh không biết phong thủy"
          → intent="khong_biet" + slot 4.2 OPTIONAL
          → SKIP NGAY, KHÔNG retry
          Bot: "Dạ vâng, em ghi nhận. Phần này em sẽ chọn cho phù hợp
                ngành nhôm kính luôn nhé. Mình tiếp tục."
          → color_accent = null
          → flag += "dealer_declined"
          → ADVANCE → slot kế (hoặc CONFIRMING nếu hết slot)

---

Bot ask slot 1.3 (SĐT — REQUIRED):
  "Cho em xin số Zalo ạ?"

Turn N+1: Dealer "đéo cho"
          → intent="refusal" + slot 1.3 REQUIRED
          → RETRY 1 (tone nhẹ + giải thích)
          Bot: "Dạ em hiểu anh ngại — em xin số chỉ để team người thật
                liên hệ, anh có quyền xoá bất cứ lúc nào. Anh cho em
                được không ạ?"

Turn N+2: Dealer "không"
          → RETRY 2 (offer dễ hơn)
          Bot: "Anh ngại để số chính cũng OK ạ — anh cho em Zalo phụ
                cũng được, hoặc số bất kỳ nào anh tiện liên hệ."

Turn N+3: Dealer "thôi"
          → slot_attempts[1.3] = 3 ≥ MAX_RETRY_REQUIRED
          → SKIP + flag `required_missing`
          Bot: "Dạ vâng, em ghi nhận anh không tiện cho số. Em tạm bỏ
                qua phần này, mình tiếp tục nhé."
          → phone_or_zalo = null
          → flag += "required_missing"
          → admin sẽ review thủ công sau
          → ADVANCE → slot kế
```

**Tổng quát hóa pattern (engine PHẢI cover):**

- Slot OPTIONAL: BẤT KỲ phản hồi "không biết / không có / không nhớ /
  tùy em" → SKIP NGAY. KHÔNG hỏi lại trong cùng session.
- Slot REQUIRED: refusal/empty → RETRY max 3 lần với tone GIẢM DẦN
  (lượt 1 = bình thường, lượt 2 = giải thích lý do, lượt 3 = offer
  fallback dễ hơn). Sau 3 → SKIP + flag.
- Slot bất kỳ: dealer rẽ tâm sự / defensive → PAUSE flow, xử intent
  TRƯỚC, KHÔNG advance.
- Engine tự choose câu hỏi/ack từ biến thể trong File 1A (hash session
  + slot mod 3).

✅ **PASS:**
- OPTIONAL: dealer "không biết" → SKIP đúng 1 lần, advance hợp lệ, flag
  `dealer_declined`
- REQUIRED: retry đúng 3 lần với tone giảm dần, sau đó SKIP + flag
  `required_missing`
- KHÔNG advance khi đang PAUSE_DEFENSIVE / PAUSE_TAM_SU
- Slot skip ≠ bị hỏi lại ở turn sau (skipped_slots tracking đúng)

❌ **FAIL:**
- OPTIONAL retry vô hạn → loop forever
- OPTIONAL: dealer "không biết" rồi vẫn hỏi lại lượt sau → vi phạm
- REQUIRED: retry > 3 lần → loop
- REQUIRED: skip ngay lượt 1 (không cho retry)
- ADVANCE khi đang PAUSE → bơ câu hỏi defensive của dealer
- Slot skipped quay lại ở turn sau → tracking sai

### Constraints (KHÔNG được vi phạm)

- KHÔNG advance khi đang `PAUSE_DEFENSIVE` / `PAUSE_TAM_SU`
- KHÔNG retry slot OPTIONAL (MAX_RETRY_OPTIONAL = 0)
- KHÔNG retry slot REQUIRED quá MAX_RETRY_REQUIRED (= 3)
- Tất cả slot processed → set stage = CONFIRMING (render card)
- skipped_slots không được bị hỏi lại trong cùng session

### Pointer implementation

→ `app/core/conversation.py` § `_handle_v7_turn` (sẽ refactor thành
   `_handle_slot` cho khớp tên slot)
→ `app/core/v7_turns.py` § `V7_TURNS` dict → đổi tên `SLOTS` cho thống
   nhất với spec mới

### Cross-ref

- ⬆ CORE § G.4 (logic Required/Optional + smart advance)
- ⬅ File 1A § 1.4 (quy ước Required/Optional), § 4 (slot Q&A — engine
   chọn câu hỏi/ack từ đây)
- ➡ F2A.2 (intent detection — input cho algorithm)
- ➡ F2A.5 (slot priority order)
- ➡ F2A.7 (sanity check trước save CONFIRMED)
- ➡ File 2C § session timeout (PAUSE handling)

---

## F2A.1 — Stages + transitions

**Tham chiếu CORE:** § J.1 (workflow voice-first), § G (khung chạy 4 stage)
**Tham chiếu File 1A:** § 3 (Greeting), § 4 (slot), § 6 (Confirmation), § 7 (Closing)

### Yêu cầu

Session có 4 stage tuyến tính (không cho phép back, chỉ có ADVANCE):

```
GREETING → ASKING → CONFIRMING → DONE
```

| Stage | Mục đích | Slot active | Output |
|---|---|---|---|
| **GREETING** | Em Linh tự giới thiệu + xin phép trò chuyện | (chưa hỏi slot nào) | Dealer ack "ok" / "làm đi" |
| **ASKING** | Thu 17 slot theo SLOT_PRIORITY_ORDER | slot 1.1 → 4.2 | Tất cả slot processed (filled hoặc skipped) |
| **CONFIRMING** | Render card + chờ dealer xác nhận/sửa | (no slot, chỉ card edit) | `confirmation_status = CONFIRMED` |
| **DONE** | Render Closing + đóng session | — | Session inactive |

### Algorithm — transition logic

```
Function: should_transition(session, latest_message)
Output: next_stage | None (None = giữ nguyên stage)

Stage hiện tại = session.stage

if stage == GREETING:
    Detect intent "affirmative" (ok / làm đi / ừ / okay):
        → next_stage = ASKING
        → set current_slot = "1.1"
    Detect intent "refusal" (không / thôi):
        → next_stage = DONE (soft-close greeting)
        → render apology + lưu flag `greeting_declined`
    Detect "defensive" (hỏi ngược ngay):
        → KHÔNG transition, xử PAUSE_DEFENSIVE trong GREETING
    Default (silence / unclear):
        → KHÔNG transition, hỏi lại "Anh sẵn sàng chưa ạ?"

if stage == ASKING:
    Run F2A.4 smart advance → return action ∈ {ADVANCE, RETRY, PARTIAL_RETRY, DEFER, SKIP, PAUSE}
    if action == ADVANCE và next_slot is None (hết slot, kể cả deferred đã re-check hết):
        → next_stage = CONFIRMING
    elif action ∈ {ADVANCE, RETRY, PARTIAL_RETRY, DEFER, SKIP}:
        → giữ stage = ASKING (update current_slot theo action)
    elif action == PAUSE:
        → giữ stage = ASKING (paused_for = "defensive" / "tam_su")

if stage == CONFIRMING:
    Detect intent "affirmative" (OK / đúng / chuẩn):
        → confirmation_status = CONFIRMED
        → next_stage = DONE
    Detect intent "edit" (sửa X thành Y / X sai):
        → update field theo edit → render card lại
        → giữ stage = CONFIRMING
    Detect intent "refusal" (không confirm):
        → flag `consent_unclear`
        → next_stage = DONE (closing nhẹ)
    Detect silence > 3 phút:
        → nhắc 1 lần "Anh duyệt giúp em với ạ?"
        → silence > 10 phút sau nhắc → soft-close: confirmation_status = PENDING

if stage == DONE:
    → KHÔNG transition. Session inactive.
    → Mọi message sau đều respond polite "Em đã ghi nhận xong rồi anh ạ..."
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `CONFIRMING_NUDGE_AFTER_S` | 180 (3p) | Nhắc nếu dealer im trong CONFIRMING |
| `CONFIRMING_SOFTCLOSE_AFTER_S` | 600 (10p) | Sau nhắc → soft-close |
| `GREETING_TIMEOUT_S` | 300 (5p) | GREETING không có response → soft-end |

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — pattern test, KHÔNG khóa cứng câu cụ thể.**

**Pattern test:** Stage chỉ tiến (forward-only). Engine KHÔNG cho dealer
back về stage trước. Mỗi stage có 1 entry condition + 1 exit condition rõ.

**Case ví dụ:**

```
Session bắt đầu → stage = GREETING
Bot render Greeting biến thể 1 → "...Mình bắt đầu nhé anh?"
Dealer: "ok làm đi"  → intent=affirmative → next_stage=ASKING + current_slot=1.1
Bot hỏi 1.1 → ...
[14 turn ASKING, fill xong 17 slot] → next_slot=None → next_stage=CONFIRMING
Bot render card → "Anh duyệt OK hay cần chỉnh chỗ nào ạ?"
Dealer: "OK chuẩn rồi" → intent=affirmative → confirmation_status=CONFIRMED
       → next_stage=DONE
Bot render Closing → session inactive

---

Edge case: dealer rẽ defensive ở GREETING
Bot Greeting → "Mình bắt đầu nhé anh?"
Dealer: "Lừa đảo à?"  → intent=defensive → KHÔNG transition
                       → PAUSE_DEFENSIVE trong GREETING
                       → Bot trả lời defensive + hỏi lại "Anh OK chưa ạ?"
Dealer: "ok rồi"     → intent=affirmative → next_stage=ASKING
```

**Tổng quát hóa:**
- Stage forward-only: GREETING → ASKING → CONFIRMING → DONE
- Mỗi stage transition phải có TRIGGER rõ (affirmative / hết slot / silence timeout)
- PAUSE trong stage = vẫn giữ stage, chỉ tạm hoãn slot
- DONE = terminal, không respond thêm

✅ **PASS:**
- GREETING → ASKING khi dealer ack
- ASKING → CONFIRMING khi `next_slot == None`
- CONFIRMING → DONE khi `confirmation_status == CONFIRMED`
- PAUSE trong stage không ăn vào transition logic

❌ **FAIL:**
- Stage skip CONFIRMING → đi thẳng DONE (lộn flow)
- ASKING → GREETING (back, vi phạm forward-only)
- DONE vẫn hỏi slot mới (session phải inactive)
- PAUSE_DEFENSIVE trong GREETING mà engine vẫn advance sang ASKING

### Constraints (KHÔNG được vi phạm)

- Stage forward-only — KHÔNG cho back
- ASKING → CONFIRMING chỉ khi hết slot (filled + skipped == 17)
- DONE = terminal — session inactive sau khi đến đây
- Mỗi turn engine LUÔN check stage trước → áp logic của stage đó

### Pointer implementation

→ `app/core/conversation.py` § `_handle_turn` — entry point kiểm tra stage
→ `app/core/session.py` § `Session.stage` enum field

### Cross-ref

- ⬆ CORE § J.1 (workflow voice-first), § G (khung chạy 4 stage)
- ⬅ File 1A § 3 (Greeting), § 6 (Confirmation), § 7 (Closing)
- ➡ F2A.4 (smart advance — chỉ chạy khi stage=ASKING)
- ➡ F2A.7 (sanity check — chạy khi CONFIRMING → DONE)
- ➡ File 2C § session timeout + storage

---

## F2A.2 — Intent detection

**Tham chiếu CORE:** § G.5 (engage tâm sự/defensive)
**Tham chiếu File 1A:** § 2.3-2.7 (markers)

### Yêu cầu

Mỗi message từ dealer phải được classify thành 1 trong 7 intent:

| Intent | Mô tả | Marker example (refer File 1A § 2) |
|---|---|---|
| `affirmative` | Đồng ý / xác nhận / tiếp tục | "ok", "ừ", "chuẩn", "được", "đc" |
| `refusal` | Từ chối field cụ thể | "đéo cho", "không nói", "miễn cho tôi" |
| `khong_biet` | Không có thông tin | "không biết", "không nhớ", "tùy em" |
| `defensive` | Hỏi ngược / nghi ngờ bot/tổ chức | "lừa đảo à?", "phí gì?", "công ty nào?" |
| `tam_su` | Kể chuyện đời (gia đình, sức khỏe, thể thao) | "vợ", "nhậu", "golf", "stress" |
| `edit` | Sửa field đã ghi (chỉ trong CONFIRMING) | "sửa X thành Y", "X sai rồi", "không phải A mà là B" |
| `normal` | Trả lời thẳng câu hỏi slot (default) | — (không match marker nào) |

### Algorithm — 2-layer detection

```
Function: detect_intent(message, stage, current_slot)
Output: intent ∈ 7 enum + extracted_data (optional)

Layer 1: REGEX / marker matching (cheap, fast)
   1. Normalize message: lowercase + strip diacritics-optional + trim
   2. Check markers theo thứ tự ƯU TIÊN (vì 1 message có thể trigger nhiều intent):
      a. defensive (cao nhất — phải xử ngay)
      b. tam_su (kể chuyện rẽ)
      c. refusal (từ chối field)
      d. khong_biet (không có data)
      e. edit (chỉ check khi stage=CONFIRMING)
      f. affirmative
   3. Nếu match marker rõ → return intent

Layer 2: LLM classify (fallback khi Layer 1 không match hoặc ambiguous)
   1. Gọi LLM với prompt classify (xem File 2B § intent classifier prompt)
   2. LLM trả structured output: {intent: ..., confidence: HIGH/MED/LOW}
   3. Nếu confidence=LOW → default intent=normal
   4. Cache result theo hash(message) để không gọi LLM lại
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `INTENT_PRIORITY` | `["defensive","tam_su","refusal","khong_biet","edit","affirmative"]` | Thứ tự check marker (cao xuống thấp) |
| `LLM_CLASSIFY_CONFIDENCE_THRESHOLD` | "MED" | Dưới MED → fallback intent=normal |
| `LLM_CLASSIFY_CACHE_TTL_S` | 3600 | Cache classify trong 1h |

### Edge case rule

| Trường hợp | Xử |
|---|---|
| Message chứa MULTI intent (vd "anh nhậu say + ok làm tiếp") | Apply INTENT_PRIORITY → `tam_su` thắng `affirmative` |
| Message rỗng / chỉ emoji / chỉ icon | intent = `normal`, slot extractor trả empty → trigger RETRY (nếu REQUIRED) |
| Message > 500 chars (tâm sự dài) | Detect `tam_su` + engage 1 nhịp (không full extract) |
| Message tiếng Anh thuần | intent detect bình thường, bot phản hồi tiếng Việt |
| Voice STT lệch (vd "sinh pha" thay "Xingfa") | Layer 2 LLM tự correct trong context, KHÔNG flag là garbage |

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine PHẢI cover MỌI message có shape tương tự.**

**Pattern test:** Engine detect ĐÚNG intent dù dealer dùng từ ngữ /
chính tả / tone khác nhau. Marker là DANH SÁCH MỞ, không exhaustive.

**Case ví dụ:**

```
Stage=ASKING, current_slot=1.3

Dealer: "đéo cho"            → intent=refusal       (marker § 2.4)
Dealer: "không tiện đâu em"  → intent=refusal       (marker § 2.4)
Dealer: "anh không nhớ số"   → intent=khong_biet    (marker § 2.5)
Dealer: "lừa đảo à?"          → intent=defensive    (marker § 2.6)
Dealer: "tổ chức gì em?"      → intent=defensive    (marker § 2.6)
Dealer: "0912345678"          → intent=normal       (extract phone)
Dealer: "hôm qua anh nhậu     → intent=tam_su       (marker § 2.7)
        say quá"

Stage=CONFIRMING:
Dealer: "ok chuẩn rồi"        → intent=affirmative  → CONFIRMED
Dealer: "sửa địa chỉ thành    → intent=edit + edit_field=address
        Hà Nội"
```

**Tổng quát hóa:**
- Marker là HINT, không exhaustive — Layer 2 LLM fallback bắt case chưa cover
- Priority: defensive > tâm_sự > refusal > không_biết > edit > affirmative > normal
- Voice STT lệch brand → Layer 2 tự correct trong context (refer File 2B)

✅ **PASS:**
- 7 intent classify đúng với marker list trong File 1A § 2
- Multi-intent → áp priority order
- Empty/garbage → intent=normal (không crash)
- Voice STT brand lệch → Layer 2 detect + correct

❌ **FAIL:**
- "đéo cho" → intent=normal (bỏ qua refusal) → bot vẫn ép hỏi
- "lừa đảo à?" → intent=normal → bot bơ defensive, advance slot
- "ok" trong stage CONFIRMING bị detect là normal → không transition DONE
- Engine call LLM cho mọi message (waste cost) — phải cache

### Constraints (KHÔNG được vi phạm)

- Layer 1 (regex) PHẢI chạy TRƯỚC Layer 2 (LLM) — performance
- Cache LLM classify result trong session
- intent=defensive HOẶC tam_su → KHÔNG advance slot, set PAUSE
- intent=edit CHỈ valid trong stage=CONFIRMING — ngoài stage này → fallback normal

### Pointer implementation

→ `app/core/intent.py` § `detect_intent` (Layer 1 + Layer 2)
→ `app/core/regex_markers.py` § marker lists
→ `app/llm/intent_classifier.py` § Layer 2 prompt + cache

### Cross-ref

- ⬆ CORE § G.5 (engage)
- ⬅ File 1A § 2.3-2.7 (marker lists)
- ➡ F2A.4 (smart advance dùng intent làm input)
- ➡ File 2B § LLM intent classifier prompt
- ➡ File 1C (escalation khi defensive lặp >2 lần)

---

## F2A.5 — Slot priority + Required/Optional retry

**Tham chiếu CORE:** § G.3 (mapping slot → tiêu chí), § G.4 (Required/Optional)
**Tham chiếu File 1A:** § 1.4 (Required/Optional quy ước), § 4 (slot order)

### Yêu cầu

Trật tự ưu tiên 17 slot + logic retry theo loại slot.

### SLOT_PRIORITY_ORDER (17 slot)

```python
SLOT_PRIORITY_ORDER = [
    # CHỦ ĐỀ 1 — Danh thiếp (REQUIRED 1.1, 1.2, 1.3)
    "1.1",  # tên người + cửa hàng        REQUIRED
    "1.2",  # địa chỉ + bán kính (raw C6)  REQUIRED (chỉ địa chỉ)
    "1.3",  # SĐT / Zalo                   REQUIRED

    # CHỦ ĐỀ 2 — Công việc + Kênh (REQUIRED 2.1, 2.2)
    "2.1",  # danh mục + sản phẩm mạnh     REQUIRED (chỉ main_product)
    "2.2",  # mô hình KD                    REQUIRED
    "2.3",  # đội thợ + ổn định            OPTIONAL
    "2.4",  # hãng nhập + backup + segment OPTIONAL
    "2.5",  # kênh khách liên hệ           OPTIONAL
    "2.6",  # FB + network thợ (C9)        OPTIONAL

    # CHỦ ĐỀ 3 — Khách cũ + Vướng (all OPTIONAL)
    "3.1",  # % khách cũ giới thiệu        OPTIONAL
    "3.2",  # cách lưu danh sách khách     OPTIONAL
    "3.3",  # OPEN — vướng mắc + pain      OPTIONAL (mining heavy)
    "3.4",  # cọc + công nợ                OPTIONAL
    "3.5",  # bảo hành — ai chịu (C4)      OPTIONAL

    # CHỦ ĐỀ 4 — Bộ thương hiệu
    "4.0",  # consent BỘ THƯƠNG HIỆU       REQUIRED
    "4.1",  # logo (em chọn)                OPTIONAL
    "4.2",  # màu + phong thủy             OPTIONAL
]

REQUIRED_SLOTS = ["1.1", "1.2", "1.3", "2.1", "2.2", "4.0"]
```

### Retry algorithm (sync F2A.4 step 2.7 + 1A § 1.6)

```
Function: handle_slot_response(slot_id, intent, extracted)
Output: action ∈ {ADVANCE, RETRY, PARTIAL_RETRY, DEFER, SKIP, PAUSE}

is_required = slot_id in REQUIRED_SLOTS

# Case 1: Có data hợp lệ → ADVANCE
if intent == "affirmative" or extracted is not None:
    if validate(extracted) PASS:
        save(extracted)
        reset consecutive_attempts[slot_id] = 0
        return ADVANCE
    else:
        # validate fail (vd phone không digits)
        if is_required:
            consecutive_attempts[slot_id] += 1
            total_attempts[slot_id] += 1
            # Check rule "không quá 2 liên tiếp"
            if consecutive_attempts[slot_id] >= MAX_RETRY_CONSECUTIVE (=2)
               and total_attempts[slot_id] < MAX_RETRY_TOTAL (=3):
                mark deferred + consecutive=0
                return DEFER
            elif total_attempts[slot_id] >= MAX_RETRY_TOTAL (=3):
                flag `required_missing`
                return SKIP
            else:
                return RETRY  # lần đầu, hỏi lại tone giải thích
        else:
            save(null) + flag dealer_declined
            return SKIP

if intent == "khong_biet":
    if is_required:
        slot_attempts[slot_id] += 1
        if slot_attempts[slot_id] >= MAX_RETRY_REQUIRED:
            save(null) + flag required_missing
            return SKIP
        return RETRY  # tone giảm dần theo lượt (xem File 1A § retry table)
    else:
        save(null) + flag dealer_declined
        return SKIP  # SKIP NGAY

if intent == "refusal":
    # Same as khong_biet (xử identical)
    if is_required:
        slot_attempts[slot_id] += 1
        if slot_attempts[slot_id] >= MAX_RETRY_REQUIRED:
            return SKIP + flag required_missing
        return RETRY
    else:
        return SKIP + flag dealer_declined

if intent in ("defensive", "tam_su"):
    return PAUSE  # giữ slot_id, KHÔNG retry count
```

### Tone giảm dần — retry REQUIRED (3 lượt)

| Lượt | Tone | Strategy |
|---|---|---|
| 1 (lần đầu hỏi) | **Bình thường** | Câu hỏi chuẩn (1 trong 3 biến thể File 1A § 4) |
| 2 (sau RETRY 1) | **Nhẹ + giải thích lý do** | Thêm "em xin vì..." + cam kết bảo mật |
| 3 (sau RETRY 2) | **Tha thiết + offer fallback** | Đưa option dễ hơn (vd "Zalo phụ cũng được", "tỉnh+quận thôi cũng được") |
| Sau lượt 3 | **SKIP + flag** | KHÔNG hỏi lại trong session. Admin review thủ công. |

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `MAX_RETRY_REQUIRED` | 3 | Sau N retry slot REQUIRED → SKIP |
| `MAX_RETRY_OPTIONAL` | 0 | OPTIONAL không retry |
| `SKIP_FLAG_REQUIRED` | `"required_missing"` | Flag khi REQUIRED bị skip sau retry max |
| `SKIP_FLAG_OPTIONAL` | `"dealer_declined"` | Flag khi OPTIONAL bị skip |
| `VALIDATE_FORMAT_FAIL_RETRY` | True | Validate fail (phone không digits) cũng count vào retry |

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine PHẢI cover MỌI shape tương tự.**

**Pattern test:** REQUIRED retry max 3 lần. OPTIONAL skip ngay. Order
slot không đổi (1.1 → 4.2). Sau retry max → SKIP + flag warning.

**Case ví dụ:**

```
Slot 1.3 (REQUIRED — SĐT):

Turn N:    Bot hỏi 1.3 (lượt 1, tone bình thường)
Dealer:    "không cho"
           → intent=refusal, slot REQUIRED
           → slot_attempts[1.3] = 1, RETRY lượt 2 (nhẹ + giải thích)

Turn N+1:  Bot retry với tone "em xin chỉ để team người thật liên hệ"
Dealer:    "thôi"
           → slot_attempts[1.3] = 2, RETRY lượt 3 (offer Zalo phụ)

Turn N+2:  Bot retry với offer fallback
Dealer:    "không"
           → slot_attempts[1.3] = 3 >= MAX_RETRY_REQUIRED
           → SKIP + flag required_missing
           → ADVANCE qua slot 2.1
           → admin sẽ review thủ công

---

Slot 2.3 (OPTIONAL — đội thợ):

Turn N:    Bot hỏi 2.3
Dealer:    "không biết"
           → intent=khong_biet, slot OPTIONAL
           → SKIP NGAY (không retry)
           → flag dealer_declined
           → ADVANCE qua slot 2.4

Turn N+5 (slot 4.2):  KHÔNG bao giờ quay lại hỏi 2.3 nữa.
```

**Tổng quát hóa:**
- REQUIRED retry max = 3, tone giảm dần lượt 2 + 3
- OPTIONAL không retry → SKIP NGAY khi `khong_biet` / `refusal`
- Validate format fail (vd phone "abc") count vào retry (vì coi như chưa cho data hợp lệ)
- Order slot fixed — không jump, không back

✅ **PASS:**
- REQUIRED 1.3: retry 3 lần → SKIP + flag `required_missing`
- OPTIONAL 2.3: "không biết" → SKIP ngay 1 lần, flag `dealer_declined`
- Slot bị SKIP không xuất hiện lại trong cùng session

❌ **FAIL:**
- REQUIRED retry > 3 lần → loop
- REQUIRED skip ngay lượt 1 (không cho retry)
- OPTIONAL retry vô hạn → loop
- Slot 2.3 đã skip mà turn sau lại hỏi → tracking sai
- Engine bỏ qua slot 2.5 (skip mà chưa có response) — phải hỏi đủ 17

### Constraints (KHÔNG được vi phạm)

- Order slot fixed theo SLOT_PRIORITY_ORDER, KHÔNG jump
- REQUIRED retry tối đa MAX_RETRY_REQUIRED (=3)
- OPTIONAL MAX_RETRY_OPTIONAL = 0
- Validate format fail count vào retry
- skipped_slots không quay lại trong cùng session

### Pointer implementation

→ `app/core/state_machine.py` § `handle_slot_response`
→ `app/core/v7_turns.py` § `SLOTS` constant với required/optional flag

### Cross-ref

- ⬆ CORE § G.3, § G.4
- ⬅ File 1A § 1.4, § 4 (mỗi slot có retry table)
- ➡ F2A.4 (smart advance dùng action output)
- ➡ F2A.7 (sanity check trước CONFIRMED save)

---

## F2A.6 — Dealer type detection (Lửa / Khoe / Lo / Bận)

**Tham chiếu CORE:** § B.3 (4 nhóm dealer), § D (tâm lý)
**Tham chiếu File 1A:** § 1.3 (tone), § 4 (ack per nhóm)
**Tham chiếu File 1B:** tone library 4 nhóm

### Yêu cầu

Bot detect 1 trong 4 nhóm dealer để chọn TONE và ACK phù hợp:

| Nhóm | Đặc điểm | Tone ack | Marker hint |
|---|---|---|---|
| **Lửa Lò** | Cộc, chửi bậy, đi thẳng | Ngắn cực, không nịnh | Caps lock, "đm", "vl", cụt câu, không emoji |
| **Khoe** | Kể thành tích, kể đội, kể số má | Khen có vế cụ thể, không sáo | Số liệu nhiều, "anh có", "anh đứng đầu", emoji nhiều |
| **Lo** | Nghi ngờ, hỏi ngược, sợ lừa | Trấn an + cam kết bảo mật rõ | "có an toàn không", "lừa đảo", "phí gì" |
| **Bận** | 1-2 chữ trả lời, không kể thêm | Cộc đối xứng, đi thẳng | Trả lời ≤5 chữ, không follow-up |
| **unknown** | Chưa đủ data để detect | Default = Bận | (chưa detect 3 turn đầu) |

### Algorithm

```
Function: detect_dealer_type(session)
Output: dealer_type ∈ enum

# Quy ước thời điểm detect
DETECT_AT_TURNS = [3, 8, 13]  # detect lần đầu turn 3, re-detect 8 + 13

current_turn = session.turn_count
if current_turn not in DETECT_AT_TURNS:
    return session.detected_dealer_type  # giữ nguyên

# Tại turn detect:
# 1. Gom toàn bộ user messages từ turn 1 → turn hiện tại
# 2. Tính 4 score (0-10) cho 4 nhóm dựa trên signal:

score_lua_lo = count(caps + chửi + cộc câu) × weight_lua
score_khoe   = count(số liệu + "anh có/anh là" + emoji) × weight_khoe
score_lo     = count(defensive marker + "phí" + "an toàn") × weight_lo
score_ban    = count(message ngắn ≤5 chữ) × weight_ban

# 3. Chọn max score (nếu tie hoặc tất cả ≤ MIN_SCORE → "unknown" → default "ban")
top_score = max(scores)
if top_score < MIN_CONFIDENCE_SCORE:
    return "ban"  # default conservative

return argmax(scores)
```

### Re-detect rule

```
- Turn 3: detect lần đầu (sau slot 1.1, 1.2, 1.3 done)
- Turn 8: re-detect (giữa flow, sau Chủ đề 2)
- Turn 13: re-detect cuối (trước Chủ đề 4)

- Nếu re-detect khác lần trước:
  • Confidence cao (top_score >= HIGH_THRESH) → DỜI sang nhóm mới
  • Confidence thấp → GIỮ nhóm cũ
- Log tracking: dealer_type_history = [(turn, type), ...]
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `DETECT_AT_TURNS` | `[3, 8, 13]` | Turn detect/re-detect |
| `MIN_CONFIDENCE_SCORE` | 2.0 | Dưới → fallback "ban" |
| `HIGH_THRESH_SWITCH` | 5.0 | Re-detect chỉ dời nếu confidence cao |
| `DEFAULT_TYPE` | `"ban"` | Khi unknown / chưa detect |

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine cover MỌI dealer có hành vi tương tự.**

**Pattern test:** Bot detect dealer type theo signal toàn cục (gom
nhiều turn), không over-fit 1 câu. Default "ban" khi chưa rõ.

**Case ví dụ:**

```
Turn 1-3 (dealer responses):
Turn 1: "Tùng. Nhôm Kính Thanh Tùng"
Turn 2: "Cao Bằng"
Turn 3: "0912xxx"

→ Turn 3 detect:
   - score_ban = 3 × 1.0 = 3.0 (message ngắn liên tục)
   - score_khoe = 0
   - score_lua = 0 (không chửi, không caps)
   - score_lo = 0
   → dealer_type = "ban"

---

Turn 1-3 (dealer khác):
Turn 1: "ANH TÊN HÙNG ĐM EM HỎI NHIỀU THẾ"
Turn 2: "BẮC NINH RỒI"
Turn 3: "0987 KO BIẾT ZALO"

→ Turn 3 detect:
   - score_lua_lo = 2.5 × 3 + 1.0 (caps + chửi + cộc) = 8.5
   - score_ban = 1.0
   → dealer_type = "lua_lo"
```

**Tổng quát hóa:**
- Tích lũy signal qua nhiều turn → detect tại turn 3, 8, 13
- 1 caps không đủ → cần pattern (caps + chửi + cộc)
- Khoe = số liệu + "anh có" + emoji + kể dài
- Lo = defensive marker xuất hiện ≥1 lần trong 3 turn đầu

✅ **PASS:**
- Detect đúng dealer type theo pattern toàn cục
- Re-detect turn 8/13 chỉ dời khi confidence cao
- Default "ban" khi chưa đủ data

❌ **FAIL:**
- Detect "lửa lò" chỉ vì 1 emoji "😡"
- Detect "khoe" chỉ vì dealer nói số (vd "60% khách cũ" — đây là answer slot 3.1, không phải khoe)
- Switch type mỗi turn (instable detection)
- Force detect ở turn 1 (không đủ data)

### Constraints (KHÔNG được vi phạm)

- DETECT_AT_TURNS cố định — không detect mỗi turn
- Re-detect chỉ dời khi confidence cao
- Lưu `dealer_type_history` để debug
- Default "ban" — tone conservative, không nịnh

### Pointer implementation

→ `app/core/dealer_type.py` § `detect_dealer_type`
→ `app/core/session.py` § `Session.detected_dealer_type` + `dealer_type_history`

### Cross-ref

- ⬆ CORE § B.3, § D
- ⬅ File 1A § 1.3, § 4 (ack 4 nhóm)
- ➡ File 1B (tone library — bot chọn ack theo type)
- ➡ File 2B § LLM ack generator prompt (input dealer_type)

---

## F2A.7 — Sanity check before CONFIRMED save

**Tham chiếu CORE:** § J.4 (luật khóa save)
**Tham chiếu File 1A:** § 6 (Confirmation Card)

### Yêu cầu

Trước khi `confirmation_status` chuyển từ `PENDING` sang `CONFIRMED`,
engine PHẢI chạy 5-point checklist. Nếu fail → KHÔNG save CONFIRMED,
flag warning + admin review.

### 5-point checklist

```
Function: sanity_check(profile)
Output: (ok ∈ bool, failed_checks ∈ list)

failed = []

# Check 1: 6 REQUIRED slot không null hoặc có flag required_missing
# Mapping slot → field bắt buộc:
SLOT_TO_REQUIRED_FIELDS = {
    "1.1": ["owner_name", "dealer_name"],   # 2 field
    "1.2": ["address"],                     # 1 field (bán kính là OPTIONAL)
    "1.3": ["phone_or_zalo"],
    "2.1": ["main_product"],                # category_stack là OPTIONAL
    "2.2": ["business_model_signal"],
    "4.0": ["brandkit_consent"],
}
for slot in REQUIRED_SLOTS:
    required_fields = SLOT_TO_REQUIRED_FIELDS[slot]
    for field in required_fields:
        if profile.get(field) is None and "required_missing" not in flags:
            failed.append(f"REQUIRED slot {slot} field {field} chưa thu mà không có flag")

# Check 2: Phone format valid (digits-only, 9-11 chữ số)
phone = profile.get("phone_or_zalo")
if phone is not None and not phone.isdigit():
    failed.append("phone format invalid")
if phone is not None and len(phone) not in range(9, 12):
    failed.append("phone length invalid")

# Check 3: Address không rỗng / không chỉ chứa stopword
addr = profile.get("address")
if addr is not None:
    if len(addr.strip()) < 3:
        failed.append("address quá ngắn")
    if any(blacklist in addr.lower() for blacklist in ADDRESS_BLACKLIST):
        failed.append(f"address chứa blacklist (chính trị/tôn giáo/vùng miền)")

# Check 4: brandkit_consent rõ ràng (yes/no, không null trừ flag)
if profile.get("brandkit_consent") is None and "consent_unclear" not in flags:
    failed.append("brandkit_consent null mà không có flag consent_unclear")

# Check 5: Không có Scope 4 field trong profile (vd c_score, tier, dealer_id)
for forbidden in SCOPE_4_FIELDS:
    if forbidden in profile and profile[forbidden] is not None:
        failed.append(f"Scope 4 field '{forbidden}' xuất hiện trong dealer_profile_raw")

return (len(failed) == 0, failed)
```

### ADDRESS_BLACKLIST

> **Hierarchy note:** CORE chỉ định nguyên tắc cao "không lưu data nhạy
> cảm" (§ E.5, § J.4). Detail blacklist cụ thể (chính trị/tôn giáo/vùng
> miền) là spec engine — sống ở rule này, không ở CORE.

```python
ADDRESS_BLACKLIST = [
    # Chính trị
    "bác hồ", "tô lâm", "trọng tổng", "nguyễn xuân phúc",
    "ba đình lăng", "lăng bác",
    # Tôn giáo
    "đức phật", "allah", "chúa trời", "thánh tôn",
    # Vùng miền (slur)
    "bắc kỳ", "nam kỳ", "trung kỳ",
]
```

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `REQUIRED_SLOTS` | (6 slot) | Slot phải có data |
| `PHONE_LEN_RANGE` | `(9, 12)` | Phone digits valid range |
| `ADDRESS_MIN_LEN` | 3 | Address tối thiểu 3 char |
| `SCOPE_4_FIELDS` | (xem F2A.3) | Field forbidden trong profile |

### Xử lý fail

```
if not ok:
    log_warning("Sanity check failed", failed_checks)
    flag += "sanity_check_failed"
    confirmation_status = "PENDING"  # KHÔNG cho CONFIRMED
    review_status = "UNDER_REVIEW"   # bắt admin review
    notify_admin(profile.session_id, failed_checks)
    # KHÔNG block dealer — bot vẫn render Closing polite
    # Admin sẽ liên hệ dealer thủ công sau
```

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine cover MỌI profile có shape tương tự.**

**Pattern test:** Engine REJECT save CONFIRMED khi 1 trong 5 check fail.
Profile pass tất 5 check → CONFIRMED + APPROVED (review_status).

**Case ví dụ:**

```
Profile A (đủ 6 REQUIRED, phone valid, address OK):
  → Check 1-5: PASS
  → confirmation_status = CONFIRMED
  → review_status = APPROVED

Profile B (phone = "abc123def"):
  → Check 2: FAIL (phone không digits)
  → confirmation_status = PENDING
  → flag += "sanity_check_failed"
  → admin review

Profile C (address = "Số 1 Lăng Bác Hà Nội"):
  → Check 3: FAIL (address blacklist match "lăng bác")
  → flag += "sanity_check_failed"
  → admin review

Profile D (c_score = 75 lọt vào profile):
  → Check 5: FAIL (Scope 4 field xuất hiện)
  → flag += "sanity_check_failed"
  → REJECT save + warning lớn (lỗi engine, không phải dealer)
```

**Tổng quát hóa:**
- Sanity check là LINE BUỘC trước CONFIRMED — không bypass được
- Fail → flag + admin review, KHÔNG block dealer flow
- Scope 4 leak (c_score, tier xuất hiện) = LỖI ENGINE → log error cao
- Address blacklist = LỖI DEALER intent → flag escalation

✅ **PASS:**
- Profile đủ 6 REQUIRED → CONFIRMED OK
- Phone "0912345678" valid → PASS check 2
- Address "Cao Bằng, Trùng Khánh" → PASS check 3
- Không có c_score/tier trong profile → PASS check 5

❌ **FAIL:**
- Phone "0912 abc" save CONFIRMED → vi phạm
- Address "Phố Bác Hồ" save CONFIRMED → vi phạm (chính trị)
- c_score lọt vào dealer_profile_raw → schema vỡ
- Engine block dealer flow vì sanity fail (phải vẫn render Closing polite)

### Constraints (KHÔNG được vi phạm)

- Sanity check LUÔN chạy trước CONFIRMED save
- Fail → KHÔNG block dealer, vẫn Closing polite
- Scope 4 leak = LỖI ENGINE, log ERROR level
- Address blacklist = flag escalation (xem File 1C)

### Pointer implementation

→ `app/core/sanity.py` § `sanity_check(profile)`
→ `app/core/validators.py` § phone/address validators
→ `app/storage/sqlite_store.py` § INSERT chỉ khi sanity PASS

### Cross-ref

- ⬆ CORE § J.4 (luật khóa save), § E.5 (consent + privacy — nguyên tắc gốc cho blacklist)
- ⬅ File 1A § 6 (card render)
- ➡ F2A.3 (schema 4 scope — định nghĩa Scope 4 fields)
- ➡ File 1C (escalation khi address blacklist match)
- ➡ File 2C (admin notification + review queue)

---

## F2A.8 — Greeting + Closing engine

**Tham chiếu CORE:** § A.3 (promise), § H.3 (closing structure)
**Tham chiếu File 1A:** § 3 (Greeting templates), § 7 (Closing templates)

### Yêu cầu

Engine chọn biến thể Greeting + Closing tự động theo session, fill
placeholder, gen local hook qua LLM (Phase 2) — KHÔNG lookup table cứng.

### Algorithm — Greeting

```
Function: render_greeting(session)
Output: greeting_text

# 1. Chọn biến thể (3 mẫu trong File 1A § 3.2)
variant_id = hash(session.session_id + "greeting") % 3
template = GREETING_VARIANTS[variant_id]

# 2. Fill placeholder (chỉ có sẵn ở greeting: KHÔNG có dealer data nào)
# → KHÔNG có placeholder dealer-specific ở Greeting

# 3. Return text
return template
```

### Algorithm — Closing

```
Function: render_closing(session)
Output: closing_text

profile = session.profile
brandkit_consent = profile.get("brandkit_consent")

# 1. Chọn closing path
if brandkit_consent == "no":
    template = CLOSING_NO_BRANDKIT  # File 1A § 7.5
else:
    variant_id = hash(session.session_id + "closing") % 3
    template = CLOSING_VARIANTS[variant_id]  # 3 mẫu File 1A § 7.3

# 2. Gen local hook qua LLM (Phase 2). Phase 1: luôn rỗng.
province = profile.get("province")
local_hook = gen_local_hook_llm(province, session.detected_dealer_type) \
             if PHASE >= 2 else ""

# Yêu cầu LLM_FAST trả 1-2 câu ≤ 30 từ, tự nhiên, có thể trả rỗng.
# CẤM hard-code mapping tỉnh → đặc sản. Cache key:
# local_hook:{province}:{dealer_type} (refer F2C.5).

# 3. Fill placeholder
filled = template.format(
    dealer_name=profile.get("dealer_name", "cửa hàng mình"),
    local_hook=local_hook,  # có thể rỗng — template thiết kế để chấp nhận
)

return filled
```

### Nguyên tắc "không khoá case" (refer File 1A § 7.4)

**Refactor 2026-05-18:** Spec gốc dùng `PROVINCE_SPECIALTY_TABLE` map
cứng 50 tỉnh → đặc sản (Cao Bằng → "vịt quay 7 vị", Hà Nội → "phở"...).
Vi phạm nguyên tắc "không khoá case, chỉ khoá luật" — ép bot phản xạ
máy móc, mọi dealer cùng tỉnh nghe cùng 1 câu.

**Quy ước mới:**
- KHÔNG có `PROVINCE_SPECIALTY_TABLE` trong code/spec.
- KHÔNG có `data/province_specialty.json`.
- Local hook (nếu cần) → LLM gen với context (tỉnh + tone + history),
  cache 7 ngày trong Redis (refer F2C.5).
- LLM được phép trả rỗng → template render bỏ qua placeholder.
- Phase 1: local_hook luôn rỗng.

### Tham số config

| Param | Default | Ý nghĩa |
|---|---|---|
| `GREETING_VARIANTS_COUNT` | 3 | Số biến thể Greeting (refer File 1A) |
| `CLOSING_VARIANTS_COUNT` | 3 | Số biến thể Closing |
| `VARIANT_HASH_SEED` | `session_id + tag` | Hash để chọn variant consistent trong session |
| `LOCAL_HOOK_LLM_MAX_TOKENS` | 60 | Phase 2: max output tokens cho local hook gen |
| `LOCAL_HOOK_CACHE_TTL_S` | 604800 | Phase 2: cache 7d (refer F2C.5) |

### Acceptance test

> ⚠️ **VÍ DỤ MINH HỌA — engine cover MỌI session.**

**Pattern test:** Engine render Greeting + Closing với biến thể
consistent trong 1 session. Local hook gen qua LLM (Phase 2) hoặc rỗng
(Phase 1) — KHÔNG có vocab đặc sản hard-code.

**Case ví dụ:**

```
Session A (session_id="abc123", province="Cao Bằng"):
  - hash("abc123" + "greeting") % 3 = 1  → variant 1
  - Greeting render đúng biến thể 1 (File 1A § 3.2)
  - hash("abc123" + "closing")  % 3 = 0  → variant 0
  - Phase 1: local_hook = "" → template render bỏ qua
  - Phase 2: LLM gen hook tự do (mỗi session khác nhau)

Session B (province="X-tỉnh-bất-kỳ"):
  - LLM phải tự xử (không phụ thuộc lookup table)

Session C (address=null):
  - local_hook = "" — template render bỏ qua

Session D (brandkit_consent="no"):
  - dùng CLOSING_NO_BRANDKIT (closing rút gọn 2 phần)
  - Không nhắc "tặng bộ thương hiệu"
```

**Tổng quát hóa:**
- 3 biến thể Greeting/Closing pick by hash (consistent trong session)
- Local hook gen qua LLM hoặc empty — KHÔNG lookup table cứng
- consent=no → closing path khác (KHÔNG nhắc tặng bộ TH)

✅ **PASS:**
- Hash-based variant pick — cùng session → cùng biến thể
- consent=no → closing rút gọn
- Closing render KHÔNG chứa hard-code "phở", "vịt quay", "mì Quảng"...
- LLM gen fail/timeout → fallback empty hook, không crash

❌ **FAIL:**
- Random variant mỗi lần render (mất consistency)
- consent=no mà closing vẫn nhắc "tặng bộ thương hiệu" → ép dealer
- Closing có mapping cứng province → đặc sản → vi phạm "không khoá case"
- Greeting fill placeholder dealer data (chưa có) → KeyError

### Constraints (KHÔNG được vi phạm)

- Variant pick = hash(session_id + tag) % N — deterministic per session
- consent=no → closing path khác, KHÔNG nhắc bộ thương hiệu
- Greeting KHÔNG fill dealer placeholder (chưa có data)
- KHÔNG hardcode 1 biến thể duy nhất — phải rotate
- **KHÔNG hardcode mapping tỉnh → đặc sản (vi phạm "không khoá case")**

### Pointer implementation

→ `app/core/greeting.py` § `render_greeting`
→ `app/core/closing.py` § `render_closing`
→ `app/llm/local_hook.py` (Phase 2: LLM gen local hook — KHÔNG lookup table)
→ `app/llm/khoe_hook.py` (LLM gen hook cho dealer Khoe)

### Cross-ref

- ⬆ CORE § A.3, § H.3
- ⬅ File 1A § 3, § 7
- ➡ F2A.6 (dealer_type input cho khoe_hook)
- ➡ File 2B § LLM gen local_hook prompt (Phase 2)
- ➡ File 2B § LLM gen khoe_hook prompt

---

## Cross-ref

| Rule File 2A | Cross-ref CORE | Cross-ref File 1A | Cross-ref File khác |
|---|---|---|---|
| F2A.1 Stages | § J.1 (workflow), § G (khung chạy 4 stage) | — | File 2C § session |
| F2A.2 Intent detection | § G.5 | § 2.6, 2.7 (markers) | File 2B § LLM classify |
| F2A.3 Schema 4 scope | § H.1 | § 4 (slot fill mapping) | File 2B § extractor schema |
| F2A.4 Smart advance | § G.4 | § 1.4, § 4 | F2A.5, F2A.6 |
| F2A.5 Slot priority | § G.3 | § 4 (order 1.1→4.2) | F2A.4 |
| F2A.6 Dealer type detection | § B.3 | § 1.3 | File 1B (tone library) |
| F2A.7 Sanity check | § J.4 | § 6 (card) | F2A.3 |
| F2A.8 Greeting/Closing engine | § A.3, § H.3 | § 3, § 7 | — |
