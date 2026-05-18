# STRATEGY — Quyết định lớn của Em Linh MKT

> **Mục đích:** Ghi lại RATIONALE (vì sao) cho 8 quyết định lớn về
> design + architecture. Để **3-6 tháng sau** Duong/Claude đọc lại
> còn nhớ vì sao chọn approach này, KHÔNG bị "đi vào vết xe đổ" sửa
> nhầm.
>
> **Format mỗi quyết định:** Vấn đề → Option đã cân nhắc → Chọn →
> Rationale → Trade-off → Khi nào nên reconsider.

---

## VERSION

| Ngày | Version | Note |
|---|---|---|
| 2026-05-14 | v1.0 | First — 7 quyết định lớn |
| 2026-05-15 | v1.1 | Thêm D8 — Model strategy (2-tier abstraction LLM_FAST/LLM_QUALITY). Reverse Phụ lục "Vì sao bỏ Gemini" → "Vì sao model-agnostic". |
| 2026-05-15 | v1.2 | Spec consistency: D3 rationale đổi count "6 REQUIRED + 11 OPTIONAL" → "6 REQUIRED + 10 OPTIONAL + 1 thông báo (slot 4.1 logo)" — slot 4.1 không fill field, sync với CORE/1A/GLOSSARY. |
| 2026-05-15 | v1.3 | Spec consistency BATCH 2: D3 Trade-off line "11 LLM extractor + 11 retry handler" → "10 + 10 (slot 4.1 không có extractor)" — sync với cách đếm "10 OPTIONAL + 1 thông báo" ở D3 line 124. |
| 2026-05-15 | v1.4 | Spec consistency BATCH 4: (1) Add **D9** — Phase 1 cut scope chỉ 3 REQUIRED (rationale: feedback loop nhanh, slot 1.3/2.1/2.2 phức tạp đẩy Phase 2). (2) Add **D10** — Slot 4.0 consent=no skip thẳng 4.1/4.2 + đi CONFIRMING (rationale: tôn trọng refusal). (3) Add **D11** — Retry rule 3 total / 2 consecutive / DEFER + PARTIAL_RETRY không count (rationale: dealer turn đầu hay test/nghịch, phân bố retry thông minh). (4) Add **D12** — Flag enum 15 chia 4 nhóm (Behavior/Abuse/Data quality/LLM guard) — rationale: admin queue trigger map theo nhóm + UI filter. (5) D8 cross-ref bỏ wiki-link `[[...]]` → markdown path standard. |

---

## D1. Vì sao tách 6 file thành 2 tier (behavioral 1A/1B/1C vs technical 2A/2B/2C)

### Vấn đề

Có 2 nhóm người đọc khác nhau:
- **Content writer / PM / sales** cần biết "bot nói gì, tone thế nào,
  edge case xử ra sao" — không quan tâm code Python
- **Dev / engineer** cần biết "state machine logic, schema, prompt
  engineering, infra" — không quan tâm câu chữ chi tiết

Nếu gộp 1 file khổng lồ → mỗi người đọc 50% trôi mắt.

### Option

1. **1 file PRD khổng lồ** (~5000 dòng tất cả) — paradigm cũ
2. **6 file tách 2 tier** (3 behavioral + 3 technical) — chọn
3. **arc42 12 sections** — chuẩn industry, nhưng quá heavy cho pilot

### Chọn: Option 2 (6 file 2 tier)

### Rationale

- **1A/1B/1C** focus behavioral — content writer / Duong đọc khi
  muốn sửa câu chữ / tone / edge case
- **2A/2B/2C** focus technical — dev/Claude đọc khi code
- Module pair (1A↔2A, 1B↔2B, 1C↔2C) → sync rule rõ: sửa 1 bên cần
  review bên kia
- Phù hợp 1 dev + 1 LLM pilot, không over như arc42

### Trade-off

