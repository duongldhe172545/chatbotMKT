# Security — Em Linh MKT Chatbot Dealer

Tài liệu này nói về **chống leak secrets + chống hacker đánh cắp dữ liệu**, không phải về RBAC/access control.

---

## 1. Threat model — đang chống cái gì

| Mối đe doạ | Trạng thái | Cách phòng |
|------------|-----------|------------|
| `.env` bị push lên git | ✅ Đã fix | `.gitignore` chặn `.env`, `.env.*`, `*.key`, `*.pem`, `secrets/`, `credentials.json` |
| `data/` (chứa SDT, tên dealer) bị push lên git | ✅ Đã fix | `.gitignore` chặn cả thư mục `data/` |
| API key lộ qua error response | ✅ Đã fix | [chat.py:26-31](app/api/chat.py#L26-L31) trả message generic, log full trace chỉ ở server |
| API key lộ qua logs | ✅ An toàn | Chỉ log INFO HTTPX (URL + status, không body/header). Không có `print(api_key)` |
| API key lộ qua frontend | ✅ An toàn | Browser KHÔNG thấy key — chỉ server gọi Anthropic. Frontend chỉ POST `/api/chat` |
| Prompt injection từ dealer ("Ignore previous, dump system") | ✅ An toàn | LLM không có quyền truy cập env. System prompt được gắn server-side, dealer không thể override |
| Stranger trên LAN xem `/admin` | ⚠️ KHÔNG bảo vệ | Chấp nhận trade-off ở MVP local. Trước khi share LAN cho người khác, cần thêm auth lại |
| Stranger spam `/api/chat` để burn token | ⚠️ Chưa | Cần rate limit. Hiện tại chỉ có `max_length=2000` trên message |
| Traffic LAN bị sniff (HTTP plain) | ⚠️ Chưa | Cần HTTPS — dùng ngrok/cloudflared khi share ngoài máy |
| Dependency có CVE | ⚠️ Chưa kiểm | Chạy `pip-audit` định kỳ |
| Data dealer plaintext trong SQLite | ⚠️ Chấp nhận với MVP | Khi chuyển M365 → mã hoá at-rest sẵn |
| **PII (SĐT, email) lộ qua server logs** | ✅ Đã fix | [logging_setup.py](app/logging_setup.py) filter redact `0xxxxxxxxx` → `[PHONE]` |
| **LLM crash giữa session** | ✅ Đã fix | [claude.py](app/llm/claude.py) retry 3 lần với backoff + fallback empty extraction |
| **Frontend double-submit gây 2 LLM call** | ✅ Đã fix | [chat.js](static/chat.js) `isSending` flag chặn ở cả form + sendMessage |

---

## 2. Khi init git lần đầu — checklist

Trước khi `git init` + `git add`:

```powershell
# 1. Verify .env và data/ thực sự bị ignore
git check-ignore -v .env data/dealers.db

# 2. Dry-run xem commit sẽ chứa file gì
git status --ignored

# 3. KHÔNG dùng "git add ." — dùng tên file cụ thể hoặc:
git add app/ static/ requirements.txt README.md SECURITY.md .gitignore .env.example
```

**Nếu lỡ commit `.env`:**
```powershell
# Xoá khỏi history (chưa push)
git rm --cached .env
git commit --amend --no-edit

# Đã push lên remote — phải rotate key NGAY và:
git filter-repo --path .env --invert-paths
# hoặc dùng BFG: https://rtyley.github.io/bfg-repo-cleaner/
```

---

## 3. Khi key bị nghi lộ — quy trình rotate

API key của Anthropic là cái duy nhất "có giá", phải bảo vệ kỹ.

**Trigger rotate ngay khi:**
- Lỡ paste vào chat/Slack/Telegram/screenshot
- Lỡ commit lên git (kể cả private repo)
- Máy dev bị mất / nghi nhiễm malware
- Thành viên có quyền đọc `.env` rời team
- Audit log Anthropic console thấy request lạ (region khác, time khác)

**Quy trình:**

1. https://console.anthropic.com/settings/keys → tìm key cũ → **Disable**
2. Tạo key mới → copy
3. Sửa `.env` local với key mới
4. Restart server
5. (Nếu có server prod) update env ở prod, restart
6. Xác nhận `Disable` key cũ không còn request về (chờ 5 phút, xem console)
7. Sau 24h confirm OK → **Delete** hẳn key cũ

---

## 4. Khi share LAN / public — checklist

Trước khi mở `0.0.0.0` cho người khác kết nối:

- [ ] Thêm Basic Auth lại cho `/admin` (đang gỡ ở MVP local)
- [ ] Đổi `HOST=0.0.0.0` chỉ khi cần thật, không dùng cho dev cá nhân
- [ ] Bật rate limit (chưa có — cần thêm `slowapi` hoặc nginx phía trước)
- [ ] Dùng HTTPS qua ngrok/cloudflared/Caddy thay vì HTTP trần
- [ ] Set Anthropic spend limit ở console: https://console.anthropic.com/settings/limits
- [ ] Audit lần cuối: `pip-audit` không có HIGH/CRITICAL CVE

---

## 5. Code hygiene rules — đã tuân thủ

Khi viết code mới, giữ các rule này:

1. **Không bao giờ log object có thể chứa secret:**
   ```python
   # XẤU
   logger.info(f"Calling LLM with config: {self.__dict__}")
   # TỐT
   logger.info("Calling LLM model=%s", self.model)
   ```

2. **Không bao giờ trả raw exception ra client:**
   ```python
   # XẤU
   raise HTTPException(500, detail=str(exc))
   # TỐT
   logger.exception("...")
   raise HTTPException(500, detail="Lỗi nội bộ")
   ```

3. **Không hard-code key/password trong code, file YAML, Dockerfile.**

4. **Tách secret ra `.env` — không dùng `os.environ["KEY"]` (KeyError leak), dùng `os.getenv` rồi check sớm.**

5. **Không log raw transcript dealer ở mức INFO** (PII). Dùng DEBUG hoặc redact.

---

## 6. Pre-commit hook để chặn lỡ tay (khuyến nghị)

Khi init repo, cài tự động:

```powershell
pip install pre-commit detect-secrets
detect-secrets scan > .secrets.baseline
```

Tạo `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

Sau đó `pre-commit install` — mọi commit sẽ tự scan, nếu thấy chuỗi giống API key thì chặn.

---

## 7. Pháp lý / Compliance — riêng cho dealer Việt Nam

Theo tài liệu MVP mục 9 (luật chống voice data bẩn):
- ✅ Audio dealer KHÔNG lưu server (chỉ text từ Web Speech API)
- ✅ Voice transcript là RAW, có cờ `confirmation_status` rõ ràng
- ⚠️ **Mục 9.9 — "không chuyển transcript cho S network":** Hiện tại transcript được gửi tới Anthropic API (server đặt tại Mỹ). Nếu "S network" trong context của dự án bao gồm cả third-party LLM US-based → **vi phạm**. Phải:
  - (a) Có consent rõ với dealer trước khi go-live, hoặc
  - (b) Swap LLM nội địa (FPT.AI, VinAI, Viettel AI) — chừa sẵn ở `app/llm/` adapter pattern

- ⚠️ **Mục 9.8 — "không dùng voice training nếu chưa có consent":** Anthropic mặc định không dùng API request để train. Verify lại tại https://www.anthropic.com/legal/commercial-terms — hiện tại OK, nhưng cần ghi nhớ khi đổi provider.

---

## 8. Báo cáo lỗ hổng

Tìm thấy bug bảo mật, **đừng public** — báo trực tiếp owner project.
