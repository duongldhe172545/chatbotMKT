# GLOSSARY — Thuật ngữ Em Linh MKT

> **Mục đích:** Định nghĩa thuật ngữ dùng chung trong CORE + 6 file
> kịch bản/luật. **Bắt buộc đọc trước** khi sửa file khác để không
> hiểu nhầm.
>
> **Tại sao cần:** Trong 6 file spec dùng các từ gần giống nhau
> ("slot vs turn vs field", "scope vs stage", "intent vs flag")
> rất nhiều lần. Không định nghĩa rõ → Duong + Claude hiểu khác nhau
> → bug khi code Phase 1.

---

## VERSION

| Ngày | Version | Note |
|---|---|---|
| 2026-05-14 | v1.0 | First |
| 2026-05-15 | v1.1 | Thêm `Session`/`Greeting`/`Closing`/`Card`/`History` (mục § 1). Thêm `LLM_FAST`/`LLM_QUALITY` tier abstraction (mục § 5). Fix Scope 4 vendor reference + Redis → infra cache. Clarify scope cấm "Marketing" (chỉ dialog). |
| 2026-05-15 | v1.2 | Spec consistency batch: § 1 đổi count "11 OPTIONAL" → "10 OPTIONAL + 1 THÔNG BÁO" (slot 4.1 không fill field — sync CORE/1A). § 4 mở rộng bảng flag 8 → **15 flag** chia 4 nhóm (sync 2A F2A.3 enum + 2C F2C.8 trigger). § 7 tách entry KE_HOACH_REFACTOR thành 4 pointer chi tiết. |
| 2026-05-15 | v1.3 | Add action `PARTIAL_RETRY` vào bảng `Action` — slot multi-field, dealer fill 1 phần. KHÔNG count `slot_attempts`. Sync với 2A F2A.4 step 2.6 + 1A § 1.5 + § 4 slot 1.1 PARTIAL handler. |
| 2026-05-15 | v1.4 | Spec consistency BATCH 4: (1) § Action mở rộng 5 → **6 action** (thêm `DEFER` — slot REQUIRED tạm gác sau 2 lần liên tiếp chưa fill, engine re-check sau N slot). Đổi columns sang `consecutive_attempts` + `total_attempts` cho rõ. Add why box "dealer turn đầu test/nghịch". (2) § Session lifecycle "TIMEOUT 30 phút" → "**1 giờ**" (sync 2C F2C.1 + 2A F2A.4 config `SESSION_TIMEOUT`). (3) § Cache TTL thêm row "System prompt build per slot×dealer_type — 1h in-memory" (sync 2C F2C.5). |

---

## 1. Thuật ngữ về FLOW (luồng hội thoại)

### `Stage` (Giai đoạn)

4 giai đoạn lớn của 1 session, **forward-only** (không cho back):

| Stage | Mô tả | Bot làm gì |
|---|---|---|
| `GREETING` | Đầu session | Render lời chào + xin phép trò chuyện |
| `ASKING` | Đang thu thập | Hỏi tuần tự 17 slot |
| `CONFIRMING` | Đã xong, chờ duyệt | Render card 5 phần, dealer xác nhận/sửa |
| `DONE` | Đóng session | Render closing + dealer notify Zalo |

→ Định nghĩa chi tiết: File 2A § F2A.1

---

### `Slot` (Ô thông tin cần thu)

**1 đơn vị thông tin** Em Linh hỏi đại lý. Có **17 slot**, đánh số theo
chủ đề:

- **Chủ đề 1 — Danh thiếp:** 1.1, 1.2, 1.3 (3 slot)
- **Chủ đề 2 — Công việc + Kênh:** 2.1, 2.2, 2.3, 2.4, 2.5, 2.6 (6 slot)
- **Chủ đề 3 — Khách cũ + Vướng:** 3.1, 3.2, 3.3, 3.4, 3.5 (5 slot, slot 3.5 MỚI)
- **Chủ đề 4 — Bộ thương hiệu:** 4.0, 4.1, 4.2 (3 slot)

→ Mỗi slot có: câu hỏi (3 biến thể) + ack template per nhóm dealer +
retry tone + handler.

→ Định nghĩa chi tiết: File 1A § 4 + File 2A § F2A.5

**KHÁC `Turn` thế nào?**
- Slot = ô thông tin (vd "phone")
- Turn = 1 message trao đổi (bot hỏi → dealer trả lời = 1 turn)
- 1 slot có thể cần 2-3 turn (vd dealer trả lời mơ hồ → bot retry → dealer trả lời lại)

