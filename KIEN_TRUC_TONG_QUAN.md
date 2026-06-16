# KIẾN TRÚC & LUỒNG HOẠT ĐỘNG — Em Linh MKT Chatbot

> Bản đồ tổng quan để nhìn 1 phát hiểu toàn hệ. Cập nhật 2026-06-12.

## 1. KIẾN TRÚC TẦNG (folder → vai trò)

```
HTTP request
   │
┌──▼─────────────────────────────────────────────────────────┐
│ app/api/         — FastAPI routes (routes_v2 = chat, admin_v2 = admin) │
│ app/main_v2.py   — app factory, CORS, error handler, threadpool        │
│ app/guards/      — rate_limit (per session), injection (regex)         │
└──┬─────────────────────────────────────────────────────────┘
┌──▼─────────────────────────────────────────────────────────┐
│ app/services/    — TẦNG ĐIỀU PHỐI                                       │
│   chat_service    = nhạc trưởng 1 lượt chat (3 transaction ngắn)        │
│   session_service = tạo/auth/hydrate session                            │
│   profile_service = đọc/ghi field + auto-derive + flag                  │
│   serializers     = DB rows → JSON                                      │
└──┬─────────────────────────────────────────────────────────┘
┌──▼─────────────────────────────────────────────────────────┐
│ app/parlant/     — BỘ NÃO HỘI THOẠI (3 bước)                            │
│   turn_processor  = pipeline 1 lượt                                     │
│   workflow_engine = QUYẾT objective (code thuần, KHÔNG LLM)             │
│   context_builder = gom ngữ cảnh + task cho LLM                         │
│   agent           = sinh reply (stub | gemini) + gắn card               │
│   observation_detector = intent + xưng hô + tâm trạng                   │
│   guideline_registry / canned_responses = luật + câu mẫu (YAML)         │
└──┬─────────────────────────────────────────────────────────┘
┌──▼─────────────────────────────────────────────────────────┐
│ app/llm/         — GỌI LLM                                              │
│   gemini / client = provider + tier routing + semaphore 50             │
│   intake_fact_extractor = prompt TRÍCH XUẤT (field + intent)           │
│   extractors/validators = 27 validator/field   extractors/schemas      │
│   auto_derive / address_llm / local_hook = derive phụ                  │
└──┬─────────────────────────────────────────────────────────┘
┌──▼─────────────────────────────────────────────────────────┐
│ app/core/        — LUẬT & TIỆN ÍCH                                      │
│   rules (load rules.yaml) · validators · card_renderer · sanity        │
│   config_v2 (env) · address_parser · regex_markers · md_exporter       │
│ app/models/      — DealerProfileRaw (40 field) + enums                  │
│ app/slots/       — 17 slot ↔ field mapping + template câu hỏi           │
│ config/*.yaml    — rules / guidelines / canned (LUẬT ngoài code)        │
└──┬─────────────────────────────────────────────────────────┘
┌──▼─────────────────────────────────────────────────────────┐
│ app/db/          — connection (WAL + 3 tx) · store (CRUD) · schema (DDL)│
│ SQLite (/data)   — 15 bảng; profile_fields lưu theo ROW (1 field/dòng)  │
└─────────────────────────────────────────────────────────────┘
```

## 2. LUỒNG 1 LƯỢT CHAT (POST /sessions/{id}/messages)

```
routes_v2.send_text_message
  → auth (token) · rate-limit/session · idempotency check
  → ChatService.send_text_message:
      TX1 (write ~ms): ghi tin user + đọc 100 tin gần + session
      ── ngoài lock ── detect_observations (intent skip/confirm)  [có thể +1 LLM]
      TX2 (write ~ms): ghi skip/confirm + đọc profile_snapshot
      ── ngoài lock ── TurnProcessor.process:
           1. pre-guard (injection — hiện chỉ FLAG, chưa chặn)
           2. ① LLM TRÍCH XUẤT  → field + intent + observations
           3. merge field vào snapshot (in-memory) + guard brandkit-choice
           4. ② WORKFLOW (code) compute_objective → hỏi gì tiếp
           5. match guideline → canned? (gemini chỉ canned cho greeting)
           6. ③ LLM TRẢ LỜI (build_system_prompt + gemini) + gắn card nếu review
           7. guard chốt-sớm (retry → fallback stub)
           8. post-guard (cắt emoji >2, sửa anh→chị)
      TX3 (write ~ms): validate + lưu field + auto-derive + ghi turn + reply
  → TX4: lưu idempotency
```
**Then chốt:** LLM làm 2 việc (trích xuất + diễn đạt); **code (Workflow Engine) quyết "hỏi gì tiếp"**, không phải LLM.