- ❌ Cross-ref tables phải maintain tay — bug khi quên update
- ❌ Có thể duplicate nội dung giữa 1A và 2A (mitigation: spec rõ
  1A = "bot nói gì", 2A = "bot xử thế nào" — không overlap)

### Reconsider khi

- Team > 5 người → cân nhắc chuyển arc42 (12 section chuẩn)
- Hoặc 1 dev đọc 6 file thấy quá nhiều → gộp 1A+1B+1C thành 1 file +
  2A+2B+2C thành 1 file (2 file total)

---

## D2. Vì sao 4 stage forward-only (không cho dealer back)

### Vấn đề

Dealer có thể muốn "quay lại sửa thông tin đã cho" giữa flow.

### Option

1. **Cho back** (vd dealer ở slot 2.3 quay lại sửa slot 1.1) — phức tạp
2. **Forward-only** + có stage CONFIRMING ở cuối cho phép sửa — chọn
3. **Không cho sửa gì cả** — UX kém

### Chọn: Option 2 (forward-only + edit ở CONFIRMING)

### Rationale

- State machine đơn giản hơn → ít bug
- Dealer biết "phải xong hết rồi mới sửa" → tập trung trả lời từng
  slot, không loanh quanh
- Stage CONFIRMING có `edit_parser` cho phép "sửa địa chỉ thành X" —
  edge case sửa rất hiếm (< 5% dealer)
- Đỡ phải handle "back từ slot 3.3 về 1.1 → reset slot 2.x?" → loop
  infinite

### Trade-off

- ❌ Dealer typo slot 1.1 → phải đợi đến CONFIRMING mới sửa được
- ❌ Một số dealer kỹ tính có thể bực

### Reconsider khi

- > 20% dealer phàn nàn không sửa được giữa flow
- Hoặc UX research cho thấy dealer Việt expect back navigation

---

## D3. Vì sao 17 slot (không 10, không 25)

### Vấn đề

Cân bằng giữa "đủ thông tin để chấm điểm C1-C9 + làm bộ thương hiệu"
vs "không hỏi quá lâu làm dealer chán".

### Option

1. **10 slot tối thiểu** (chỉ identity + main product) — không đủ chấm C5/C6/C8/C9
2. **17 slot** (4 chủ đề chia đều) — chọn
3. **25 slot** (chi tiết từng C1-C9) — quá lâu, dealer drop session

### Chọn: Option 2 (17 slot, 4 chủ đề)

### Rationale

- **4 chủ đề tự nhiên** trong câu chuyện làm ăn:
  - Danh thiếp (3 slot)
  - Công việc + Kênh (6 slot)
  - Khách cũ + Vướng (5 slot)
  - Bộ thương hiệu (3 slot)
- **6 REQUIRED + 10 OPTIONAL + 1 thông báo (slot 4.1 logo)** → dealer cộc
  vẫn xong nhanh 6 slot, dealer kỹ tính có thể chia sẻ thêm 10 slot OPTIONAL.
  Slot 4.1 không fill field, chỉ là turn bot thông báo "logo em chọn theo
  ngành" — không tốn effort dealer.
- **Slot 3.5 MỚI** (bảo hành — ai chịu) thêm vì C4 (skin in the game)
  cần signal này

### Trade-off

- ❌ 17 slot vẫn dài cho dealer "Bận" → trung bình 6-7 phút trò chuyện
- ❌ Slot OPTIONAL nhiều → 10 LLM extractor + 10 retry handler (slot 4.1 không có extractor)
- ❌ Dealer drop giữa session → mất profile (sanity check vẫn pass với
  REQUIRED minimum)

### Reconsider khi

- > 30% dealer drop trước CONFIRMING → cắt OPTIONAL slot
- Backend Scoring không dùng vài raw signal → bỏ slot tương ứng
- Slot mới phát sinh từ feedback admin queue → thêm

---

## D4. Vì sao REQUIRED retry max 3, OPTIONAL skip ngay (không retry)

### Vấn đề