---

### `Required` vs `Optional`

| Loại | Slot | Retry behavior khi dealer "không biết"/"không cho" |
|---|---|---|
| **REQUIRED** (6 slot) | 1.1, 1.2, 1.3, 2.1, 2.2, 4.0 | Retry **3 lần** tone giảm dần → SKIP + flag `required_missing` |
| **OPTIONAL** (10 slot) | 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 4.2 | **SKIP NGAY** (không retry) + flag `dealer_declined` |
| **THÔNG BÁO** (1 slot) | 4.1 | KHÔNG fill field, KHÔNG có extractor. Bot thông báo "logo em chọn theo ngành" — dealer ack "vâng/ok" là pass, đi tiếp slot 4.2 |

**Tổng = 6 + 10 + 1 = 17 slot.**

→ Định nghĩa chi tiết: File 1A § 1.4 + File 2A § F2A.5

---

### `Action` (Hành động state machine)

Sau mỗi message dealer, engine quyết 1 trong **6 action**:

| Action | Khi nào | `consecutive_attempts` | `total_attempts` |
|---|---|---|---|
| `ADVANCE` | Slot vừa fill HIGH (đủ field bắt buộc trong slot) → chuyển slot kế | reset 0 | — |
| `RETRY` | Slot REQUIRED `filled=[]` (dealer KHÔNG cho gì cả), consecutive < 2 và total < 3 → hỏi lại tone giảm dần | +1 | +1 |
| `PARTIAL_RETRY` | Slot multi-field, dealer fill 1 phần (`filled≠[]` và `missing≠[]`) → ack + hỏi field còn thiếu | **0** (không đếm) | **0** |
| `DEFER` | Slot REQUIRED hỏi 2 lần liên tiếp chưa được + total < 3 → tạm gác, đi slot khác. Engine re-check sau N slot. | reset 0 | +1 (giữ) |
| `SKIP` | Slot OPTIONAL "không biết" / REQUIRED đã hết total (3) → bỏ slot, advance | — | — |
| `PAUSE` | Dealer rẽ defensive/tâm sự → tạm dừng flow xử intent trước | — | — |

> **Why DEFER:** dealer turn đầu hay test/nghịch bot, không phải refusal thật. Hỏi
> 3 lần liên tiếp dồn dập làm dealer bực hoặc drop session. DEFER cho phép
> phân bố 3 lần retry thông minh: 2 liên tiếp + 1 sau pause vài slot. Refer
> File 1A § 1.6 + File 2A § F2A.4 step 2.7-2.8.

→ Định nghĩa chi tiết: File 2A § F2A.4 (step 2.6 PARTIAL, 2.7 DEFER, 2.8 re-check) + File 1A § 1.5-1.6

---

### `Session`

1 lần dealer mở chatbot → đóng/timeout. Có `session_id` UUID, gắn với
1 dealer (có thể 1 dealer nhiều session nếu mở lại). Lưu trong bảng
`sessions` (Scope 3). Lifecycle: GREETING → ASKING → CONFIRMING → DONE
(hoặc TIMEOUT nếu **1 giờ** không hoạt động — refer 2C F2C.1 + 2A F2A.4
config `SESSION_TIMEOUT`).

→ Định nghĩa chi tiết: File 2A § F2A.1 + File 2C § F2C.1

---

### `Greeting` / `Closing`

- **Greeting**: lời chào đầu session (Stage GREETING). 3 biến thể
  random + hook tỉnh thành. Render từ template, không gen LLM.
- **Closing**: lời chốt cuối session (Stage DONE). 3 biến thể + path
  riêng cho `consent=no`. Render template.

→ Định nghĩa chi tiết: File 1A § 3 (Greeting) + § 7 (Closing); engine
File 2A § F2A.8.

---

### `Card` (Card xác nhận 5 phần)

ASCII card render trong Stage CONFIRMING, gồm 5 phần:
1. Danh thiếp (slot 1.1, 1.2, 1.3)
2. Công việc + Kênh (slot 2.x)
3. Khách cũ + Vướng (slot 3.x)
4. Bộ thương hiệu (slot 4.x)
5. Trong 3 ngày tới (next action)

Dealer review → confirm hoặc edit. **KHÔNG hiển thị C-code/Tier/Score**.

