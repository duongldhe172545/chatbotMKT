# BỐI CẢNH DỰ ÁN — Em Linh MKT Chatbot (gửi AI khác đánh giá)

> **Cho người đọc (AI khác):** File này là bối cảnh DỰ ÁN + cách
> tiếp cận TÀI LIỆU hiện tại. Mục đích là để bạn đánh giá ĐỘC LẬP
> (không bị bias bởi AI A đã viết) và đưa ra phản biện trung thực.
>
> **Câu hỏi chính cần bạn trả lời ở cuối file. Đọc bối cảnh trước,
> trả lời sau.**

---

## PHẦN 1 — Bối cảnh dự án

### 1.1 Sản phẩm là gì?

**Em Linh MKT** là một chatbot intake (thu thập hồ sơ đại lý) cho thị
trường Việt Nam, ngành cửa nhôm kính / cửa cuốn / tủ bếp / VLXD. Bot
chat với chủ cửa hàng đại lý qua web (sau này có voice + Zalo), trò
chuyện 4-5 phút để thu thập 22 thông tin cốt lõi (tên, địa chỉ, sản
phẩm, đội thợ, hãng nhập, kênh khách, vướng mắc khách cũ, etc.) → cuối
buổi tặng "bộ thương hiệu" (logo + danh thiếp + video giới thiệu) làm
quà.

**Mục đích kinh doanh:** Onboard đại lý vào "Cộng Đồng Thợ 4.0" — sau
đó team người thật của doanh nghiệp sẽ liên hệ tư vấn chiến lược nền
tảng số.

**Đặc thù:**
- Thị trường: dealer Việt, đa số bận, có người cộc tính, có người sợ
  scam, có người thích khoe thành tích
- Bot phải linh hoạt 4 nhóm tâm lý (Lửa Lò / Khoe / Lo / Bận)
- Voice STT hay lệch tên brand (Xingfa → "sinh pha", Schüco → "su cô")
- KHÔNG được lộ với dealer rằng bot đang chấm điểm họ (backend Scoring
  C1-C9 là service nội bộ riêng, dealer KHÔNG được biết)

### 1.2 Tech stack hiện tại (code đang refactor)

- Backend: Python 3.11 + FastAPI
- LLM: **model-agnostic** (spec dùng 2-tier abstraction `LLM_FAST` +
  `LLM_QUALITY` — refer D8 trong `RULE_KICH_BAN/0_STRATEGY.md`)
  - Pilot vendor hiện tại: **Google Gemini** (Gemini 2.5 Flash cho FAST,
    Gemini 2.5 Pro cho QUALITY) — chọn vì cost rẻ
  - Fallback vendor: **Anthropic Claude** (Haiku 4.5 + Sonnet 4.6) —
    code adapter còn giữ trong `app/llm/claude.py`
  - Backend Scoring là service **riêng** (không phải chatbot), hiện
    chạy Gemini 2.5 Pro chấm C1-C9 — refer `chatbot_tieu_chi_dealer.md`
- Storage: SQLite (WAL mode), pilot scale (≤ 100 dealer/ngày)
- Frontend: HTML/CSS/JS vanilla
- Deploy: Railway

### 1.3 Quy mô team

- **1 dev** (Duong) — owner sản phẩm + code
- **1 LLM** (Claude Code) — pair programming
- Pilot stage, chưa scale

### 1.4 Trạng thái hiện tại

Đã có 1 implementation v7 cũ (~5500 dòng Python) đang chạy ngon nhưng
paradigm đổi nhiều: từ "16 micro-turn fixed" → "17 slot Required/
Optional + 4 stage forward-only + dealer type detection".

→ Đang refactor lại từ đầu.

---

## PHẦN 2 — Tài liệu hiện tại (cần bạn đánh giá)

### 2.1 Cấu trúc

