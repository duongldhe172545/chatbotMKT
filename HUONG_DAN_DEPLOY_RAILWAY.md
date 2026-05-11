# Hướng dẫn deploy Em Linh MKT lên Railway

> Step-by-step chi tiết. Người chưa quen Railway cũng làm được.
> Ngày: 2026-05-10

---

## Mục lục

1. [Chuẩn bị trước khi deploy](#1-chuẩn-bị-trước-khi-deploy)
2. [Tạo Railway project](#2-tạo-railway-project)
3. [Set ENV variables (quan trọng nhất)](#3-set-env-variables)
4. [Generate domain + truy cập app](#4-generate-domain)
5. [Mount Persistent Volume (Option B — giữ data)](#5-mount-persistent-volume)
6. [Custom domain (tuỳ chọn)](#6-custom-domain)
7. [Verify deploy thành công](#7-verify-deploy-thành-công)
8. [Auto-redeploy khi push code](#8-auto-redeploy)
9. [Xem logs + monitor](#9-xem-logs)
10. [Troubleshooting — lỗi thường gặp](#10-troubleshooting)
11. [Cost ước tính + theo dõi](#11-cost-ước-tính)
12. [Rollback / rotate password / rotate API key](#12-rollback--rotate)

---

## 1. Chuẩn bị trước khi deploy

### 1.1. Tài khoản Railway

- Truy cập https://railway.com
- Click **Login** → **Login with GitHub** (chọn cách này — tiện cho deploy auto từ repo)
- Verify email nếu Railway yêu cầu

### 1.2. Có GitHub repo (đã có)

Repo của anh: `https://github.com/duongldhe172545/chatbotMKT`
- Đã push commit mới nhất chưa? Nếu chưa, push lên `main` trước.

### 1.3. ANTHROPIC_API_KEY trong tay

- Mở `.env` local để copy `ANTHROPIC_API_KEY=sk-ant-...`
- Hoặc lấy lại tại https://console.anthropic.com/settings/keys

### 1.4. Files Railway cần (đã có sẵn trong repo)

Verify 4 file này tồn tại ở root repo:

| File | Mục đích |
|---|---|
| `Procfile` | Lệnh start: `web: python -m app.main` |
| `railway.json` | Config builder + healthcheck |
| `runtime.txt` | Python version `python-3.12.7` |
| `requirements.txt` | Dependencies |

→ Tất cả đã commit. Không cần làm gì.

---

## 2. Tạo Railway project

### 2.1. New Project

1. Vào https://railway.com/dashboard
2. Click **+ New Project** (góc trên phải, nút màu tím)
3. Chọn **Deploy from GitHub repo**

### 2.2. Connect GitHub (lần đầu)

Nếu chưa connect:
1. Click **Configure GitHub App**
2. Authorize Railway access GitHub
3. Chọn repo `duongldhe172545/chatbotMKT` → **Install**

### 2.3. Chọn repo

- Tìm `chatbotMKT` trong list → click **Deploy Now**
- Railway sẽ tự detect Python (qua `requirements.txt` + `runtime.txt`) → bắt đầu build
- Build mất **~2-3 phút lần đầu** (cài pip dependencies)

### 2.4. Theo dõi build

- Tab **Deployments** → click deployment đang chạy
- Xem **Build Logs** real-time
- Build xong → status chuyển sang **DEPLOYED** (màu xanh) hoặc **CRASHED** (màu đỏ)

⚠️ **Build sẽ CRASH ngay lần đầu** vì chưa set ENV variables (đặc biệt `ANTHROPIC_API_KEY`). Đó là bình thường. Sang bước 3 để fix.

---

## 3. Set ENV variables

Đây là bước **quan trọng nhất**. Sai 1 variable → app crash.

### 3.1. Vào tab Variables

1. Trong project → click vào service `chatbotMKT`
2. Tab **Variables** (icon `{}`)
3. Click **+ New Variable**

### 3.2. Điền 8 biến (copy + paste theo bảng)

| Variable | Value | Giải thích |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` (key của anh) | LLM API key. **BẮT BUỘC** |
| `LLM_PROVIDER` | `claude` | Provider |
| `LLM_MODEL` | `claude-sonnet-4-6` | Model — Sonnet 4.6 quality. Đổi `claude-haiku-4-5-20251001` để tiết kiệm 3x |
| `STORAGE_ADAPTER` | `sqlite` | DB |
| `SQLITE_PATH` | `data/dealers.db` | Đường dẫn — sẽ đổi ở [bước 5](#5-mount-persistent-volume) khi mount volume |
| `HOST` | `0.0.0.0` | **BẮT BUỘC** — Railway container cần bind 0.0.0.0, không phải 127.0.0.1 |
| `USE_REPLIER` | `true` | Bật Replier (Bước 1 refactor) |
| `UVICORN_RELOAD` | `false` | **BẮT BUỘC** — TUYỆT ĐỐI không bật reload ở production |
| `ADMIN_USERNAME` | `admin` | Login admin |
| `ADMIN_PASSWORD` | `duongdeptrai123` | Password admin (đổi nếu muốn mạnh hơn) |
| `CORS_ALLOWED_ORIGINS` | `*` | Mặc định cho dev. Production nên đổi thành domain cụ thể (xem dưới) |

⚠️ **KHÔNG set `PORT`** — Railway tự inject `$PORT` env, code đã đọc đúng. Set vào sẽ conflict.

### 3.3. Cách điền nhanh — Raw Editor

Thay vì click + New Variable từng cái:

1. Tab **Variables** → click **Raw Editor** (góc trên phải, icon `</>`)
2. Paste toàn bộ block sau (sửa `sk-ant-...` thành key thật):

```
ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
LLM_PROVIDER=claude
LLM_MODEL=claude-sonnet-4-6
STORAGE_ADAPTER=sqlite
SQLITE_PATH=data/dealers.db
HOST=0.0.0.0
USE_REPLIER=true
UVICORN_RELOAD=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=duongdeptrai123
CORS_ALLOWED_ORIGINS=*
```

3. Click **Update Variables** → Railway sẽ trigger redeploy tự động.

### 3.4. Verify

- Sau khi save, Railway sẽ redeploy (~2 phút)
- Tab **Deployments** → deployment mới → xem logs
- Nếu thấy `INFO: Application startup complete.` → OK
- Nếu thấy `RuntimeError: ANTHROPIC_API_KEY chưa được set` → quay lại sửa biến

---

## 4. Generate domain

App đã chạy, nhưng chưa có URL public. Tạo domain:

### 4.1. Generate Railway-provided domain (nhanh nhất)

1. Service `chatbotMKT` → tab **Settings** (icon bánh răng)
2. Cuộn xuống mục **Networking**
3. Mục **Public Networking** → click **Generate Domain**
4. Railway tạo URL kiểu: `chatbotmkt-production-xxxx.up.railway.app`
5. Click vào URL → mở app trên browser

### 4.2. Test ngay

- `https://your-app.up.railway.app/` → app phải hiện greeting "Dạ em chào anh ạ! Em là Linh..."
- `https://your-app.up.railway.app/admin` → browser popup login
  - Username: `admin`
  - Password: `duongdeptrai123`
- `https://your-app.up.railway.app/health` → `{"status":"ok"}`

⚠️ Nếu thấy lỗi 502 Bad Gateway → quay lại logs, app chưa start được. Xem [Troubleshooting](#10-troubleshooting).

---

## 5. Mount Persistent Volume

### 5.1. Tại sao cần?

**Mặc định Railway KHÔNG có persistent storage.** Filesystem reset mỗi khi:
- Anh push code mới (auto deploy)
- Service restart
- Region migration

→ `data/dealers.db` mất hết data mỗi lần.

**Volume = ổ cứng riêng** gắn vào container, KHÔNG reset khi deploy mới.

### 5.2. Tạo Volume

1. Service `chatbotMKT` → tab **Settings**
2. Cuộn xuống mục **Volumes** (hoặc tìm **Storage**)
3. Click **+ New Volume**
4. Cấu hình:
   - **Mount Path**: `/app/data`
   - **Size**: `1` GB (đủ cho ~10K dealer profile)
   - **Name**: `dealers-data` (tự đặt)
5. Click **Create Volume**

→ Railway sẽ tự redeploy lần nữa (~2 phút) để mount volume vào container.

### 5.3. Update SQLITE_PATH

Volume đã mount tại `/app/data`. Code phải dùng đường dẫn này:

1. Tab **Variables**
2. Tìm `SQLITE_PATH=data/dealers.db`
3. Đổi thành: `SQLITE_PATH=/app/data/dealers.db` ← **dấu `/` đầu, đường dẫn TUYỆT ĐỐI**
4. Save → Railway redeploy

### 5.4. Verify volume hoạt động

1. Truy cập `/admin/profiles` → chat 1 cuộc thử với dealer test
2. Xác nhận có session mới trong admin
3. **Trigger redeploy thủ công**: Settings → tab Deployments → click `⋮` deployment hiện tại → **Redeploy**
4. Đợi redeploy xong (~2 phút)
5. Vào lại `/admin/profiles` → **session vẫn còn** ✅ → volume hoạt động đúng

Nếu session mất → SQLITE_PATH chưa đổi đúng, sửa lại bước 5.3.

### 5.5. Cost

| Storage | Giá |
|---|---|
| 1 GB | $0.25/tháng |
| 5 GB | $1.25/tháng |
| 10 GB | $2.50/tháng |

Pilot 100 dealer × ~10KB profile = ~1MB. **1GB volume thừa thãi**, ~3 năm mới hết.

---

## 6. Custom domain

(Tuỳ chọn — không bắt buộc)

### 6.1. Yêu cầu

Anh đã sở hữu domain (vd `chatbot.example.com`). Mua domain ở:
- Namecheap (~$10/năm)
- Cloudflare Registrar (~$8/năm — at-cost)
- GoDaddy / Tenten / Mắt Bão (Việt Nam)

### 6.2. Setup ở Railway

1. Service → Settings → Networking
2. Mục **Custom Domains** → click **+ Custom Domain**
3. Nhập domain, vd `chatbot.example.com`
4. Railway hiện CNAME target, vd: `xxx.up.railway.app`
5. Copy CNAME target

### 6.3. Setup DNS ở domain provider

Vào DNS settings của domain (Cloudflare / Namecheap):

1. Add record:
   - **Type**: `CNAME`
   - **Name**: `chatbot` (hoặc `@` nếu trỏ root domain)
   - **Value**: `xxx.up.railway.app` (CNAME target Railway cho)
   - **TTL**: Auto (hoặc 5 phút)
   - **Proxy** (Cloudflare): tắt (DNS only) — Railway tự cấp HTTPS

2. Save

### 6.4. Đợi DNS propagate

- 5-15 phút thường đủ
- Test: `nslookup chatbot.example.com` → phải trả về Railway server
- Truy cập `https://chatbot.example.com` → app load được + có HTTPS (Railway tự cấp Let's Encrypt cert)

### 6.5. Update CORS (nếu set restricted)

Nếu anh đã đổi `CORS_ALLOWED_ORIGINS` không phải `*`, thêm domain mới:
```
CORS_ALLOWED_ORIGINS=https://chatbot.example.com,https://admin.example.com
```

---

## 7. Verify deploy thành công

Checklist sau khi deploy:

- [ ] `https://your-domain/` → hiện greeting Em Linh
- [ ] `https://your-domain/admin` → popup login → admin/duongdeptrai123 → vào được
- [ ] `https://your-domain/admin/profiles` → load list profile
- [ ] `https://your-domain/admin/sessions` → load list sessions
- [ ] `https://your-domain/health` → `{"status":"ok"}`
- [ ] Chat thử 1 cuộc → bot reply tự nhiên
- [ ] Trigger redeploy thủ công → data dealer **vẫn còn** (volume OK)
- [ ] Browser DevTools → Network tab → response có header `X-Request-ID`

---

## 8. Auto-redeploy

Setup xong, mọi `git push origin main` sẽ **tự động trigger build + deploy** mới (~2-3 phút).

### 8.1. Workflow chuẩn

```
Anh code local
↓
git add .
git commit -m "..."
git push origin main
↓
GitHub nhận push
↓
Railway phát hiện thay đổi → trigger build
↓
Build xong → deploy → URL có code mới
```

Anh không cần SSH, không cần copy file thủ công.

### 8.2. Xem deploy đang chạy

- Project → service → tab **Deployments**
- Deployment đang chạy → status **BUILDING** → **DEPLOYING** → **DEPLOYED**
- Nếu **CRASHED** → click vào xem log lỗi

### 8.3. Tắt auto-deploy (nếu muốn)

Settings → Source → uncheck **Automatically deploy on push**.
Sau đó muốn deploy thì tự click **Deploy** trong dashboard.

---

## 9. Xem logs

### 9.1. Real-time logs

1. Service → tab **Deployments**
2. Click vào deployment đang chạy
3. Xem **Deploy Logs** — log của uvicorn + handler

### 9.2. Lọc log

- Search box top of log → tìm `request_id` cụ thể
- Filter level (INFO / WARNING / ERROR)

### 9.3. Use case thực tế

Dealer báo lỗi screenshot có header `X-Request-ID: a3b9c1d4`:
1. Vào Deployments → Logs
2. Search: `a3b9c1d4`
3. Thấy ngay full flow request đó (đầu vào + handler trace + response)

### 9.4. Export log

Settings → Logs → click **Download** (giới hạn 1000 dòng / lần ở free tier).

---

## 10. Troubleshooting

### 10.1. Build CRASHED ngay sau khi tạo project

**Nguyên nhân thường gặp:** Chưa set `ANTHROPIC_API_KEY`.

**Fix:** [Bước 3](#3-set-env-variables) — set đầy đủ ENV.

### 10.2. App start nhưng truy cập 502 Bad Gateway

**Nguyên nhân:** `HOST` không phải `0.0.0.0`.

**Fix:** Variables → đổi `HOST=0.0.0.0` → save → redeploy.

### 10.3. Build mất quá 5 phút / fail

**Nguyên nhân:** `requirements.txt` có dependency lỗi hoặc Python version không match.

**Fix:**
- Check `runtime.txt` đúng `python-3.12.7`
- Check `requirements.txt` không có gì lạ
- Logs build → tìm dòng `ERROR` đầu tiên

### 10.4. Reload restart loop

**Nguyên nhân:** `UVICORN_RELOAD=true` ở production → uvicorn watcher loop.

**Fix:** Variables → `UVICORN_RELOAD=false` → save.

### 10.5. Admin login bị 401 mặc dù pass đúng

**Nguyên nhân:**
- ENV `ADMIN_PASSWORD` chưa set
- Hoặc set nhầm space đầu/cuối

**Fix:** Verify password trong Variables → save lại không có space thừa.

### 10.6. Mất data sau khi push code mới

**Nguyên nhân:** Chưa mount volume hoặc `SQLITE_PATH` không trỏ đúng `/app/data/...`.

**Fix:** [Bước 5](#5-mount-persistent-volume).

### 10.7. CORS error khi frontend gọi API

**Nguyên nhân:** Frontend deploy domain khác mà `CORS_ALLOWED_ORIGINS` không có domain đó.

**Fix:** Thêm domain vào `CORS_ALLOWED_ORIGINS` (CSV).

### 10.8. App chậm / latency cao cho dealer Việt Nam

**Nguyên nhân:** Railway region default = US-West / EU. VN ping ~200-300ms.

**Fix:**
- Settings → Region → đổi sang **Asia-Southeast1** (Singapore) — nếu Railway có
- Hoặc cân nhắc Fly.io (có Singapore region rõ ràng)

---

## 11. Cost ước tính

### 11.1. Free tier Railway

- $5 credit/tháng
- Đủ cho service nhỏ chạy ~24/7 + ~50 dealer pilot
- Khi vượt → charge theo CPU+RAM-hour

### 11.2. Tính cost dự kiến

| Tài nguyên | Cost |
|---|---|
| Compute (~256MB RAM, idle 70%, ~720h/tháng) | $3-5/tháng |
| Volume 1GB | $0.25/tháng |
| Custom domain | Free (Railway) |
| Egress traffic | $0.10/GB (free 100GB) |
| **Tổng MVP** | **~$4-6/tháng** (trong free tier $5) |

### 11.3. Khi vượt free tier

- 100-500 dealer pilot: ước tính $10-15/tháng
- 1000+ dealer: nâng cấp Pro $20/tháng + add Postgres

### 11.4. Theo dõi cost

- Dashboard → **Usage** tab
- Hiện CPU+RAM+egress real-time
- Set spend limit: Settings → **Spend Limit** → đặt $10 (cảnh báo) + $20 (hard cap)

### 11.5. Cost LLM Anthropic (tách riêng, không tính trong Railway)

- Sonnet 4.6: ~$0.025/turn × 10 turn = ~$0.25/cuộc dealer
- Pilot 100 dealer: ~$25/tháng Anthropic
- Set spend limit: https://console.anthropic.com/settings/limits

---

## 12. Rollback / rotate

### 12.1. Rollback deploy lỗi

Push code mới gây crash:

1. Tab **Deployments**
2. Tìm deployment cũ (status DEPLOYED, gần đây)
3. Click `⋮` → **Redeploy**
4. Railway revert về code cũ trong ~2 phút

### 12.2. Rotate ADMIN_PASSWORD

Khi password lộ:

1. Variables → `ADMIN_PASSWORD` → đổi value mới
2. Save → Railway redeploy
3. Browser tab cũ logout (mất cookie cache) hoặc Cmd+Shift+Del clear

### 12.3. Rotate ANTHROPIC_API_KEY

Khi key lộ (theo SECURITY.md):

1. https://console.anthropic.com/settings/keys → **Disable** key cũ
2. **Create Key** mới → copy
3. Railway → Variables → `ANTHROPIC_API_KEY` → paste key mới
4. Save → redeploy
5. Verify: chat thử trên Railway URL → hoạt động → xác nhận key mới ok
6. Sau 24h → **Delete** key cũ ở Anthropic console

### 12.4. Restart service nhanh

Settings → tab Deployments → deployment hiện tại → click `⋮` → **Restart**.

Không cần redeploy đầy đủ, chỉ restart container (~10s).

---

## 13. Sau khi deploy thành công

### 13.1. Pilot 5-10 dealer ADG nội bộ

- Gửi URL `https://your-domain` cho team Sếp Vinh
- Họ test thử 5-10 cuộc chat
- Anh xem `/admin` mỗi ngày để check data

### 13.2. Monitor

- Hàng tuần check Railway **Usage** tab — cost trending OK?
- Hàng tuần check `/admin/sessions` — dealer chat thật có vào không?
- Hàng tháng check Anthropic spend — có đột biến?

### 13.3. Khi vượt 50 dealer

- Cân nhắc upgrade Postgres (Railway có add-on free tier 1GB)
- Setup backup tự động (xem KE_HOACH_HOAN_THIEN_v2.md mục 4.6)

---

## 14. Liên kết hữu ích

- Railway docs: https://docs.railway.com
- Railway pricing: https://railway.com/pricing
- Railway status (down detector): https://status.railway.com
- Anthropic console: https://console.anthropic.com
- Repo Em Linh: https://github.com/duongldhe172545/chatbotMKT

---

**End of file. Anh deploy theo từng bước, có lỗi báo tôi.**
