# Em Linh MKT - Parlant-style Chatbot v2

Chatbot tư vấn chiến lược kinh doanh và intake thông tin đại lý cửa, nhôm kính, tủ bếp và VLXD Việt Nam.

Hệ thống được thiết kế theo kiến trúc **Parlant-style** tự phát triển (Phase 1-7), thay thế toàn bộ state machine dạng slot-locked cũ bằng cơ chế declarative/objective-driven, quản lý hành vi qua guidelines và ghi nhận vết xử lý (trace logs) đầy đủ.

---

## 1. Tính năng cốt lõi (V2)

* **Pipeline Turn Xử Lý Tuyến Tính**: Xử lý tin nhắn qua 8 bước chặt chẽ:
  1. *Pre-turn guards*: Chống prompt injection, phát hiện input rác/garbage, phát hiện lăng mạ.
  2. *Extraction*: Trích xuất dữ liệu thô (facts) bằng Regex + LLM.
  3. *Validation*: Kiểm tra dữ liệu (SĐT, địa chỉ blacklist, tên, v.v.).
  4. *Merge & Derive*: Hợp nhất thông tin vào hồ sơ (profile) + tự động suy diễn địa lý (tỉnh, huyện), tên hotline, vai trò.
  5. *Objective Compute*: Quyết định nhiệm vụ tiếp theo dựa trên trạng thái hồ sơ (Journeys).
  6. *Context Build & Guidelines Match*: Match các guidelines nghiệp vụ dựa trên observations (Bận, Lo, Khoe, Lửa Lò).
  7. *Agent Reply Generation*: Gọi LLM với ngữ cảnh (context variables) sinh 1 câu trả lời tự nhiên gắn liền canned responses.
  8. *Post-turn guards*: Chống lặp từ, sửa đổi lỗi dấu câu, loại bỏ PII bảo mật.
* **Trace logs chi tiết**: Mỗi turn được ghi nhận đầy đủ trace thông tin (Objective, Guidelines match, Observations, Latency...) lưu trong DB và hiển thị trên Admin Timeline.
* **Pipeline logo tự động**: Tự động trigger Imagen tạo logo dưới nền khi hồ sơ được đại lý xác nhận và đồng ý.

---

## 2. Hướng Dẫn Cài Đặt Local

```powershell
# Tạo môi trường ảo
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Cài đặt thư viện chạy ứng dụng (Production)
pip install -r requirements.txt

# Cài đặt thư viện phát triển & testing (nếu cần chạy pytest)
pip install -r requirements-dev.txt

# Tạo file cấu hình môi trường
copy .env.example .env
```

Mở file `.env` và điền `GEMINI_API_KEY`. 

---

## 3. Chạy Ứng Dụng Local

Mặc định, server sẽ đọc biến cấu hình `PORT` để chạy. Nếu port 8000 đã bị chiếm dụng trên máy bạn, bạn có thể thiết lập biến môi trường chạy trên port khác (ví dụ: `8082`):

**Chạy trên Windows PowerShell:**
```powershell
$env:PORT="8082"
.\.venv\Scripts\python.exe -m app.main_v2
```

**Chạy trên Command Prompt:**
```cmd
set PORT=8082
.venv\Scripts\python.exe -m app.main_v2
```

Server sẽ khởi chạy tại địa chỉ: `http://127.0.0.1:8082`.

---

## 4. Các Endpoint Quan Trọng

* **Giao diện người dùng**:
  * Chat UI: `GET /`
  * Admin UI: `GET /admin`
* **API endpoints (V2)**:
  * Khởi tạo Session: `POST /api/v1/sessions`
  * Hydrate/Restore Session: `GET /api/v1/sessions/{session_id}`
  * Gửi tin nhắn: `POST /api/v1/sessions/{session_id}/messages`
  * Lấy danh sách Events (Polling): `GET /api/v1/sessions/{session_id}/events`
  * Trạng thái logo: `GET /api/v1/sessions/{session_id}/logos`
  * Dựng lại logo: `POST /api/v1/sessions/{session_id}/logos/retry`
* **API admin (Basic Auth)**:
  * Danh sách sessions + turns timeline: `GET /api/admin/sessions`
  * Export markdown đơn: `GET /api/admin/sessions/{session_id}/export`
  * Export bulk ZIP: `GET /api/admin/sessions/export`

