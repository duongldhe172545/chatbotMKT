# Em Linh MKT — Chatbot Dealer MVP

Chatbot voice/text thu data dealer ngành cửa/VLXD, theo workflow trong [EM_LINH_MKT_MVP_VOICE_INTAKE_DEALER_v01-1_1.md](EM_LINH_MKT_MVP_VOICE_INTAKE_DEALER_v01-1_1.md).

**Trạng thái:** ~40% scope MVP. Có intake voice/text + extract LLM + Confirmation Card + admin viewer.
**Chưa có:** Zalo OA, M365 Lists, Mini App + Community Routing, First Mission, KPI tracking. Xem [KE_HOACH_RA_SOAT_v01.md](KE_HOACH_RA_SOAT_v01.md) cho roadmap.

---

## 1. Cài đặt

```powershell
# 1. Tạo virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Cài thư viện
pip install -r requirements.txt

# 3. Cấu hình
copy .env.example .env
# Mở .env, điền ANTHROPIC_API_KEY=sk-ant-...
```

Lấy API key tại https://console.anthropic.com/ (cần nạp tối thiểu $5).

## 2. Chạy

```powershell
python -m app.main
```

| Truy cập từ | URL |
|-------------|-----|
| Cùng máy chạy server | http://127.0.0.1:8000 |
| Máy khác cùng WiFi (cần `HOST=0.0.0.0`) | http://<lan-ip>:8000 |
| Public HTTPS (mic work mọi nơi) | dùng ngrok — xem mục 7 dưới |

Mở Chrome hoặc Edge (Web Speech API yêu cầu).

## 3. Cấu trúc code

```
app/
├── main.py                FastAPI entrypoint + setup logging
├── config.py              Singleton factory cho LLM/Storage (env-driven)
├── labels.py              Source-of-truth cho mọi label tiếng Việt
├── logging_setup.py       Setup + PII redaction filter
├── api/
│   ├── chat.py            POST /api/chat — channel-agnostic
│   ├── admin.py           GET /api/admin/* — list profiles, sessions
│   └── labels_route.py    GET /api/labels — frontend fetch labels
├── core/
│   ├── conversation.py    State machine 4 stage
│   ├── extractor.py       LLM extract DealerProfileRaw
│   ├── chat_replier.py    Free-form chat sau DONE
│   ├── card_renderer.py   Render Confirmation Card
│   ├── edit_parser.py     Regex parse "sửa X thành Y" — tiết kiệm LLM call
│   ├── red_flags.py       Rule-based detect SĐT giả, abuse, prompt injection...
│   └── prompts.py         Greeting + system prompts (load playbook)
├── models/schema.py       Pydantic DealerProfileRaw + Session + flags
├── llm/
│   ├── base.py            LLMProvider interface
│   ├── claude.py          Anthropic + retry + logging
│   └── call_logger.py     Append logs/llm_calls.jsonl (timing + token)
├── storage/
│   ├── base.py            StorageAdapter interface
│   └── sqlite_store.py    SQLite + migration check tường minh
└── playbook/              9 file .md nạp vào system prompt LLM
    ├── 00_persona.md      Vai trò + xưng hô + cấm tiếng Anh
    ├── 01_principles.md   9 nguyên tắc vàng (ACK + WHY + ASK)
    ├── 01_scenarios.md    Edge cases A-N
    ├── 02_intake_flow.md  5 numbered steps
    ├── 02_red_flags.md    Hướng dẫn xử lý flag
    ├── 03_examples.md     Hội thoại mẫu
    ├── 04_vn_language.md  Bẫy chính tả + cụm chuẩn
    ├── 06_abbreviations_slang.md  Viết tắt + lóng VN
    └── 07_unknown_cases.md  Framework 6 nhóm A-F cho input lạ

static/
├── index.html
├── chat.js                Web Speech + typing rotating + double-submit guard
├── style.css
├── admin.html
├── admin.js               Fetch labels từ /api/labels
└── admin.css

data/dealers.db            SQLite tự sinh
logs/llm_calls.jsonl       Auto-append mỗi LLM call (cho cost tracking)
```

## 4. Mở rộng về sau (adapter pattern)

| Việc | Thêm file | Đổi env |
|------|-----------|---------|
| Đổi LLM sang Gemini | `app/llm/gemini.py` | `LLM_PROVIDER=gemini` |
| Đổi sang Haiku (rẻ hơn) | (đã sẵn) | `LLM_MODEL=claude-haiku-4-5-20251001` |
| Lưu sang M365 List qua Power Automate | `app/storage/power_automate_store.py` | `STORAGE_ADAPTER=power_automate` |
| Nối Zalo OA | `app/channels/zalo.py` + endpoint webhook | thêm env Zalo token |
| STT server-side (Whisper) | `app/stt/whisper_local.py` | `STT_PROVIDER=whisper_local` |

Logic `ConversationService` không thay đổi.

## 5. Luật khóa MVP (mục 26 file gốc) — đã tuân

- ✅ Không tạo `Dealer_ID` chính thức — chỉ ghi `review_status='RAW'`
- ✅ Không lưu profile nếu chưa `confirmation_status='CONFIRMED'`
- ✅ Tối đa 5 cụm câu intake, skip sau 2 lần hỏi không trả lời
- ✅ Không bắt gõ form dài — voice/chat tự nhiên
- ✅ Red flags rule-based: SĐT giả, abuse, prompt injection, escalation

## 6. Edit playbook

Team product/marketing edit `.md` trong `app/playbook/` để chỉnh tone/scenarios. Sau khi edit:

```powershell
# Restart server để load playbook mới
# Ctrl+C dừng, rồi:
python -m app.main
```

LLM tự cập nhật hành vi.

## 7. Public HTTPS qua ngrok (cho test trên iPhone/Android)

```powershell
.\tools\ngrok.exe config add-authtoken <YOUR_TOKEN>
.\tools\ngrok.exe http 8000
```

URL HTTPS hiện ra → dùng cho mic work mọi nơi (iOS Safari WebKit hơi chập chờn nhưng OK).

## 8. Cost tracking

Mọi LLM call log vào `logs/llm_calls.jsonl`:

```json
{"ts":"2026-05-05T...","method":"extract_structured","model":"claude-sonnet-4-6","duration_ms":3421,"input_tokens":12345,"output_tokens":456,"success":true,"retry_count":0}
```

Tính cost (Sonnet 4.6: $3/1M input, $15/1M output):
```powershell
# Quick check trong PowerShell
type logs\llm_calls.jsonl | ConvertFrom-Json | Measure-Object input_tokens -Sum
```

Đổi sang Haiku tiết kiệm ~3x cost (hiệu quả khi pilot >100 dealer).

## 9. Logs PII

Logger có filter tự động redact SĐT thành `[PHONE]` và email thành `xxx***@domain` trong stderr. Xem [app/logging_setup.py](app/logging_setup.py).

## 10. Test thủ công

1. Mở browser, app tự chào.
2. Trả lời tự nhiên 5 cụm câu (gõ hoặc bấm 🎤).
3. Bot gửi Confirmation Card → gõ "đúng" để chốt.
4. Mở `/admin` xem profile mới + flag.
5. (Tuỳ chọn) Sửa info bằng "sửa SĐT thành 0901234567" — regex parse, không tốn LLM.

## 11. Bảo mật

Xem [SECURITY.md](SECURITY.md) — threat model, rotate API key, checklist trước khi share LAN.
