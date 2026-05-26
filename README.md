# Em Linh MKT - Chatbot Dealer

Chatbot voice/text thu thong tin dealer cua, nhom kinh, tu bep va VLXD cho Cong Dong Tho 4.0. Ung dung hien tai la FastAPI + static web UI, luu SQLite, goi Gemini theo 2 tier `LLM_FAST` va `LLM_QUALITY`.

## Trang thai

Da co:
- Intake voice/text qua `/api/chat`
- State machine theo stage `GREETING -> ASKING -> CONFIRMING -> DONE`
- Extract slot bang LLM + validator + merge profile
- Confirmation card, edit profile, admin view
- Guard prompt injection, hallucination, drift, abuse, rate limit
- Scheduler nudge/timeout cho confirmation

Chua co:
- Zalo OA webhook production
- M365 Lists / Postgres adapter production
- Mini App, community routing, KPI tracking

## Cai dat local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Mo `.env` va dien `GEMINI_API_KEY`.

## Chay local

```powershell
python -m app.main
```

Mac dinh server chay tai `http://127.0.0.1:8000`.

Endpoint chinh:
- `GET /` - chat UI
- `POST /api/chat` - chat runtime
- `GET /admin` - admin UI
- `GET /api/admin/*` - admin API, dung HTTP Basic
- `GET /health` - health check

## Cau hinh

`.env.example` duoc dong bo voi `app/config.py`.

Bien quan trong:
- `GEMINI_API_KEY`
- `LLM_FAST=gemini-2.5-flash`
- `LLM_QUALITY=gemini-2.5-pro`
- `SQLITE_PATH=data/chatbot.db`
- `HOST=127.0.0.1`
- `PORT=8000`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `SESSION_TIMEOUT_S`, `RATE_LIMIT_IP_PER_HOUR`, `RATE_LIMIT_MSG_PER_MINUTE`
- `SCHEDULER_ENABLED`, `SCHEDULER_SWEEP_INTERVAL_S`
- `SESSION_TIMEOUT_NUDGE_CARD_S`, `SESSION_TIMEOUT_CONFIRMING_S`

Runtime hien tai chi formalize Gemini. Khong co provider fallback an.

## Cau truc code

```text
app/
  main.py                 FastAPI entrypoint, lifespan, static mount
  config.py               Pydantic settings
  logging_setup.py        Logging + PII redaction
  api/
    chat.py               Chat endpoint
    admin.py              Admin endpoints
    health.py             Health endpoint
    labels_route.py       UI label endpoint
  core/
    conversation.py       Orchestrator stage-level
    _conv_greeting.py     GREETING handler
    _conv_asking.py       ASKING handler
    _conv_confirming.py   CONFIRMING handler
    _conv_done.py         DONE handler
    _conv_helpers.py      Ack, slot question, history helper
    state_machine.py      Slot transition decision
    card_renderer.py      Confirmation card renderer
    edit_parser.py        Confirming edit parser
    session.py            Session helpers
    scheduler.py          Background session sweep/nudge
  llm/
    base.py               Provider interface
    client.py             2-tier LLM client
    gemini.py             Gemini provider
    ack_generator.py      Slot ack generation
    system_prompt.py      Prompt builder
    extractors/           Slot tool schemas, runner, validators
  models/
    schema.py             DealerProfileRaw, SessionState
    enums.py              Stage, intent, action, flags
  slots/
    definitions.py        Slot metadata
    templates.py          Slot questions/retry templates
  storage/
    sqlite_store.py       SQLite store + migrations
  guards/                 Prompt, hallucination, drift, rewrite guards

static/
  index.html, chat.js, style.css
  admin.html, admin.js, admin.css

data/
  stt_corrections.json
  brand_whitelist.json
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Neu Windows chan ghi temp/cache, dat cac bien temp ve thu muc workspace truoc khi chay:

```powershell
$env:TEMP="$PWD\pytest_tmp"
$env:TMP="$PWD\pytest_tmp"
$env:PYTEST_ADDOPTS="-o cache_dir=$PWD\pytest_tmp\.pytest_cache"
.\.venv\Scripts\python.exe -m pytest -q
```

## Chay public de test mic

Web Speech API can HTTPS khi test tren may khac.

```powershell
.\tools\ngrok.exe http 8000
```

## Data va logs

- SQLite mac dinh: `data/chatbot.db`
- Log runtime ghi ra stderr theo config logging
- Local artifact nhu `__pycache__`, `.pytest_cache`, `pytest_tmp`, log local va DB test rong khong nen commit

## Deploy ghi chu

Khi deploy len Railway/container:
- Set `HOST=0.0.0.0`
- Khong hardcode `PORT` neu platform inject port rieng
- Dung persistent volume neu van muon luu SQLite qua moi lan deploy
- Dat password admin manh