```
EM_LINH_MKT_CORE.md          (v3.0.0, ~600 dòng)
  — principles + structure: triết lý / persona / ngôn ngữ / tâm lý
    dealer / 17 slot / schema 4 scope / 9 tiêu chí chấm điểm /
    luật khóa / recovery

SYNC_LOG.md                  (v1.0.0, ~150 dòng)
  — quy ước versioning (semver) + sync rule khi sửa file +
    log mọi thay đổi

KE_HOACH_REFACTOR.md         (v1.0, ~1500 dòng)
  — kế hoạch refactor v7→v8: phân tích phản biện 12 điểm +
    schema mapping (cũ→mới) + cấu trúc folder mới + 4 phase
    migration + 24 action items Phase 1

RULE_KICH_BAN/
  KICH_BAN_1A_core.md       (v0.2.0, ~1100 dòng)
    — Behavioral spec: 17 slot Q&A script + 3 biến thể câu hỏi /
      slot + 4 ack template / nhóm dealer + retry tone REQUIRED +
      Greeting templates (3 biến thể) + Confirmation Card 5 phần +
      Closing templates (3 biến thể)

  KICH_BAN_1B_tone.md       (v0.1.0, ~400 dòng)
    — Behavioral spec: Tone library 4 nhóm dealer
      (Lửa Lò / Khoe / Lo / Bận) — đặc điểm nhận biết + tone matrix
      4 dimension + ack pattern + cấm + pivot rule

  KICH_BAN_1C_edgecase.md   (v0.1.0, ~250 dòng)
    — Behavioral spec: 12 edge case (defensive lặp, tâm sự dài,
      refusal lặp, abuse cá nhân, troll/inject, garbage, voice fail,
      im lặng, address blacklist, brand unknown, phone invalid,
      escalation queue) + 3 cấp escalation L1/L2/L3

  LUAT_2A_core.md           (v0.2.0, ~700 dòng)
    — Technical spec: 8 rule
      F2A.1 Stages + transitions (4 stage forward-only)
      F2A.2 Intent detection (7 intent, 2-layer regex + LLM)
      F2A.3 Schema 4 scope (chatbot direct / auto-derive / state / external)
      F2A.4 Smart advance state machine (ADVANCE/RETRY/SKIP/PAUSE)
      F2A.5 Slot priority + Required/Optional retry (max 3 lần REQUIRED)
      F2A.6 Dealer type detection (4 nhóm, detect turn 3/8/13)
      F2A.7 Sanity check 5-point trước save
      F2A.8 Greeting/Closing engine + province specialty table 50 tỉnh

  LUAT_2B_llm.md            (v0.1.0, ~700 dòng)
    — Technical spec: 8 rule LLM engineering
      F2B.1 System prompt template (≤ 600 token)
      F2B.2 Extractor schema (1 tool / slot, 17 tool)
      F2B.3 Intent classifier (Layer 2 LLM fallback)
      F2B.4 Ack generator per dealer type
      F2B.5 STT brand correction (Xingfa fuzzy)
      F2B.6 Address parser (63 tỉnh)
      F2B.7 Auto-derive (brand_short / initials / slogan 5 options)
      F2B.8 4 guard (injection / hallucinate / drift / PII leak)

  LUAT_2C_infra.md          (v0.1.0, ~700 dòng)
    — Technical spec: 8 rule infrastructure
      F2C.1 Session lifecycle + DB schema
      F2C.2 Spam guard (rate limit IP + abuse score)
      F2C.3 Concurrency (Redis lock TTL 30s)
      F2C.4 Timeout + retry policy + fallback safe ack
      F2C.5 Cache (LLM/STT/address/slogan, multi-layer)
      F2C.6 Monitoring + alerting (Prometheus + Grafana)
      F2C.7 Data files (9 JSON file versioning)
      F2C.8 Admin queue + review workflow + SLA
```

**Tổng:** 3 file root + 6 file `RULE_KICH_BAN/` + 1 KE_HOACH_REFACTOR
≈ **~6100 dòng spec** (chưa kể CORE, SYNC_LOG, KE_HOACH).

### 2.2 Cấu trúc trong mỗi file

#### File 1A/1B/1C (behavioral)

- VERSION + CHANGELOG
- MỤC LỤC
- Quy ước
- Nội dung chính (slot Q&A / tone matrix / edge case)
- Cross-ref bảng

#### File 2A/2B/2C (technical)