→ Định nghĩa chi tiết: File 1A § 6 + module `app/core/card_renderer.py`.

---

### `History`

Lịch sử message của 1 session (list of `{role, content, ts}`). Dùng
làm context cho LLM extractor + ack. Lưu ở Scope 3 (sessions table
hoặc bảng riêng tùy infra). KHÔNG persist sau khi session DONE >
retention period (Phase 1 = 30d, sau scale tùy compliance).

→ Định nghĩa chi tiết: File 2C § F2C.1 (storage).

---

## 2. Thuật ngữ về SCHEMA (dữ liệu)

### `Field` (Trường dữ liệu)

**1 ô dữ liệu** trong profile dealer (vd `owner_name`, `phone_or_zalo`,
`address`). Khác `slot`:

- Slot = ô THU THẬP (hỏi-đáp)
- Field = ô LƯU TRỮ (DB column)
- 1 slot có thể fill nhiều field (vd slot 1.1 fill `owner_name` + `dealer_name`)
- 1 field có thể được nhiều slot fill (vd `zalo` fill từ slot 1.3 hoặc 2.5)

### `Scope` (Phạm vi nguồn data)

4 scope cho mỗi field:

| Scope | Bên gen | Lưu ở đâu | Ví dụ field |
|---|---|---|---|
| **1. Chatbot direct** | Chatbot hỏi trực tiếp 17 slot | `dealer_profile_raw` | `dealer_name`, `phone_or_zalo`, `customer_pain` |
| **2. Chatbot auto-derive** | Chatbot tự gen từ data scope 1 | `dealer_profile_raw` | `province` (parse từ address), `brand_name_short` (rút gọn dealer_name), `slogan_options` (LLM gen) |
| **3. Internal state** | Chatbot state machine | `sessions` table | `stage`, `current_slot`, `flags`, `detected_dealer_type` |
| **4. External (Backend Scoring)** | Service khác (`LLM_QUALITY`, hiện tại Gemini 2.5 Pro) | **Bảng RIÊNG, chatbot KHÔNG ghi** | `c1..c9`, `c_score`, `tier`, `dealer_id`, `batch` |

⚠️ **Quan trọng:** Scope 4 = backend Scoring nội bộ. **Chatbot KHÔNG được:**
- Ghi Scope 4 field vào `dealer_profile_raw`
- Hiển thị Scope 4 vocab ("Tier A", "C-score", "C1-C9") với dealer

→ Định nghĩa chi tiết: File 2A § F2A.3

---

### `RAW Signal` (Tín hiệu thô cho Scoring)

Field text dài raw, lưu Scope 1, dùng làm input cho backend Scoring chấm
9 tiêu chí C1-C9:

| Signal field | Slot mining | Tiêu chí backend dùng |
|---|---|---|
| `local_dominance_signal` | 1.2 (bán kính khách) | C6 |
| `supplier_negotiation_signal` | 2.4 (backup nguồn) | C8 |
| `community_network_signal` | 2.6 (thợ/đối tác giới thiệu) | C9 |
| `motivation_signal` | 3.3 (vướng mắc + động lực) | C5 |
| `warranty_responsibility_signal` | 3.5 (bảo hành ai chịu) | C4 |
| `usp_signal` | 3.3 (lợi thế ngầm) | bonus |

→ Chatbot **chỉ thu raw**. Backend Scoring **tự chấm C1-C9 sau** —
KHÔNG phải job chatbot.

---

## 3. Thuật ngữ về TONE (giọng nói)

### `Dealer Type` (Nhóm tâm lý đại lý)

4 nhóm + 1 default, detect ở turn 3/8/13:

| Type | Đặc điểm | Tone ack |
|---|---|---|
| `lua_lo` (Lửa Lò) | Cộc, caps, chửi bậy | Ngắn ≤8 từ, không nịnh |
| `khoe` (Khoe) | Kể thành tích, số liệu | Khen CỤ THỂ + insight |
| `lo` (Lo) | Nghi ngờ, hỏi ngược | Trấn an + cam kết bảo mật cụ thể |
| `ban` (Bận) | 1-2 chữ, đi thẳng | Ngắn 5-12 từ, có thể gộp ack + ask |
| `unknown` | Chưa đủ data | **Default = `ban`** (conservative) |

→ Định nghĩa chi tiết: File 1B § 2 + File 2A § F2A.6

---

### `Intent` (Ý định message dealer)

