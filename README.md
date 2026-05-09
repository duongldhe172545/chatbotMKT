# Em Linh MKT — Chatbot Dealer MVP

Chatbot voice/text thu data dealer ngành cửa/tủ bếp/VLXD cho Cộng Đồng Thợ 4.0.

**Trạng thái:** ~55% scope MVP. Có intake voice/text + extract LLM + Confirmation Card + admin + spam protection 4 layer + scope guard chống prompt injection.
**Chưa có:** Zalo OA, M365 Lists, Mini App + Community Routing, First Mission, KPI tracking.

---

## 1. Cài đặt local

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

## 2. Chạy local

```powershell
python -m app.main
```

| Truy cập từ | URL |
|-------------|-----|
| Cùng máy chạy server | http://127.0.0.1:8000 |
| Máy khác cùng WiFi (cần `HOST=0.0.0.0`) | http://<lan-ip>:8000 |
| Public HTTPS (mic work mọi nơi) | dùng ngrok — xem mục 7 |
| Production cloud | Railway — xem mục 8 |

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
│   ├── conversation.py    State machine 4 stage + ConversationService
│   ├── extractor.py       LLM extract DealerProfileRaw (chỉ trích field)
│   ├── replier.py         LLM sinh reply (Performer) — tách khỏi Extractor
│   ├── chat_replier.py    Free-form chat sau DONE
│   ├── card_renderer.py   Render Confirmation Card
│   ├── edit_parser.py     Regex parse "sửa X thành Y" — tiết kiệm LLM call
│   ├── red_flags.py       Detect SĐT giả, abuse, prompt injection
│   ├── intent_detect.py   is_tam_su / is_defensive / is_refusal
│   ├── address_form.py    Detect xưng hô anh/chị
│   ├── opener_enforcer.py Đa dạng cụm mở đầu (4 nhóm A/B/C/D)
│   ├── reply_guards.py    enforce_min_length + enforce_defensive_answer
│   ├── spam_guard.py      Layer 1+3+4+5 — quota / injection / trivial / mode
│   └── prompts.py         Greeting + system prompts (load playbook)
├── models/schema.py       Pydantic DealerProfileRaw + Session + flags
├── llm/
│   ├── base.py            LLMProvider interface
│   ├── claude.py          Anthropic + retry + logging
│   ├── gemini.py          Google Gemini (tương đương)
│   └── call_logger.py     Append logs/llm_calls.jsonl
├── storage/
│   ├── base.py            StorageAdapter interface
│   └── sqlite_store.py    SQLite + migration
└── playbook/              Domain knowledge load vào system prompt
    ├── 02_red_flags.md
    ├── 04_vn_language.md
    ├── 06_abbreviations_slang.md
    └── _legacy/           File cũ không load (giữ làm reference)

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
| Đổi sang Gemini (đã có) | — | `LLM_PROVIDER=gemini` |
| Đổi sang Haiku (rẻ hơn) | — | `LLM_MODEL=claude-haiku-4-5-20251001` |
| Lưu sang M365 List | `app/storage/power_automate_store.py` | `STORAGE_ADAPTER=power_automate` |
| Lưu Postgres | `app/storage/postgres_store.py` | `STORAGE_ADAPTER=postgres` |
| Nối Zalo OA | `app/channels/zalo.py` + endpoint webhook | thêm env Zalo token |

Logic `ConversationService` không thay đổi.

## 5. Edit playbook

Team product edit `.md` trong `app/playbook/` để chỉnh domain knowledge. Sau khi edit:

```powershell
# Restart server để load playbook mới
python -m app.main
```

LLM tự cập nhật hành vi.

## 6. Cost tracking

Mọi LLM call log vào `logs/llm_calls.jsonl`:

```json
{"ts":"2026-05-05T...","method":"extract_structured","model":"claude-sonnet-4-6","duration_ms":3421,"input_tokens":12345,"output_tokens":456,"success":true,"retry_count":0}
```

Đổi sang Haiku tiết kiệm ~3x cost (hiệu quả khi pilot >100 dealer).

## 7. Public HTTPS qua ngrok (test trên iPhone/Android)

```powershell
.\tools\ngrok.exe config add-authtoken <YOUR_TOKEN>
.\tools\ngrok.exe http 8000
```

URL HTTPS hiện ra → dùng cho mic work mọi nơi.

## 8. Deploy production qua Railway

### 8.1. Setup lần đầu

1. Tạo account tại https://railway.com
2. **New Project** → **Deploy from GitHub repo** → chọn repo này
3. Railway tự detect Python (qua `requirements.txt` + `Procfile`)

### 8.2. Cấu hình ENV variables (Railway dashboard → Variables)

```
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-4-6
STORAGE_ADAPTER=sqlite
SQLITE_PATH=data/dealers.db
HOST=0.0.0.0
USE_REPLIER=true
UVICORN_RELOAD=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<your-secret-password>
```

⚠️ **Lưu ý:**
- `HOST=0.0.0.0` bắt buộc cho Railway (mặc định 127.0.0.1 chỉ bind localhost trong container).
- KHÔNG set `PORT` — Railway tự inject `$PORT` env.
- KHÔNG bật `UVICORN_RELOAD=true` ở production.

### 8.3. Deploy

- `git push origin main` → Railway tự build + deploy
- Logs: Railway dashboard → service → Logs
- URL: Settings → Networking → "Generate domain" → cấp `*.up.railway.app`
- Custom domain: Settings → Networking → "Custom Domain" → trỏ CNAME

### 8.4. Lưu ý về data

⚠️ **Mặc định Railway KHÔNG có persistent volume.** Mỗi deploy mới = filesystem reset = `data/dealers.db` mất hết.

**3 cách giải quyết:**

**A) Chấp nhận fresh start (test phase):**
- Bỏ qua, đợi sau pilot mới quan tâm.

**B) Persistent Volume ($0.25/GB/tháng):**
- Railway dashboard → Service → Settings → Volumes → Mount `/app/data`
- Set `SQLITE_PATH=/app/data/dealers.db`

**C) Postgres add-on (free tier 1GB):**
- Railway dashboard → New → Database → PostgreSQL
- Tạo `app/storage/postgres_store.py` (chưa code)
- Set `STORAGE_ADAPTER=postgres`

## 9. Logs PII

Logger có filter tự động redact SĐT thành `[PHONE]` và email thành `xxx***@domain` trong stderr.

## 10. Test thủ công

1. Mở browser, app tự chào.
2. Trả lời tự nhiên (gõ hoặc bấm 🎤).
3. Bot gửi Confirmation Card → gõ "đúng" để chốt.
4. Mở `/admin` (login: admin / `<password trong .env>`) xem profile mới.
5. Sửa info bằng "sửa SĐT thành 0901234567" — regex parse, không tốn LLM.