Mỗi rule có 7 section:
- **Yêu cầu** — mô tả rule
- **Algorithm** — pseudocode
- **Tham số config** — bảng
- **Acceptance test** — text + 1-2 case ví dụ + "tổng quát hóa pattern"
  + PASS/FAIL list
- **Constraints** — KHÔNG được vi phạm
- **Pointer implementation** — file path Python
- **Cross-ref** — link spec khác

### 2.3 Quy ước xuyên suốt

1. **Disclaimer toàn cục**: "Tất cả example là minh họa, engine phải
   cover MỌI shape tương tự, KHÔNG khóa cứng 1 case"
2. **Semver versioning**: `vMAJOR.MINOR.PATCH` cho mỗi file
3. **Sync rule**: Sửa file MAJOR/MINOR → bắt buộc review file liên
   quan (cross-ref)
4. **Module pair**: File 1A ↔ 2A, 1B ↔ 2B, 1C ↔ 2C
5. **Việt hóa**: cấm dùng "BRANDKIT/Profile/Tier/Scoring" với dealer

### 2.4 Sample 1 rule (để bạn hình dung độ chi tiết)

Trích từ `LUAT_2A_core.md` § F2A.4 (Smart advance state machine):

```
## F2A.4 — Smart advance state machine

**Tham chiếu CORE:** § G.4 Logic Required/Optional + Smart advance
**Tham chiếu File 1A:** § 1.4 Quy ước Required/Optional + § 4 slot Q&A

### Yêu cầu

Sau mỗi message từ đại lý, state machine quyết định 1 trong 4 hành động:
- `ADVANCE` — chuyển sang slot tiếp theo
- `RETRY` — hỏi lại slot hiện tại (tone giảm dần)
- `SKIP` — bỏ slot hiện tại, qua slot tiếp
- `PAUSE` — tạm dừng flow để xử intent đặc biệt

### Algorithm

[pseudocode 30 dòng]

### Tham số config

| Param | Default | Ý nghĩa |
| MAX_RETRY_REQUIRED | 3 | Sau N retry → SKIP + flag |
| MAX_RETRY_OPTIONAL | 0 | OPTIONAL không retry |
| ...

### Acceptance test

> ⚠️ VÍ DỤ MINH HỌA — engine cover mọi shape tương tự

**Pattern test:** Slot OPTIONAL "không biết" → SKIP NGAY...

**Case ví dụ minh họa:**
[3-4 case Q&A turn-by-turn]

**Tổng quát hóa pattern (engine PHẢI cover):**
[bullet list 4-5 nguyên tắc]

✅ PASS:
[4-5 bullet]

❌ FAIL:
[4-5 bullet]

### Constraints (KHÔNG được vi phạm)
[4-5 bullet]

### Pointer implementation
→ `app/core/conversation.py` § `_handle_v7_turn`

### Cross-ref
[link 5-7 spec khác]
```

→ Format này dùng cho **8 rule F2A + 8 rule F2B + 8 rule F2C = 24 rule total**.

---

## PHẦN 3 — Câu hỏi cần bạn (AI khác) trả lời

Trả lời TRUNG THỰC, không cần lịch sự. Mục đích là cross-validate AI A
(Claude) đã thiết kế tài liệu hợp lý chưa.

### Q1. Cấu trúc 6 file (1A/1B/1C + 2A/2B/2C) có phù hợp industry standard không?

Cụ thể:
- Có cần tách behavioral (1A/B/C) vs technical (2A/B/C) như vậy không?
- Module pair (1A↔2A, etc.) có hợp lý không?
- Có industry pattern nào tương đương (arc42, C4, IEEE 830, BDD) match
  approach này?
- Hay nên gộp lại / tách thêm?

### Q2. Volume ~6100 dòng spec có over-engineered cho dự án pilot 1 dev không?

Cụ thể:
- Pilot scale ≤ 100 dealer/ngày, 1 dev FT, 1 LLM pair-programming
- Có cần spec chi tiết đến mức 8 rule × 7 section × 3 file = 168 spec
  blocks?