7 intent enum cho mỗi message:

| Intent | Marker example |
|---|---|
| `affirmative` | "ok", "ừ", "chuẩn", "được" |
| `refusal` | "đéo cho", "không nói", "miễn cho tôi" |
| `khong_biet` | "không biết", "không nhớ", "tùy em" |
| `defensive` | "lừa đảo à", "phí gì", "em là ai" |
| `tam_su` | "vợ", "nhậu", "golf", "stress" |
| `edit` | "sửa X thành Y" (chỉ valid trong stage CONFIRMING) |
| `normal` | Default — không match marker nào |

→ Detect 2-layer (Layer 1 regex + Layer 2 LLM fallback).

→ Định nghĩa chi tiết: File 2A § F2A.2

---

## 4. Thuật ngữ về EDGE/EXCEPTION

### `Flag` (Cờ tích lũy)

Marker trong session.flags, lưu Scope 3. Mỗi flag = 1 sự kiện đặc biệt
trong session, để admin review.

**15 flag** (4 nhóm — sync với 2A F2A.3 enum + 2C F2C.8 queue triggers):

| Nhóm | Flag | Trigger |
|---|---|---|
| Behavior | `dealer_declined` | OPTIONAL slot SKIP ("không biết") |
| Behavior | `required_missing` | REQUIRED slot SKIP sau 3 retry |
| Behavior | `consent_unclear` | brandkit_consent null sau retry — slot 4.0 |
| Behavior | `multiple_refusal_in_row` | 3 OPTIONAL refuse liên tiếp — File 1C § 4 |
| Abuse | `prompt_injection` | Detect injection pattern — File 1C § 6 |
| Abuse | `abusive_language` | Dealer chửi cá nhân — File 1C § 5 |
| Abuse | `garbage_input` | Gibberish lặp — File 1C § 7 |
| Abuse | `dealer_too_defensive` | Defensive ≥3 lần — File 1C § 2 |
| Abuse | `address_blacklist` | Address chính trị/tôn giáo — File 1C § 10 |
| Data quality | `sanity_check_failed` | F2A.7 5-point check fail |
| Data quality | `phone_invalid_after_retry` | Phone sai format 3 lần — File 1C § 12 |
| Data quality | `voice_quality_poor` | STT empty/noise lặp — File 1C § 8 |
| Data quality | `brand_not_in_whitelist` | Brand lạ → admin review — File 1C § 11 |
| LLM guard | `hallucinate` | LLM bịa data — F2B.8 G2 |
| LLM guard | `pii_leak` | Bot share data dealer khác — F2B.8 G4 |

→ Full enum: File 2A § F2A.3 (Scope 3 flags Literal). Khi thêm flag mới:
  bump version 2A + update bảng này + KE_HOACH_REFACTOR § 2.3.

---

### `Escalation` (Chuyển human agent)

3 cấp + queue admin review:

| Cấp | Trigger | Hành động |
|---|---|---|
| **L1** | Vi phạm nhẹ lần 1 | Bot tự xử + flag |
| **L2** | Lặp 2 lần | Cảnh báo polite + offer dừng |
| **L3** | Lặp 3 lần / cực đoan | Soft-end session + push admin queue |

→ Định nghĩa chi tiết: File 1C § 13 + File 2C § F2C.8

---

## 5. Thuật ngữ về TECH

### `Sanity Check 5-point`

5 check trước khi `confirmation_status` chuyển PENDING → CONFIRMED:

1. 6 REQUIRED field không null (hoặc có flag `required_missing`)
2. Phone digits-only, len 9-11
3. Address ≥ 3 char, không chứa blacklist
4. `brandkit_consent` rõ ràng (không null trừ flag `consent_unclear`)
5. Không có Scope 4 field leak (c_score, tier, ...)

→ Định nghĩa chi tiết: File 2A § F2A.7

---

### `Guard` (Lớp bảo vệ)

4 guard chạy sau MỌI LLM response:

| Guard | Chống |
|---|---|
| `injection` | Dealer paste prompt jailbreak |
| `hallucinate` | LLM bịa data dealer chưa cho |
| `drift` | LLM dùng vocab cấm (Tier, C-score, BRANDKIT) |
| `pii_leak` | Bot share data dealer khác |

+ 2 guard tầng infra:
- `rate_limit` — IP/message rate (lưu ở **infra cache** — in-memory
  Phase 1, Redis hoặc tương đương khi scale)