## 3. WORKFLOW ENGINE — thứ tự ưu tiên objective
`compute_objective()`: **cờ chặn** → **field bắt buộc thiếu** (tên→cửa hàng→địa chỉ→SĐT→sản phẩm→mô hình) → **optional** (đội thợ→hãng→kênh→FB→khách cũ→địa bàn→lưu khách→nút thắt→thanh toán→bảo hành) → **brandkit** (consent→logo intent→màu→phong cách→slogan) → **review card** → **zalo handoff**.
→ Field bắt buộc thiếu thì KHÔNG đi tiếp được (tự enforce).

## 4. DỮ LIỆU
- `DealerProfileRaw`: 6 REQUIRED + ~20 OPTIONAL + 6 RAW-signal (nuôi 9 tiêu chí C1-C9) + ~12 derived.
- `profile_fields` ROW model (field_name, raw_value, normalized_value, status, version) → audit dễ, thêm field không cần ALTER.
- 9 tiêu chí C1-C9 = nhặt từ các signal field, chấm ở backend riêng (ngoài chatbot).

---

## 5. LỖI / BẤT HỢP LÝ — ĐÃ VERIFY (lọc khỏi báo cáo 4 agent)

### ✅ CONFIRMED (đã đọc tận code):
| # | Lỗi | Vị trí | Mức | Ghi chú |
|---|---|---|---|---|
| A | **SĐT sai làm kẹt luồng** | resolve_blocking_flag task chung (§Phase 10.1) | 🔴 | đã có plan |
| B | **Admin ẩn trường cơ bản rỗng** | [admin.js:325](static/admin.js#L325) (§10.2) | 🔴 | đã có plan |
| C | **rules.yaml `rules:` LẶP key ở slot 2.4 + 2.6** → mất luật "Chỉ hỏi 1 câu" (P4.10) | [rules.yaml:102-106](config/rules.yaml#L102), [117-121](config/rules.yaml#L117) | 🔴 | **MỚI** — YAML lấy list sau, list đầu bị nuốt |
| D | **admin session-list gán sai dealer_type** = `logo_issued_status` | [admin_v2.py:156](app/api/admin_v2.py#L156) | 🟡 | **MỚI** — list admin hiện nhãn tone từ trạng thái logo (vô nghĩa) |
| E | "ốt đo"≠Austdoor: không có từ điển hãng | validate_supplier_brands (§10.3) | 🟡 | đã có plan |
| F | est_team_size "vài ba" bị loại (§10.4) | validators.py:151 | 🟡 | đã có plan |
| G | Chốt sớm khi chửi (§10.5) | turn_processor:47 | 🟡 | đã có plan |
| H | injection guard chỉ FLAG, không chặn/sanitize | [turn_processor.py:_pre_turn_guards](app/parlant/turn_processor.py) (guards/injection.py có sẵn nhưng không gọi) | 🟡 | bảo mật |
| I | Dead code: `show_logo_brief` (workflow không bao giờ trả) + check state LOGO_READY/PENDING | agent.py / turn_processor:201 | 🔵 | dọn |
| J | `_BRANDKIT_CHOICE_FIELDS` định nghĩa 2 nơi (chat_service + turn_processor) | DRY | 🔵 | gộp |

### ❌ ĐÃ LOẠI (agent báo nhưng SAI / cố ý):
- "Rate-limit theo session không theo IP" → **CỐ Ý** (sự kiện chung WiFi = chung IP, limit IP sẽ chặn nhầm khách thật). Không sửa.
- "serializers thiếu brandkit_consent trong REQUIRED" → **KHÔNG phải bug**: brandkit_consent được enforce riêng ở nhánh brandkit của workflow, không thuộc nhóm required cơ bản.
- "slot 4.0 thiếu dấu `-`" → SAI (đọc lại: dấu `-` đầy đủ).
- "phone regex sai format 84" → thực tế số thật vẫn đúng; "023941212" bị loại là ĐÚNG. Lỗi nằm ở XỬ LÝ sau loại (A), không phải validator.
- "C4 bảo hành luôn null do thiếu template" → SAI (slot 3.5 có trong OPTIONAL_FIELDS_PRIORITY, transcript trước bot có hỏi bảo hành).

→ **2 bug MỚI cần thêm vào Phase 10: C (duplicate YAML key) + D (admin dealer_type).** Và mở rộng test YAML để bắt cả duplicate-key (hiện chỉ bắt dict).