Khi dealer "không biết" / "không cho" → bot xử thế nào? Loop hỏi mãi
gây bực, skip luôn thì mất data.

### Option

1. **Retry mọi slot 3 lần** — dealer bực vì slot OPTIONAL bị ép
2. **Skip mọi slot ngay** — REQUIRED không có data → flow vô nghĩa
3. **REQUIRED retry 3 lần + OPTIONAL skip ngay** — chọn

### Chọn: Option 3 (asymmetric)

### Rationale

- **REQUIRED** = thông tin sống còn (tên, địa chỉ, phone, sản phẩm, mô hình,
  consent) → ép 3 lần với tone giảm dần OK
- **OPTIONAL** = "nice to have" — dealer bận, không nhớ chi tiết → SKIP
  tôn trọng thời gian
- 3 lần là **threshold pain** từ UX research: lần 1 hỏi bình thường,
  lần 2 giải thích lý do, lần 3 offer fallback dễ hơn — chưa được thì
  thôi

### Trade-off

- ❌ OPTIONAL skip ngay → data RAW signal thiếu nhiều → chấm Scoring
  khó hơn (admin review thủ công nhiều hơn)
- ❌ REQUIRED retry 3 lần → dealer cộc có thể drop session

### Reconsider khi

- Admin queue overload vì OPTIONAL miss quá nhiều → cân nhắc retry 1 lần
- Hoặc REQUIRED skip rate > 20% → cân nhắc giảm 6 REQUIRED xuống 4

---

## D5. Vì sao default tone "Bận" cho 3 turn đầu (chưa detect)

### Vấn đề

Chưa biết dealer thuộc nhóm nào (Lửa/Khoe/Lo/Bận) → bot nên tone gì
mặc định?

### Option

1. **Khoe default** (khen niềm nở) — nguy hiểm nếu dealer là Lo (nghi ngờ)
2. **Lửa Lò default** (cộc) — nguy hiểm nếu dealer là Khoe (cụt hứng)
3. **Bận default** (trung tính, ngắn) — chọn
4. **Detect ngay turn 1** — không đủ data, accuracy thấp

### Chọn: Option 3 (Bận = default conservative)

### Rationale

- Bận = tone TRUNG TÍNH nhất, không nịnh không cộc
- Nếu dealer thực là Bận → đúng tone luôn
- Nếu dealer là Khoe → có thể bị cụt hứng 3 turn nhưng turn 3 detect
  sẽ chuyển sang Khoe ngay
- Nếu dealer là Lo → tone trung tính không gây nghi ngờ
- Nếu dealer là Lửa Lò → hơi mềm 1 chút nhưng dealer Lửa Lò không bực
  với mềm (chỉ bực với khen nịnh)
- Detect turn 1 không đủ data — ít accuracy hơn turn 3

### Trade-off

- ❌ Dealer Khoe trong 3 turn đầu có thể cảm thấy "bot không hiểu"
- ❌ Re-detect turn 8/13 cũng có sai số

### Reconsider khi

- Manual test 20 dealer Khoe → ≥ 5 người phàn nàn → cân nhắc detect
  signal khoe sớm hơn

---

## D6. Vì sao 1 tool schema riêng cho mỗi slot (17 tool), không 1 tool gộp

### Vấn đề

LLM extract field — dùng 1 tool to gồm 22 field, hay 17 tool nhỏ 1-2 field?

### Option

1. **1 tool to** với 22 field — LLM bịa field không có (hallucinate cao)
2. **17 tool riêng** với 1-2 field/tool — chọn
3. **4 tool theo chủ đề** (1, 2, 3, 4) — middle ground

### Chọn: Option 2 (17 tool)

### Rationale

- LLM được give 1 tool với chỉ field SLOT HIỆN TẠI → focus, không bịa
- Đỡ confuse: dealer ở slot 1.1 (tên) thì LLM không "nhân tiện
  extract" phone hay address
- Strict schema → validate Pydantic dễ
- Tool input_schema strict (type + enum + maxLength + pattern) →
  chống prompt injection bằng input dài
