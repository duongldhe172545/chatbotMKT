# ĐÁNH GIÁ APPROACH TÀI LIỆU — Em tự phán xét

> **Mục đích:** Em (Claude) tự đánh giá lại approach tài liệu mình đã
> đề xuất (CORE + 6 file 1A/1B/1C/2A/2B/2C + SYNC_LOG) bằng cách đối
> chiếu với industry standard. Tự critique để Duong biết chỗ nào
> tốt / chỗ nào over-engineered / chỗ nào thiếu.
>
> **Audience:** Duong + AI khác đọc cross-validate.

---

## VERSION

| Ngày | Version | Note |
|---|---|---|
| 2026-05-14 | v1.0 | Đánh giá lần đầu sau research |

---

## TL;DR (Bottom line)

**Approach hiện tại của em:** 7/10. Đúng spirit industry standard,
nhưng quá chi tiết cho 1 dự án pilot.

- ✅ **Tốt:** Cấu trúc 2-tier (behavioral 1A/1B/1C + technical 2A/2B/2C)
  + versioning + cross-ref + disclaimer "examples only" — match đúng
  best practice của BDD/Specification by Example và arc42.
- ⚠️ **Over-engineered:** Volume ~3000 dòng spec cho 1 chatbot intake
  pilot. Anthropic best practice: system prompt như "onboarding doc"
  cho LLM — không cần volume này.
- ❌ **Thiếu:** Không có "Glossary" rõ + không có "Architecture
  Decision Records" (ADR) + không có "Acceptance Criteria" dạng
  Gherkin (Given-When-Then) để LLM/test parse.
- 🔄 **Đề xuất adjust:** Giữ 6 file nhưng compress mỗi file ≤ 50%
  volume hiện tại + thêm 1 file Glossary + thêm 1 folder ADR/ +
  thêm Gherkin scenarios cho acceptance test.

---

## PHẦN 1 — Approach hiện tại của em (recap)

```
EM_LINH_MKT_CORE.md          (v3.0.0)  — principles + structure
SYNC_LOG.md                  (v1.0.0)  — versioning + sync rule
KE_HOACH_REFACTOR.md         (v1.0)    — refactor plan

RULE_KICH_BAN/
├── KICH_BAN_1A_core.md      (v0.2.0)  — 17 slot Q&A script (behavioral)
├── KICH_BAN_1B_tone.md      (v0.1.0)  — 4 nhóm tone library (behavioral)
├── KICH_BAN_1C_edgecase.md  (v0.1.0)  — 12 edge case (behavioral)
├── LUAT_2A_core.md          (v0.2.0)  — state machine + schema (technical)
├── LUAT_2B_llm.md           (v0.1.0)  — prompt + extractor (technical)
└── LUAT_2C_infra.md         (v0.1.0)  — storage + monitoring (technical)
```

**Quy ước:**
- File 1A ↔ 2A, 1B ↔ 2B, 1C ↔ 2C (module pair)
- Semver + cross-ref tables
- Disclaimer toàn cục "examples only, engine cover shape tương tự"
- "Acceptance test" trong mỗi rule (kiểu informal)

---

## PHẦN 2 — Đối chiếu industry standard

### 2.1 Có đối chiếu với arc42 (architecture documentation chuẩn)