- `abuse_detector` — score aggregation

→ Định nghĩa chi tiết: File 2B § F2B.8 + File 2C § F2C.2

---

### `LLM_FAST` / `LLM_QUALITY` (Model tier abstraction)

2-tier abstraction trong spec để tránh hardcode tên model (model
deprecate / đổi giá nhanh → spec rot). Mapping vendor-specific chỉ ở
config code.

| Tier | Dùng cho task | Vendor mapping pilot |
|---|---|---|
| `LLM_FAST` | Intent classify, extractor, STT brand correct, address parser, auto-derive brand_short/initials, ack Bận+Lửa Lò | Gemini 2.5 Flash (pilot) — fallback Claude Haiku 4.5 hoặc GPT-4o-mini |
| `LLM_QUALITY` | Ack Khoe+Lo (insight cụ thể), slogan options (5 phương án sáng tạo), defensive/tâm sự handler | Gemini 2.5 Pro (pilot) — fallback Claude Sonnet 4.6 hoặc GPT-4o |

→ Routing rule chi tiết: File 2B § routing table.
→ Rationale: `0_STRATEGY.md` § D8.

---

### `Cache TTL`

Cache LLM/STT/address theo TTL khác nhau:

| Cache | TTL |
|---|---|
| LLM intent classify | 1h |
| STT brand correct | 24h |
| Address parse | 24h |
| Province specialty | ∞ (in-memory) |
| Slogan options | 7d (same dealer name → same slogan) |
| System prompt build (per slot × dealer_type) | 1h (in-memory) |

→ Định nghĩa chi tiết: File 2C § F2C.5

---

## 6. Vocab cấm với dealer (FORBIDDEN)

> **Scope cấm:** chỉ trong **dialog bot ↔ dealer**. Trong code module
> (`app/llm/...`), spec file (tên file "EM_LINH_MKT"), tài liệu nội bộ
> (vd "Marketing" trong "Em Linh MKT" = tên persona) — KHÔNG cấm.

Bot **TUYỆT ĐỐI KHÔNG** dùng các từ sau khi nói với dealer:

```
❌ Tier / Tier A / Tier B / hạng A
❌ C-score / Score / Scoring / chấm điểm / đánh giá điểm
❌ C1 / C2 / ... / C9
❌ BRANDKIT (→ dùng "bộ thương hiệu")
❌ Namecard (→ "danh thiếp")
❌ Profile (→ "hồ sơ")
❌ Mini App (→ "ứng dụng nhỏ")
❌ Marketing (→ "quảng bá")
❌ batch (→ không nhắc)
❌ dealer_id (→ "mã đại lý" — nếu có)
```

→ Guard `drift` auto-rewrite hoặc reject + regenerate. File 2B § F2B.8.

→ Vocab giữ tiếng Anh (đã phổ biến): Logo, Video, QR, App, Zalo,
Facebook, Email, brand riêng (Xingfa, Schüco, Việt Pháp...).

---

## 7. Lookup nhanh — file nào tra cứu gì

| Cần biết | Tra file |
|---|---|
| Bot nói câu gì ở slot X | File 1A § 4 (Slot X) |
| Tone 4 nhóm dealer | File 1B § 2 |
| Edge case (defensive, abuse, troll) xử thế nào | File 1C |
| State machine logic | File 2A § F2A.4 |
| Schema field/scope | File 2A § F2A.3 |
| LLM prompt + extractor | File 2B |
| Storage + concurrency + cache | File 2C |
| Tổng quan triết lý + 17 slot list | CORE |
| Vì sao chọn approach này | `0_STRATEGY.md` |
| Versioning + log thay đổi | SYNC_LOG.md |
| Kế hoạch refactor v7→v8 — overview + 4 phase | `KE_HOACH_REFACTOR.md` § Executive summary + § PHẦN 4 |
| Schema mapping v7 cũ → v8 mới (field + flag enum) | `KE_HOACH_REFACTOR.md` § PHẦN 2 |
| Action items Phase 1 (24 task MVP) | `KE_HOACH_REFACTOR.md` § PHẦN 5 |
| Cấu trúc folder mới (app/, data/, tests/) | `KE_HOACH_REFACTOR.md` § PHẦN 3 |

---

**Lưu ý duy trì:** Khi thêm thuật ngữ mới vào CORE/1A/1B/1C/2A/2B/2C →
**update file này** + bump version + log SYNC_LOG.