- Cost: pass 1 tool mỗi turn, không pass 17 tool cùng lúc → token cost
  thấp

### Trade-off

- ❌ Code 17 tool schema → maintenance: 17 chỗ phải sync
- ❌ Mitigation: define dict `SLOT_TOOL_SCHEMAS` trong 1 file
  `schemas.py` thay 17 file riêng

### Reconsider khi

- LLM cost spike → gộp lại 4 tool theo chủ đề
- Hoặc field cross-slot (vd dealer trả lời "Tùng, 0912xxx" trong slot
  1.1) — hiện engine bỏ phone, hỏi lại slot 1.3 (tốn turn)

---

## D7. Vì sao tách Scope 4 (Backend Scoring) ra service riêng, KHÔNG cho chatbot gen

### Vấn đề

Field `c1..c9`, `c_score`, `tier`, `dealer_id`, `batch` — ai gen?

### Option

1. **Chatbot gen luôn** (LLM chấm điểm sau intake) — fast, 1 service
2. **Tách service Scoring riêng** (`LLM_QUALITY` chấm sau, async — hiện tại là Gemini 2.5 Pro, có thể đổi vendor) — chọn
3. **Admin chấm thủ công** — quá chậm scale

### Chọn: Option 2 (tách service)

### Rationale

- **Separation of concerns:** chatbot thu data, Scoring chấm điểm,
  Designer team làm bộ thương hiệu — 3 service riêng
- **TUYỆT ĐỐI KHÔNG cho dealer biết bị chấm điểm** → nếu cùng service
  với chatbot, risk leak vocab cao (LLM lỡ nói "Tier A")
- Scoring service đã có (hiện tại chạy Gemini 2.5 Pro chấm batch — xem
  `chatbot_tieu_chi_dealer.md`. Vendor có thể đổi, chatbot không phụ
  thuộc). Chatbot chỉ cần xuất raw signal đủ context, Scoring tự đọc + chấm
- Scoring có thể chạy ASYNC sau khi session DONE → không block dealer
- Reasonable scale: chatbot 100 dealer/ngày → Scoring batch 1 lần/ngày

### Trade-off

- ❌ 2 service, 2 codebase, 2 deploy
- ❌ Migration data giữa chatbot DB và Scoring DB (mitigation: shared
  DB, schema isolated bằng table riêng)

### Reconsider khi

- Pilot < 50 dealer/ngày → có thể gộp 1 service tạm (tiết kiệm infra)
- Hoặc nếu vendor LLM ra Assistants/Agents API có Scoring inline (vd
  OpenAI Assistants, Anthropic Claude with Tools, Gemini Function
  Calling) → reconsider gộp service

---

## Phụ lục — Quyết định nhỏ (không đủ tầm 1 file riêng)

### Vì sao chia category enum 7 loại (cua_cuon / cua_nhom_kinh / cua_thep / tu_bep / solar / bao_tri / vlxd)?

- Lấy từ MVP v01 sau khảo sát thị trường thực tế
- 7 loại cover ≥ 95% dealer ngành cửa/nhôm kính/tủ bếp/VLXD Việt
- Reconsider khi gặp dealer ngoài 7 loại > 5%

### Vì sao SQLite (không Postgres) cho pilot?

- Pilot ≤ 100 dealer/ngày → SQLite WAL mode đủ
- Deploy Railway dễ (file local, không cần managed DB)
- Reconsider khi scale > 500 dealer/ngày hoặc cần multi-region

### Vì sao spec model-agnostic (LLM_FAST / LLM_QUALITY) thay vì hardcode vendor?

- Model thay đổi nhanh: vendor mới ra, giá đổi, model deprecate. Hardcode
  tên model trong spec → spec rot trong 3-6 tháng
- Lõi (rule/flow/schema/tone/guard) phải vendor-portable. Pilot có thể
  chạy Gemini Flash cho rẻ; production có thể đổi Claude Haiku nếu cần
  reasoning tốt hơn — spec không cần viết lại