[arc42](https://docs.arc42.org/home/) là template architecture chuẩn
12 sections, dùng phổ biến cho LLM applications. Đối chiếu:

| arc42 section | Em có cover? | Ở đâu |
|---|---|---|
| 1. Introduction & Goals | ✅ Có | CORE § A (triết lý), § B.1 (persona) |
| 2. Constraints | ⚠️ Phân tán | CORE § E (ranh giới), § J (luật khóa) — không tập trung |
| 3. Context & Scope | ⚠️ Thiếu rõ | CORE § F (domain knowledge) — nhưng không vẽ context diagram |
| 4. Solution Strategy | ❌ **THIẾU** | Không có file giải thích "why slot 1.1→4.2", "why 4 stage forward-only" |
| 5. Building Block View | ✅ Có | File 2A (modules + relationships), KE_HOACH_REFACTOR § 3 |
| 6. Runtime View | ✅ Có | File 2A § F2A.1 (stages transition) + § F2A.4 (smart advance) |
| 7. Deployment View | ⚠️ Thiếu | File 2C § F2C.1 (storage) + § F2C.6 — chưa có deployment topology rõ |
| 8. Crosscutting Concepts | ✅ Có | Disclaimer toàn cục, cross-ref tables |
| 9. Architecture Decisions | ⚠️ **PARTIAL** | Đã có `0_STRATEGY.md` D1-D8 (vì sao SQLite, vì sao model-agnostic, vì sao tách Scoring service, ...). Chưa có ADR riêng tách file nhưng đủ cho pilot. |
| 10. Quality | ⚠️ Phân tán | Acceptance test trong từng rule — không tổng hợp quality scenarios |
| 11. Risks & Technical Debt | ⚠️ Phân tán | KE_HOACH_REFACTOR § 6 (risk) — nhưng không trong spec |
| 12. Glossary | ❌ **THIẾU** | Không có file "thuật ngữ" — vd "slot vs turn", "REQUIRED vs OPTIONAL", "tier" (nội bộ) |

**Verdict:** Em cover 5/12 đầy đủ, 4/12 phân tán/thiếu rõ, 3/12 thiếu
hoàn toàn (Solution Strategy / ADR / Glossary).

→ **Hành động đề xuất:** thêm 3 file:
- `RULE_KICH_BAN/0_GLOSSARY.md` — thuật ngữ
- `RULE_KICH_BAN/0_STRATEGY.md` — solution strategy
- `RULE_KICH_BAN/ADR/` — folder chứa decision records (1 file/decision)

### 2.2 Đối chiếu với Conversation Design (PatternFly)

[PatternFly Conversation Design](https://www.patternfly.org/patternfly-ai/conversation-design/)
nêu 5 nguyên tắc cốt lõi cho chatbot:

| PatternFly principle | Em có cover? | Ở đâu |
|---|---|---|
| 1. Transparency (disclose AI use) | ⚠️ Mâu thuẫn | File 1C § 6 nói "KHÔNG tự xưng bot/AI" — vi phạm transparency? |
| 2. Clarity (brief, consistent) | ✅ Có | File 1B § 2 (tone matrix 4 nhóm) |
| 3. User Value (frame in terms of value) | ✅ Có | File 1A § 4 retry table có "explain lý do cần" |
| 4. Privacy (tell users why) | ✅ Có | File 1B § 2.3 (Lo) — cam kết bảo mật cụ thể |
| 5. Control (user has last word) | ⚠️ Phân tán | File 1A § 5 (refusal handler) — đúng spirit nhưng không tập trung 1 chỗ |

**Verdict:** Em cover 3/5 rõ, 2/5 có vấn đề.

⚠️ **Vấn đề transparency:** Spec em viết "KHÔNG tự xưng bot/AI/model".
Đây là MÂU THUẪN với industry standard. Đại lý hỏi "em là bot à?" mà
bot lảng tránh = vi phạm transparency. Có thể fix bằng cách:
- Cho phép bot nói "em là chatbot, đằng sau có team người thật"
- Thay vì lảng tránh hoàn toàn

→ Em recommend update File 1C § 6 + File 1B § 2.3.

### 2.3 Đối chiếu với BDD / Specification by Example (Gherkin)

[BDD Gherkin Guidelines for AI](https://automationpanda.com/2026/04/27/bdd-gherkin-guidelines-for-ai-coding-and-testing/)
nói: "AI coding agents create effective Gherkin scenarios when provided
clear rules. Without explicit rules, AI-generated Gherkin drifts into
vague Then steps."

Approach em hiện tại:
- Em viết "Acceptance test" trong mỗi rule (vd F2A.4 § Acceptance test)
- Định dạng: text + disclaimer + 1 case ví dụ + "tổng quát hóa pattern"
- **KHÔNG dùng Given-When-Then chuẩn**

So với Gherkin chuẩn:
```gherkin
Scenario: Slot OPTIONAL với "không biết" → SKIP NGAY
  Given current_slot = "4.2" (color_accent, OPTIONAL)
  And bot vừa hỏi "Anh thích màu nào?"
  When dealer trả lời "không biết phong thủy"
  Then action = SKIP
  And slot 4.2 không retry
  And flag += "dealer_declined"
  And next_slot = next trong SLOT_PRIORITY_ORDER
```

**Verdict:** Em viết acceptance test informal, không Gherkin. **Tốt
hơn** nếu chuyển sang Gherkin vì:
- Dev viết test code parse được trực tiếp (test framework `behave` /
  `pytest-bdd`)
- AI khác (Claude code Phase 1) hiểu rõ hơn — case rõ ràng, không
  ambiguous
- Specification by Example principle: "concrete examples in domain
  language" — Gherkin chính là format này

→ **Hành động đề xuất:** Convert "Acceptance test" trong File 2A/2B/2C
sang Gherkin. Effort ≈ 1 ngày.

### 2.4 Đối chiếu với Rasa domain.yml (chatbot framework chuẩn)

[Rasa Domain](https://rasa.com/docs/reference/primitives/slots/) cấu
trúc domain file:

```yaml
intents:
  - greet
  - inform_name
  - deny
slots:
  owner_name:
    type: text
    influence_conversation: false
    mappings:
      - type: from_entity
        entity: name
        intent: inform_name
responses:
  utter_ask_owner_name:
    - text: "Cho em xin tên anh ạ?"
forms:
  intake_form:
    required_slots:
      - owner_name
      - dealer_name
      - address
```

So với em:
| Rasa concept | Em map về |
|---|---|
| `intents:` | File 2A § F2A.2 (7 intent) — gần giống |
| `slots:` | File 2A § F2A.3 (Scope 1 fields) + File 2A § F2A.5 — gần giống |
| `responses:` | File 1A § 4 (templates per slot) — gần giống |
| `forms:` (required_slots) | File 2A § F2A.5 (REQUIRED list) — đúng |
| `stories:` (training conversation) | **KHÔNG có** — em không viết stories |
| `rules:` (deterministic flows) | File 2A § F2A.4 (state machine) — giống rules |

**Verdict:** Approach em **gần khớp Rasa** về cấu trúc concept (intent /
slot / form / response / rule). **Thiếu** "stories" = training
conversation example.

→ **Hành động đề xuất:** Thêm file `RULE_KICH_BAN/STORIES/` chứa 5-10
conversation transcript mẫu (happy / defensive / tâm sự / abuse) cho
LLM học pattern. Không bắt buộc Phase 1.

### 2.5 Đối chiếu với Anthropic prompt engineering (LLM-native)

[Anthropic best practice](https://www.buildmvpfast.com/blog/system-prompt-design-best-practices-llm-instructions-engineering-2026)
framing: "LLM là employee mới — system prompt là onboarding doc."

System prompt em đang viết (CORE + File 1B + File 2B):
- Volume: ~3000 dòng total
- **Quá dài** cho 1 LLM context window
- LLM Phase 1-3 dev đọc PHẢI focus vào 1-2 rule cụ thể, không phải toàn spec

So với best practice "onboarding doc cho new employee":
- New employee không đọc 3000 dòng cùng lúc → đọc per topic
- Onboarding tốt: 1 page overview + chi tiết theo task
- **Em có CORE (overview) — OK** nhưng CORE đã 600 dòng (quá dài)

→ **Hành động đề xuất:** Compress CORE từ 600 → 200 dòng. Detail đẩy
sang file con (1A/1B/.../2C). CORE chỉ giữ:
- Triết lý 1 câu
- Persona 1 paragraph
- 4 stage tóm tắt
- 17 slot list (chỉ id + tên, không detail)
- Schema 4 scope (chỉ list field, không type)
- Pointer tới file con

---

## PHẦN 3 — Tổng kết phân tích phản biện

### 3.1 Chỗ tốt (giữ nguyên)

| ✅ Tốt | Lý do |
|---|---|
| Phân tách behavioral (1A/B/C) vs technical (2A/B/C) | Đúng spirit "spec for stakeholder vs spec for dev" — chuẩn arc42 split |
| Semver + SYNC_LOG | Versioning chuẩn industry, đúng "Living Documentation" |
| Disclaimer "examples only" | Đúng BDD principle "examples drive specification, not replace it" |
| Cross-ref tables giữa các file | Đúng "Linked Documentation" pattern |
| 4 dealer type detection + ack pattern khác nhau | Đúng "personalization" PatternFly principle |
| Tone library tách riêng (1B) | Đúng pattern "Content Style Guide" của conversation design |
| Edge case + escalation tách riêng (1C) | Đúng pattern "fault tolerance design" |
| Schema 4 scope + sanity check 5-point | Đúng "Data Boundaries" pattern + validation gate |
| Guards (injection/hallucinate/drift/PII) | Đúng "Defense in Depth" |
| Versioning cho data files | Đúng "Configuration as Code" |

### 3.2 Chỗ over-engineered (giảm bớt)

| ⚠️ Over | Vì sao | Đề xuất |
|---|---|---|
| Volume ~3000 dòng cho pilot | 1 dev + 1 Claude, không phải team 10 người | Compress mỗi file ≤ 50% |
| 8 rule F2A + 8 rule F2B + 8 rule F2C | Spec mỗi rule có Yêu cầu / Algorithm / Tham số / Acceptance test / Constraint / Pointer / Cross-ref — quá nhiều bullet | Gộp 24 rule thành 12 rule (1 rule cover 2 concept gần nhau) |
| PROVINCE_SPECIALTY_TABLE 50 tỉnh hardcode trong file 2A | Data nên ở data file | Move sang `data/province_specialty.json` (em đã plan trong KE_HOACH_REFACTOR) |
| Mỗi rule có 4-6 acceptance test text | Test informal, không executable | Convert sang Gherkin (executable) |
| File 2C § F2C.6 monitoring (Prometheus + Grafana) | Pilot < 100 dealer/ngày — Prometheus overkill | Defer Phase 5 (KE_HOACH_REFACTOR đã note) |
| File 2C § F2C.3 concurrency Redis lock | Phase 1-3 dùng in-memory đủ | Phase 4 mới Redis (đã note) |

### 3.3 Chỗ thiếu (bổ sung)

| ❌ Thiếu | Vì sao quan trọng | Đề xuất |
|---|---|---|
| Glossary | "Slot vs turn vs field" — 3 từ dev/LLM confuse được | Tạo `0_GLOSSARY.md` (≤ 100 dòng) |
| ADR (Architecture Decision Records) | "Vì sao chọn SQLite?" — sau 6 tháng không ai nhớ | Tạo folder `ADR/` 1 file/decision |
| Solution Strategy section | "Vì sao 4 stage forward-only?" — rationale cho design choice | Tạo `0_STRATEGY.md` (~200 dòng) |
| Gherkin acceptance test | LLM/test framework parse executable | Refactor "Acceptance test" trong File 2A/B/C sang Gherkin |
| Context diagram (Building Block View) | Vẽ system context (web client → bot → DB → LLM API) | Thêm mermaid diagram trong CORE hoặc 0_STRATEGY |
| Stories (conversation transcript mẫu) | Training material cho LLM + tester | Tạo `STORIES/` folder 5-10 transcript |
| Transparency policy rõ | Mâu thuẫn với File 1C § 6 hiện tại | Update File 1C § 6 — cho phép tự nhận chatbot, có team người thật phía sau |
| Quality scenarios tập trung | Phân tán trong từng rule | Tạo `0_QUALITY.md` tập hợp |

### 3.4 Đánh giá tổng — score 7/10

| Tiêu chí | Score | Note |
|---|---|---|
| Cover scope đầy đủ (functional) | 9/10 | Cover hết slot + intent + state machine + edge case |
| Cover scope đầy đủ (non-functional) | 7/10 | Có monitoring + spam guard nhưng phân tán |
| Theo industry standard | 7/10 | Có 2-tier + versioning + cross-ref. Thiếu ADR + Glossary + Gherkin |
| Phù hợp scale dự án | 6/10 | **Over-engineered** cho 1 dev pilot |
| LLM-friendly (Claude code đọc dễ) | 7/10 | Có Pointer implementation. Thiếu Gherkin (LLM hiểu Gherkin tốt hơn freeform text) |
| Maintainability | 8/10 | Semver + SYNC_LOG + cross-ref đầy đủ |
| Onboarding mới (dev mới đọc 1 ngày hiểu được) | 5/10 | 3000 dòng quá nhiều, cần overview |
| Decision rationale (vì sao chọn X?) | 4/10 | Thiếu ADR — sau này không ai nhớ |
| **TOTAL** | **6.6/10** | Tốt spirit, cần adjust volume + bổ sung 3 artifact |

---

## PHẦN 4 — Hành động đề xuất (5 task)

| # | Task | Effort | Priority |
|---|---|---|---|
| 1 | Tạo `RULE_KICH_BAN/0_GLOSSARY.md` (~100 dòng) — thuật ngữ slot/turn/scope/dealer_type/etc. | 0.5 ngày | HIGH |
| 2 | Tạo `RULE_KICH_BAN/0_STRATEGY.md` (~200 dòng) — solution strategy + architecture rationale | 1 ngày | HIGH |
| 3 | (Optional khi scale) Tách `0_STRATEGY.md` D1-D8 thành ADR riêng `RULE_KICH_BAN/ADR/00X-*.md` — chuẩn format MADR. Pilot tạm để gộp trong STRATEGY. | 1 ngày | LOW (defer) |
| 4 | Refactor "Acceptance test" trong File 2A/2B/2C → Gherkin format | 1-2 ngày | MEDIUM (P1 dev cần) |
| 5 | Update File 1C § 6 + File 1B § 2.3 transparency policy | 0.5 ngày | HIGH (vi phạm chuẩn) |

**Tổng:** 4-5 ngày — làm SONG SONG với Phase 1 refactor, không block.

---

## PHẦN 5 — Self-critique về self-critique này

**Em có thể bias gì khi tự đánh giá?**

1. **Over-confidence:** Em viết spec → tự đánh giá → có thể không thấy
   được điểm dở thật sự. Giải pháp: cross-validate bằng AI khác (xem
   `BOI_CANH_DU_AN.md`).

2. **Confirmation bias trong search:** Em search "chatbot specification
   best practice" → kết quả có thể skew về "phải document chi tiết".
   Search ngược lại "lean documentation chatbot" có thể ra kết quả
   khác (less is more).

3. **Em chỉ tham khảo 5-6 nguồn:** arc42 + PatternFly + BDD + Rasa +
   Anthropic. Không cover hết (vd: Google Dialogflow CX, Microsoft Bot
   Framework Composer, IBM Watson Assistant).

4. **Em có thể đánh giá CAO cho việc viết spec** vì em là LLM — LLM
   được train trên data dev/docs, có thể overvalue documentation.
   Reality check: nhiều startup pilot không viết spec dài thế này.

5. **Vietnam context:** Em không research kỹ "Vietnam startup
   documentation practice" — có thể team Vietnam thường ít formal
   hơn, dùng Notion/Google Docs đơn giản hơn arc42.

→ **Lời khuyên:** Duong nên đọc `BOI_CANH_DU_AN.md` + hỏi AI khác (vd
ChatGPT, Gemini) câu hỏi tương tự. So 2 đánh giá để có view cân bằng.

---

## NGUỒN THAM KHẢO

- [arc42 Documentation](https://docs.arc42.org/home/) — 12-section
  template chuẩn architecture
- [PatternFly Conversation Design](https://www.patternfly.org/patternfly-ai/conversation-design/) —
  5 nguyên tắc cốt lõi chatbot UX
- [BDD Gherkin Guidelines for AI](https://automationpanda.com/2026/04/27/bdd-gherkin-guidelines-for-ai-coding-and-testing/) —
  Gherkin specification by example
- [Rasa Domain Structure](https://rasa.com/docs/reference/primitives/slots/) —
  intent / slot / form / response / rule pattern
- [System Prompt Design Best Practices](https://www.buildmvpfast.com/blog/system-prompt-design-best-practices-llm-instructions-engineering-2026) —
  Anthropic "onboarding doc" framing
- [Designing intelligent chatbots — Frontiers AI](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1618791/full) —
  framework design + UX best practice
- [Specification by Example with AI](https://urgo.medium.com/using-specification-by-example-to-drive-ai-95c19f0bb4ec) —
  AI hiểu concrete examples > abstract generalisations
- [LangChain Context Engineering](https://docs.langchain.com/oss/python/langchain/context-engineering) —
  context engineering = "number one job of AI Engineers"
- [Conversation Design Institute](https://www.conversationdesigninstitute.com/topics/best-practices) —
  best practice conversation design
- [Awesome arc42 Copilot (GitHub)](https://github.com/MSiccDev/awesome-arc42-copilot) —
  LLM prompts cho arc42 documentation