- Hay 1 README + 1 PRD ngắn + code comments là đủ?
- Threshold "đủ doc" cho pilot là gì?

### Q3. Format "Acceptance test" hiện tại (informal text + case ví dụ + PASS/FAIL bullet) có nên chuyển sang Gherkin (Given-When-Then) không?

Cụ thể:
- Hiện em viết text + "tổng quát hóa pattern"
- Gherkin sẽ executable (test framework parse được)
- Trade-off: Gherkin formal hơn, đòi training dev đọc/viết
- Phù hợp cho 1 dev pilot không?

### Q4. Em đang thiếu 3 artifact industry standard: Glossary / ADR (Architecture Decision Records) / Solution Strategy. Có nên thêm?

Cụ thể:
- Glossary: định nghĩa "slot vs turn vs field", "REQUIRED vs OPTIONAL", "4 dealer type"
- ADR: 1 file / decision lớn (vd "Vì sao SQLite không Postgres?", "Vì sao 4 stage forward-only?")
- Solution Strategy: section giải thích "vì sao chọn approach này"
- Effort thêm ≈ 2-3 ngày
- Có đáng cho pilot không?

### Q5. Vietnam context: team Việt thường document như thế nào? Có cần adapt approach không?

Cụ thể:
- Em research nhưng chủ yếu nguồn US/EU (arc42 / Rasa / PatternFly)
- Startup Việt thường ít formal hơn — dùng Notion + Google Docs
- Có industry pattern nào specific cho Vietnamese startup chatbot
  team không?
- Approach hiện tại (file MD + git + semver) có over so với team Việt
  thường làm không?

### Q6. Spec hiện tại nói "BOT KHÔNG được tự xưng là bot/AI/model với dealer". PatternFly nói "Transparency: Be transparent about AI use". Mâu thuẫn này xử thế nào?

Cụ thể:
- Lý do nội bộ: muốn dealer cảm giác trò chuyện tự nhiên, không cộc
- Lý do industry: transparency = nguyên tắc đạo đức + luật (vd EU AI
  Act, FTC guidance)
- Có cách nào dung hòa? (vd "em là chatbot, phía sau có team người thật")

### Q7. Nếu là bạn, bạn sẽ adjust gì TOP 3?

Tự do critique. Không cần giữ ý của AI A. Có thể đề xuất:
- Bỏ file nào → gộp file nào
- Đổi format từ MD sang YAML / JSON / Notion
- Thay đổi mức chi tiết
- Refactor structure khác (vd theo arc42 12 sections)
- Bất kỳ điều gì bạn thấy nên adjust

---

## PHẦN 4 — Format trả lời mong muốn

Trả lời theo format:

```markdown
# ĐÁNH GIÁ TÀI LIỆU EM LINH MKT — bởi AI [TÊN_BẠN]

## TL;DR (1-2 paragraph)
[bottom line — approach hợp lý hay không]

## Q1: [tóm tắt câu hỏi]
[trả lời ngắn]

## Q2: ...
[...]

## Hành động TOP 3 nếu là tôi
1. ...
2. ...
3. ...

## Nguồn tham khảo
- ...
```

---

## PHẦN 5 — Đọc thêm (nếu cần verify)

Nếu bạn muốn đọc nội dung gốc các file để verify, đây là file cần đọc:

| File | Đường dẫn | Note |
|---|---|---|
| CORE | `EM_LINH_MKT_CORE.md` | Principles + 17 slot list |
| SYNC_LOG | `SYNC_LOG.md` | Versioning rule |
| File 1A sample | `RULE_KICH_BAN/KICH_BAN_1A_core.md` | Behavioral — 17 slot Q&A |
| File 2A sample | `RULE_KICH_BAN/LUAT_2A_core.md` | Technical — 8 rule state machine |
| Kế hoạch refactor | `KE_HOACH_REFACTOR.md` | Migration plan |
| Self-critique của AI A | `DANH_GIA_TAI_LIEU.md` | Em (Claude) tự đánh giá |

---

**Cảm ơn bạn đã đọc + đánh giá. Mong feedback trung thực.**

— Duong (product owner) + Claude (AI A — đã viết spec)