- Refer **D8** (model strategy)

### Vì sao Redis defer Phase 4 (không Phase 1)?

- Phase 1-3: in-memory adapter cùng interface với Redis → đủ pilot
- Redis cần infra mới (Railway add-on, cost) → defer khi scale thật
- Refer `KE_HOACH_REFACTOR.md` § Phase 4

### Vì sao schema mới drop hết dealers.db cũ (không migrate)?

- v7 cũ + v8 mới khác paradigm hoàn toàn (16 micro-turn → 17 slot 4 stage)
- Migration script effort > lợi ích (data dealer cũ ít, có thể export
  JSON archive)
- Refer `KE_HOACH_REFACTOR.md` § Q2

---

## D8 — Model strategy: 2-tier abstraction `LLM_FAST` / `LLM_QUALITY`

### Vấn đề

Spec hardcode tên model (Haiku, Sonnet, Gemini Flash, GPT-4o) → 3-6
tháng sau model deprecate / đổi giá → phải sửa spec 7-10 chỗ. Lõi
business (intent / extract / ack / guard) không đổi nhưng cứ phải
re-version vì model name đổi.

### Option

1. **Hardcode model name** (vd "Claude Haiku 4.5") — dễ đọc, chính xác,
   nhưng rot nhanh
2. **2-tier abstraction**: `LLM_FAST` (rẻ, deterministic, dùng cho
   intent/extract/STT/derive) + `LLM_QUALITY` (chất lượng cao, dùng cho
   ack Khoe/Lo, slogan, defensive handler) — chọn
3. **5-tier abstraction**: ultra-cheap / cheap / standard / quality /
   reasoning — chi tiết hơn nhưng over-engineering cho pilot
4. **Generic "LLM"** không phân tier — dev phải tự quyết mỗi chỗ → drift

### Chọn: Option 2 (2 tier)

### Rationale

- Đủ phân biệt cost/quality cho 99% case trong scope chatbot intake
- Vendor-portable: pilot có thể là Gemini Flash + Gemini Pro; production
  có thể đổi Haiku + Sonnet; chỉ sửa 1 chỗ trong config code, không sửa
  spec
- Mapping cụ thể (khi code thật):
  - `LLM_FAST` ← Gemini 2.5 Flash hoặc Claude Haiku 4.5 hoặc GPT-4o-mini
  - `LLM_QUALITY` ← Gemini 2.5 Pro hoặc Claude Sonnet 4.6 hoặc GPT-4o
- Routing rule rõ trong [[luat-2b-llm]]:
  - Intent classify, extractor, STT brand correct, address parser,
    brand_short/initials derive, ack Bận/Lửa Lò → `LLM_FAST`
  - Ack Khoe/Lo (insight cụ thể), slogan options (5 phương án sáng tạo),
    defensive/tâm sự handler → `LLM_QUALITY`

### Trade-off

- ❌ 2 tier không cover edge case "ultra-cheap" cho intent siêu đơn giản
  (vd embedding-based intent) — accept, scale sau
- ❌ Khi pilot phải còn 1 đoạn code tự map `LLM_FAST` → tên model thật
  (vd `app/llm/client.py:resolve_model("fast")`) — không né được, đây
  là chỗ duy nhất hardcode

### Reconsider khi

- Có > 3 tier rõ ràng cần thiết (vd thêm "reasoning model" cho task
  phức tạp như multi-turn debate detection)
- Vendor lock-in trade-off thay đổi (vd 1 vendor giảm giá 10x, cost
  không còn là constraint chính)

### Cross-ref

- `RULE_KICH_BAN/LUAT_2B_llm.md` § routing table (chỗ áp tier thực tế)
- `BOI_CANH_DU_AN.md` § Tech stack (vendor mapping hiện tại)
- `KE_HOACH_REFACTOR.md` § 0.9 LLM client (cấu hình runtime)

---

---