---

## 5. Cấu Trúc Mã Nguồn

```text
app/
  main_v2.py              FastAPI entrypoint v2 (lifespan, static mount)
  api/
    routes_v2.py          Router REST API v2 (/api/v1/sessions)
    admin_v2.py           Router Admin API v2 (Basic Auth, markdown export)
    auth.py               HTTP Basic Auth dependency
  core/
    config_v2.py          Cấu hình settings từ environment variables
    ids.py                Bộ tạo UUID v4 prefixed (sess_, msg_, turn_)
    responses.py          Envelope chuẩn hoá response thành công/thất bại
    security.py           Băm token, xác thực Bearer token
    logo_jobs.py          Background worker quản lý hàng chờ dựng logo
    logo_generator.py     Trình sinh logo SVG local / AI Imagen
    md_exporter.py        Trích xuất hồ sơ sang Markdown Việt thuần
    validators.py         Hàm validator dữ liệu (SĐT, Tên, Địa chỉ blacklist)
    abuse_detector.py     Phát hiện lăng mạ/abuse
    garbage_detector.py   Phát hiện input rác/garbage
    address_blacklist.py   Kiểm tra địa chỉ blacklist
    address_parser.py     Phân tích địa chỉ (tỉnh/thành)
    _conv_derive.py       Tự động suy diễn thông tin địa lý và loại đại lý
    card_renderer.py      Vẽ các card ASCII hiển thị cho người dùng
  db/
    connection.py         Lớp kết nối SQLite, thread-safe
    schema.py             Định nghĩa DB schema SQLite
    store.py              Thao tác CRUD sessions, messages, turns, profiles
  guards/
    injection.py          Chống prompt injection (Pre-turn)
    rate_limit.py         Giới hạn tần suất gọi API (Pre-turn)
    drift.py              Chặn người dùng nói lạc đề/drift (Pre-turn)
    hallucinate.py        Chống lặp từ, sửa lỗi chính tả/dấu câu, bảo vệ PII (Post-turn)
  models/
    enums.py              Các enum hệ thống (Stage, ReviewStatus, v.v.)
    planner.py            Model phụ trợ cho flow planner
    schema.py             Pydantic models lưu trữ tạm thời / serialization
  parlant/
    agent.py              Agent generator build system prompt + LLM call
    turn_processor.py     Linear pipeline 8 bước xử lý turn thoại
    workflow_engine.py    Điều hướng hành trình (workflow state transitions)
    observation_detector.py Phát hiện signals người dùng (Bận, Khoe, Lo, Lửa Lò)
    guideline_registry.py  Quản lý guideline điều phối hội thoại
    canned_responses.py   Quản lý câu thoại mẫu ổn định từ config
    context_builder.py    Lắp ghép context variables cho LLM
  services/
    chat_service.py       Điều phối gửi/nhận tin nhắn và gọi TurnProcessor
    session_service.py    Quản lý vòng đời session, hydration
    profile_service.py    Lưu trữ facts, quản lý validation và auto-derivatives
    serializers.py        Chuyển đổi dữ liệu sang events/public state
  slots/
    definitions.py        Định nghĩa 17 slots thu thập thông tin đại lý
    templates.py          Định nghĩa câu hỏi gợi ý và validator cho từng slot
config/
  guidelines.yaml         Cấu hình guidelines điều tiết giọng nói và luồng
  canned_responses.yaml   File câu thoại mẫu cố định
static/
  index.html, chat.js, style.css  Frontend v2 chat client (SPA)
  admin.html, admin.js, admin.css Giao diện Admin Dashboard hiển thị Timeline Trace logs
```

---

## 6. Hướng Dẫn Chạy Kiểm Thử (Tests)

Hệ thống test suite chạy trên Transient Database SQLite (trong bộ nhớ hoặc thư mục tạm) độc lập hoàn toàn. Mặc định các paid API calls (Gemini/Imagen) đều bị mock chặn.

**Chạy toàn bộ 808 tests:**
```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

**Chạy riêng các smoke tests tích hợp của từng phase:**
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1_smoke.py tests/test_phase2_smoke.py tests/test_phase3_smoke.py tests/test_phase4_smoke.py tests/test_phase5_smoke.py -q
```