## D9 — Phase 1 cut scope chỉ 3 REQUIRED (không phải 6)

### Vấn đề

Phase 1 MVP cần feedback loop sớm. Nếu làm hết 6 REQUIRED slot ngay từ
đầu → mất 3-4 ngày chỉ riêng phần extractor + validation phức tạp (slot
1.3 phone digits-only retry, 2.1 auto-derive `main_category`, 2.2 suy
`dealer_type` enum).

### Chọn: 3 REQUIRED slot Phase 1 (1.1 tên, 1.2 địa chỉ, 4.0 consent)

### Rationale

- 3 slot này text-str đơn giản nhất, không cần LLM auto-derive phức tạp
- Đủ chạy end-to-end happy case (greeting → 3 slot → card → DONE)
- Phase 1 MVP demo trong 6-8 ngày thay vì 10-12 ngày
- Slot 1.3 / 2.1 / 2.2 đẩy đầu Phase 2 — kế thừa infrastructure Phase 1

### Trade-off

- ❌ Card Phase 1 hiện hotline=null, main_category=null → e2e test phải
  assert null thay vì validate format
- ❌ Dealer Phase 1 demo "chưa thực tế" (thiếu phone) — chấp nhận vì
  scope MVP

### Reconsider khi

- Phase 1 xong < 6 ngày → có thể gộp slot 1.3 luôn
- User feedback "card thiếu phone quá kỳ" → đẩy slot 1.3 lên Phase 1.5

→ Refer KE_HOACH_REFACTOR § 0.1 + § PHẦN 4 Phase 1.

---

## D10 — Slot 4.0 consent=no → skip thẳng 4.1/4.2 + đi CONFIRMING

### Vấn đề

Slot 4.0 hỏi `brandkit_consent` (yes/no). Nếu dealer nói "không cần quà"
mà bot vẫn hỏi 4.1 logo + 4.2 màu phong thủy → vô lý + ép dealer.

### Chọn: consent=no → mark skip 4.1/4.2, đi thẳng CONFIRMING

### Rationale

- Tôn trọng refusal — dealer đã rõ ràng không cần
- Card render bỏ section "Bộ thương hiệu" hoặc note "dealer từ chối"
- Closing path consent=no riêng (1A § 7.5)
- Engine logic ở F2A.4 step 2.5

### Trade-off

- ❌ Dealer reject 4.0 → mất cơ hội upsell logo/màu (rare case)

### Reconsider khi

- Pilot data show > 5% dealer reject 4.0 sau đó hỏi xin lại → cân nhắc
  thêm bước "anh có muốn xem demo bộ thương hiệu trước khi quyết không?"

→ Refer F2A.4 step 2.5 + File 1A § 4 slot 4.0 handler.

---

## D11 — Retry rule: 3 tổng / 2 liên tiếp / DEFER + PARTIAL_RETRY không count

### Vấn đề

Retry rule cũ "REQUIRED retry max 3 lần liên tiếp" có 2 vấn đề:
1. Dealer turn đầu hay **test/nghịch** bot (gõ "abc", emoji, im lặng) —
   không phải refusal thật. Hỏi 3 lần liên tiếp dồn dập làm dealer bực
   hoặc drop session.
2. Slot multi-field (1.1, 1.2, 2.1, 2.4, 2.5, 2.6, 3.3) dealer thường
   fill 1 phần. Engine cũ count vào retry → vô lý (dealer đã chia sẻ).

### Chọn

- **`MAX_RETRY_TOTAL = 3`** (tổng / session — giữ nguyên)
- **`MAX_RETRY_CONSECUTIVE = 2`** (mới — không hỏi quá 2 lần liên tiếp)
- Sau 2 lần liên tiếp REQUIRED chưa fill → action `DEFER`:
  - Gác slot, advance qua slot khác
  - Engine re-check sau `DEFER_RECHECK_AFTER_N_SLOTS = 2` slot
  - Khi dealer mood ok (intent ∈ {affirmative, normal}) → hỏi lại lần 3
  - Lần 3 vẫn không → SKIP + flag `required_missing`
- Slot multi-field partial fill → action `PARTIAL_RETRY`:
  - Ack field đã cho + hỏi field còn thiếu trong turn kế
  - **KHÔNG count `slot_attempts`**

### Rationale

- Phân bố 3 lần retry thông minh: 2 liên tiếp + 1 sau pause
- Phân biệt "test/nghịch" vs "refusal thật" qua intent detect
- PARTIAL_RETRY tôn trọng dealer đã chia sẻ 1 phần
- Action enum tăng từ 4 → 6 (thêm PARTIAL_RETRY + DEFER)

### Trade-off

- ❌ State machine phức tạp hơn (6 action thay 4)
- ❌ Engine phải track `consecutive_attempts` + `total_attempts` riêng
- ❌ DEFER có thể loop nếu re-check sai context — mitigation:
  `MAX_DEFER_PER_SLOT = 1` (1 slot chỉ defer 1 lần / session)

### Reconsider khi

- Pilot data: dealer Bận/Lửa Lò chấp nhận hỏi 3 lần liên tiếp ≥ 80% →
  có thể bỏ DEFER cho 2 nhóm này
- Implementation complexity quá cao → tạm bỏ DEFER Phase 1, dùng
  retry liên tiếp; add Phase 2

→ Refer F2A.4 step 2.6-2.8 + F2A.5 retry algorithm + 1A § 1.5-1.6 +
  GLOSSARY § Action (6 action).

---

## D12 — Flag enum 15 chia 4 nhóm (không phải 6 phẳng)

### Vấn đề

Phiên bản trước flag enum chỉ 6 phẳng (`prompt_injection`,
`abusive_language`, `garbage_input`, `dealer_declined`,
`required_missing`, `consent_unclear`). File 1C edge case + 2C admin
queue thật sự cần thêm 9 flag — nếu không, Pydantic raise runtime + 9
sự kiện không có flag tracking.

### Chọn: 15 flag chia 4 nhóm (Behavior / Abuse / Data quality / LLM guard)

| Nhóm | Flag | Mục đích |
|---|---|---|
| **Behavior (4)** | dealer_declined, required_missing, consent_unclear, multiple_refusal_in_row | Dealer chủ động từ chối / skip |
| **Abuse (5)** | prompt_injection, abusive_language, garbage_input, dealer_too_defensive, address_blacklist | Dealer vi phạm hoặc data nguy hiểm |
| **Data quality (4)** | sanity_check_failed, phone_invalid_after_retry, voice_quality_poor, brand_not_in_whitelist | Lỗi format / data chưa whitelist |
| **LLM guard (2)** | hallucinate, pii_leak | Bot lỗi (cần review LLM) |

### Rationale

- Admin queue trigger map theo nhóm → set priority hợp lý
  (LLM guard = HIGH security, Behavior = MEDIUM, ...)
- Filter UI admin: tab "abuse" tab "data quality" — không phải scroll list
- Mở rộng dễ: thêm flag mới chỉ cần add vào enum + map nhóm

### Trade-off

- ❌ 15 flag nhiều hơn 6 → maintenance: phải đảm bảo 1C + 2A + 2C +
  KE_HOACH sync
- ❌ Pilot có thể không trigger hết 15 flag — chưa biết nhóm nào dùng nhiều

### Reconsider khi

- Pilot run 1 tháng: nếu 3-4 flag không bao giờ trigger → cân nhắc xóa
- Nếu pattern mới phát sinh → thêm flag

→ Refer 2A F2A.3 enum + GLOSSARY § 4 + 2C F2C.8 trigger + KE_HOACH § 2.3.

---

**Lưu ý duy trì:** Khi có decision mới lớn (đổi tier mapping, đổi infra,
đổi flow chính) → **thêm 1 mục D13/D14/... vào file này** + bump version
+ log SYNC_LOG.
