# KẾ HOẠCH TỔNG — Em Linh MKT (cập nhật 2026-06-12)

> **Ràng buộc xuyên suốt:** chưa commit/push tới khi sếp test xong · khoá LUẬT không khoá case · test full multi-turn + adversarial trước khi báo done · KHÔNG đụng/mất data production.

---

## 1. CÒN LẠI (việc thật sự cần làm)

### 🔴 Trước sự kiện
- [x] ~~PHASE 8 — vá lỗi an toàn nội dung~~ ✅ DONE (thuần luật) — xem §Phase 8.
- [ ] **PHASE 9 — fix theo feedback team MKT** (xem §Phase 9 + [PHAN_TICH_FEEDBACK_MKT_2026-06-12.md](PHAN_TICH_FEEDBACK_MKT_2026-06-12.md)): Đợt 1 (xưng hô / cắt độ dài / mốc 3 ngày) nên trước sự kiện; Đợt 2 (reorder brandkit-first) cụm lớn, cân nhắc sau.
- [ ] **Sếp test** bản local hiện tại (Phase 6 + 7): giọng tự nhiên, card/slogan đúng lúc, không cộc lốc.
- [ ] **Commit + push** toàn bộ P0→P7 (sau khi sếp OK). Kèm **dọn script nháp**: xoá `scripts/_smoke_p6.py`, `_live_p6.py`, `_diag.py`, `_verify_extract.py`; **giữ** `load_test.py`, `profile_turn.py`.
- [ ] **Deploy Railway** + set env: `SQLITE_PATH=/data/chatbot_v2.sqlite3`, `APP_ENV=production`, `CONVERSATION_RUNTIME=gemini`. **KHÔNG set `WEB_WORKERS`** (>1 = thảm hoạ với SQLite).
- [ ] **Load test 1 vòng TRÊN Railway** (`scripts/load_test.py` trỏ URL prod, ~$0.3) — số local bị thổi phồng bởi mạng nhà; môi trường thật mới là số chốt.
- [ ] **Smoke test** 2-3 hội thoại thật trên prod + check quota Gemini còn nguyên, trước giờ G.

### 🟡 Chờ sếp quyết (đang tạm hoãn để test lại)
- [ ] **#2** — C1: câu trả lời định tính ("khách quen nhiều") bị skip thay vì ghi nhận.
- [ ] **#4** — Slogan "số 1 VN" / "tốt nhất": có vi phạm luật quảng cáo không → có chặn không.
- [ ] Giọng: thỉnh thoảng còn mở "Dạ không sao anh" — siết thêm hay để vậy (tránh over-steer).

### 🟢 Sau sự kiện (không khẩn)
- [ ] **P4.5** — thu lại field khi khách hợp tác về sau (combo A+C). Đổi HÀNH VI runtime → cần test UX riêng, KHÔNG ship sát sự kiện. (Field chưa skip cứng vẫn tự được hỏi lại; chỉ field bị refusal/khong_biet mới mất.)
- [ ] **Perf/infra phụ:** log rotate (M4), close connection ở health_check (M5), gộp 2 write-tx idempotency (H5), read-only tx cho `poll_events`/`authorize` (H4). Redis (M6) chỉ khi chạy nhiều worker.
- [ ] Minor 9 tiêu chí: tín hiệu phụ C3/C5/C9 (nhẹ — trọng tâm đã đúng).

---

## 2. ĐÃ XONG (code rồi, CHƯA commit — chờ sếp test)

| Phase | Nội dung | Test |
|---|---|---|
| **P0** | Batch fix: chống chốt sớm, logo_existing_intent (nâng cấp/thiết kế lại/làm mới), card gọn 4 phần, bớt hứa | ✅ |
| **P1** | An toàn data: gỡ HẲN auto-DROP table, migration additive (`ALTER ADD COLUMN`, không drop), fail-fast nếu prod không trỏ được `/data` | ✅ |
| **P2** | Concurrency: tách **3 transaction ngắn** (đưa 2 call Gemini RA NGOÀI write-lock), `BEGIN IMMEDIATE` serialize cursor, global error handler 503 + Retry-After, `synchronous=NORMAL` | ✅ |
| **P3** | Sự kiện ~100 người: threadpool 40→150, 429 fail-fast + semaphore Gemini 50, rate-limit/session, history window 40. **Load test local: 100 VU, ~3s/lượt, 0 lỗi, 0 db-locked** | ✅ |
| **P4** | Khớp 9 tiêu chí: sửa C2/C5 lệch trọng tâm, C6 thành câu hỏi RIÊNG, C8/C9 gặng, brandkit propose→confirm, luật KHỚP NGỮ NGHĨA (hết gán "đói"=mô hình), admin hiện đủ C1-C9 + câu gốc khách | ✅ |
| **6** | Dọn prompt: tách `principles_extraction`/`principles_reply`, gỡ luật lặp 3 chỗ ("1 câu hỏi"/"không chốt"/ACK), bỏ no_close_rule verbose → **giọng tự nhiên trở lại** | ✅ |
| **7** | Card không bung trước khi chốt slogan (7.1), gộp 1 dòng "Phong cách logo" (7.2), tone tích cực + icon mỗi lượt (7.3), **thu gọn guard chống-chốt-sớm** còn 5 marker lõi → hết câu cộc lốc (7.6) | ✅ 651 |

> Chi tiết root-cause/cách fix nằm trong git diff + memory (`project_phase6_prompt_dedup`, `project_phase7_conversation_fix`).

---

## 3. QUYẾT ĐỊNH KHÔNG LÀM
- **Postgres** — giữ SQLite. Lý do: ràng buộc không đụng data prod (migrate = thao tác DUY NHẤT phải di chuyển data) + Railway Postgres cần nâng gói + SQLite+WAL đủ vài trăm dealer/1 node. Chỉ xem lại nếu cần nhiều instance ngang / hàng trăm ghi-giây bền vững.
- **7.4** "Dương An Cơ" (tiểu từ tình thái trong tên) — kệ, tên vốn mơ hồ + khách tự sửa được.
- **7.5** Form địa chỉ bung lặp — không phải lỗi.

---

## PHASE 8 — VÁ LỖI AN TOÀN NỘI DUNG ✅ DONE 2026-06-12 (CHƯA commit) — thuần luật

**ĐÃ LÀM (658 test pass + live verify):** 8.1 luật abuse vào `principles_extraction` → "anh buôn ma tuý" / "slogan là <bậy>" KHÔNG được nhận làm field (live + DB xác nhận main_product không lưu, bot re-hỏi lịch sự); 8.2 luật vào task `show_profile_review` (chưa gửi link/chưa chốt ở bước duyệt); 8.3 BỎ (set `ZALO_GROUP_URL` khi deploy). **Bonus:** test mới bắt được 2 lỗi YAML CÓ SẴN — luật "ok không phải dữ liệu" (slot xác nhận) + luật SĐT slot 1.3 bị parse thành **dict** (thiếu nháy quanh dấu `:`) → đã vá + thêm test chống tái (`test_p8_content_safety.py`).

> Nguồn: transcript test "Nội thất Linh Đan" — người test gõ rác/bậy/phi pháp. Sự kiện 100 người chắc chắn có người làm vậy.

> **Hướng: THUẦN LUẬT** (sếp chốt 2026-06-12 — không fix code cứng/blocklist). Bug xảy ra vì THIẾU luật → thêm luật là khớp gốc.

### 8.1 — Luật: nội dung bậy/phi pháp KHÔNG phải dữ liệu (LỖI 1) — ✅ LUẬT
**Hiện tượng:** "anh buôn ma tuý" → thẻ "Sản phẩm: buôn ma tuý"; "slogan là địt mẹ mày" → thẻ "Slogan: ...".
**Gốc:** bộ TRÍCH XUẤT (①) lấy chữ bậy làm value vì khách nói thẳng "slogan là X" — chưa có luật cấm. (Luật "KHỚP NGỮ NGHĨA" không bắt vì "slogan là X" đúng cấu trúc trả lời.)
**Fix:** thêm 1 luật vào `principles_extraction` ([rules.yaml](config/rules.yaml)): nội dung chửi bậy/tục/xúc phạm/phi pháp (ma túy/vũ khí/hàng cấm) → KHÔNG gán cho field nào (kể cả khi nói thẳng "slogan/sản phẩm/tên là…"), intent=tam_su → bot phản hồi nhã nhặn rồi hỏi lại. ① không nhả field → không lưu → Workflow không advance → không lên thẻ.

### 8.2 — Luật: bước trình thẻ CHƯA gửi link Zalo (LỖI 3) — ✅ LUẬT
**Hiện tượng:** lượt review bot tự "đã thu thập đầy đủ + [Link Zalo]" trước khi khách duyệt.
**Gốc:** task `show_profile_review` ([context_builder.py](app/parlant/context_builder.py)) chưa nói rõ "chưa gửi link ở bước này" → LLM tự chốt sớm. (Card + "anh duyệt OK?" thì ĐÚNG — chỉ đoạn "đã xong + link" là sớm 1 bước.)
**Fix:** thêm vào task review: CHỈ mời xem lại + xác nhận; CHƯA gửi link Zalo / CHƯA chào kết thúc — để bước bàn giao sau khi khách đã duyệt.

### ~~8.3~~ — Bịa link Zalo từ số khách (LỖI 2) → **BỎ** (sếp quyết)
Link bịa = số khách xảy ra vì local chưa cấu hình link Zalo thật → LLM vớ số khách. **Set `ZALO_GROUP_URL` thật khi deploy là xong** (bot có link đúng để dùng; luật cấm-dùng-số-khách ở handoff vốn đã có). Không cần code.

### Test
- (rule wired) prompt extractor chứa luật 8.1; task review chứa "CHƯA gửi link".
- (live, gemini) gõ "slogan là <bậy>" / "sản phẩm là ma tuý" → KHÔNG lưu, KHÔNG lên thẻ, bot hỏi lại.

---

## PHASE 9 — FIX THEO FEEDBACK TEAM MKT (plan chi tiết 2026-06-12, CHƯA code)

> Nguồn: [PHAN_TICH_FEEDBACK_MKT_2026-06-12.md](PHAN_TICH_FEEDBACK_MKT_2026-06-12.md). Chia 2 đợt. Tinh thần: thuần luật chỗ nào được, code chỗ nào cần tất định.

### ĐỢT 1 — nên TRƯỚC sự kiện (nhẹ, ít rủi ro)

#### 9.1 — Xưng hô anh/chị TẤT ĐỊNH ✅ DONE 2026-06-12 (CHƯA commit)
**Gốc:** `address_form="anh"` hardcode → prompt luôn "gọi khách: anh"; LLM chỉ né "chị" khi cue rõ → loạn xạ. Guard chỉ chạy khi =="chi" (không bao giờ) → vô dụng.
**Đã làm (đơn giản hơn plan — KHÔNG đụng schema LLM):**
- `detect_address_form(messages)` ([observation_detector.py](app/parlant/observation_detector.py)): quét tin nhắn KHÁCH tìm dấu hiệu tự xưng "chị" (regex high-precision: "chị tên / tôi là chị / gọi chị / cho chị xin / chị muốn…"), mặc định "anh". **Sticky tự nhiên** vì cue nằm trong history → tính lại mỗi lượt vẫn ổn định.
- [chat_service.py](app/services/chat_service.py) tính `address_form` từ `recent_messages` → truyền vào `turn_processor.process` (bỏ hardcode).
- Guard [turn_processor.py](app/parlant/turn_processor.py) `_post_turn_guards`: form="chi" + reply lỡ "anh" → đổi "chị" (giữ hoa/thường, bắt mọi vị trí).
- **12 test + live verify:** "chị tên Thư" → bot gọi "chị" nhất quán cả phiên. (Lượt chào ĐẦU chưa có cue → vẫn "anh" mặc định — chấp nhận được.)

#### 9.2 — Cắt độ dài (CẢ câu hỏi) + khen "giống người" (🟡 CHƯA fix — đụng nhiều người nhất)
**Vấn đề gồm 2 phần (sếp đính chính):**
- **(a) DÀI ở phần hỏi:** bot giảng giải/nhận xét cả lĩnh vực TRƯỚC khi hỏi.
- **(b) NỊNH generic mỗi lượt:** khen lặp tính từ sáo ("uy tín/chuyên nghiệp") → máy móc, "chưa thật".

**Câu trả lời KÌ VỌNG (ví dụ before → after):**

| Tình huống | HIỆN TẠI (dài/nịnh) | KÌ VỌNG (gọn/thật) |
|---|---|---|
| Khách: "tủ bếp" (đang hỏi sản phẩm) | "Dạ vâng, tủ bếp là dòng sản phẩm rất tiềm năng và luôn được khách quan tâm. Anh cho em hỏi thêm, mô hình kinh doanh chính của cửa hàng mình là xưởng sản xuất trực tiếp hay đại lý phân phối thương mại ạ? 🛠️" | "Dạ tủ bếp ạ! 🛠️ Cửa hàng mình là **xưởng sản xuất hay đại lý phân phối** ạ?" |
| Khách: "điện mặt trời" | "Dạ điện mặt trời là lĩnh vực rất tiềm năng trong xu hướng năng lượng xanh, nhiều gia đình đang quan tâm… [giảng giải] … Anh cho em hỏi cửa hàng mình ở khu vực nào ạ?" | "Dạ mảng điện mặt trời đang lên ạ ✨ Cửa hàng mình ở **khu vực nào** ạ?" |
| Lượt KHÔNG có gì đặc biệt để khen | "Dạ vâng em ghi nhận rồi ạ, cảm ơn anh đã chia sẻ nhé! Cửa hàng mình thật chuyên nghiệp… [câu hỏi]" | "Dạ em ghi nhận rồi ạ. Anh thường **nhập hàng từ hãng nào** ạ? 🤝" *(không ép khen)* |

→ Khuôn kì vọng: **1 đoạn ~25-40 từ** = (ack ngắn HOẶC bỏ) + **câu hỏi đi thẳng** + 1 icon. KHÔNG giảng giải, KHÔNG khen mỗi lượt.

**Cách fix (thuần LUẬT tone — đúng gu):**
1. [rules.yaml](config/rules.yaml) `tone.general`: nhấn 1 đoạn ~25-40 từ; câu hỏi đi thẳng, KHÔNG giảng giải lĩnh vực; khen CÓ CHỌN LỌC (chỉ khi có cái cụ thể, đa dạng, KHÔNG mỗi lượt), tránh tính từ sáo lặp.
2. [rules.yaml](config/rules.yaml) `principles_reply`: "ack/khen KHÔNG bắt buộc mỗi lượt".
3. [context_builder.py](app/parlant/context_builder.py) task collect: rút cực gọn, nhấn "đi thẳng câu hỏi".
**Test:** chạy lại 3 kịch bản team (solar/no-logo/có-logo), ĐO độ dài thật + cảm giác.
**Rủi ro:** cắt quá tay mất nét ấm → test cân bằng. KHÔNG đụng icon/tích cực (7.3).

#### 9.3 — Nói rõ mốc 3 ngày + trả lời "cần gì / quy trình / bao lâu" (🟡 CHƯA fix, nhẹ)
Gồm 2 việc nhỏ:

**(A) Mốc 3 ngày — sửa task handoff.** [context_builder.py](app/parlant/context_builder.py) nhánh `zalo_handoff` (+ lúc chốt brandkit) thêm câu nêu rõ mốc.
- *Ví dụ:* "…Bộ nhận diện (logo + danh thiếp + video) đội ngũ bên em gửi qua Zalo **trong 3 ngày tới** nhé!"

**(B) Trả lời khi khách hỏi "cần gì / quy trình / bao lâu".** Hiện bot lảng (#22). Thêm 1 **luật vào `principles_reply`** ([rules.yaml](config/rules.yaml)): "Khi khách hỏi quy trình / cần thông tin gì / bao lâu → trả lời RÕ rồi quay lại câu đang hỏi". Reply LLM đọc câu hỏi + luật → tự trả lời (không cần intent mới).
- *Ví dụ* — khách "cần thông tin gì?" → "Dạ em chỉ cần vài thông tin cơ bản (tên, ngành, màu/phong cách anh thích) — khoảng **4-5 phút** ạ. Đội thiết kế làm **logo + danh thiếp + video**, gửi qua Zalo **trong 3 ngày**. Mình tiếp nhé, [câu đang dở]?"
- khách "bao lâu có?" → "Dạ sau khi trao đổi xong, đội ngũ gửi trọn bộ qua Zalo trong **3 ngày tới** ạ. [tiếp tục]"

**Test:** hỏi "cần gì để có brandkit?", "bao lâu?", "quy trình thế nào?" → bot liệt kê rõ, không lảng.

### ĐỢT 2 — cụm LỚN (thay đổi luồng vừa → test kỹ; có thể SAU sự kiện)

#### 9.4 — Reorder brandkit-first + preview LIVE + 9 tiêu chí thành tư vấn (🔴)
**Mục tiêu:** hết "16 lần hỏi mới tới brandkit" + hết hụt hẫng "hứa mà chưa thấy".
**Cách fix:**
1. **Đảo thứ tự** ([workflow_engine.py](app/parlant/workflow_engine.py) `compute_objective` + `compute_workflow_state` + `_build_collection_status`): REQUIRED cơ bản (tên/địa chỉ/SĐT/sản phẩm/mô hình) → **brandkit_consent + màu/phong cách/slogan NGAY** → bước preview/chốt → RỒI mới tới C1-C9 (chuyển `OPTIONAL_FIELDS_PRIORITY` xuống sau brandkit, đặt là "bonus").
2. **Preview = SHOW MẪU ĐẸP CÓ SẴN** (sếp chốt 2026-06-12 — KHÔNG gen logo live): gen logo bằng GPT/DALL-E = đắt; bằng model rẻ = logo XẤU → tác dụng ngược. Thay vào đó **lưu sẵn vài mẫu logo đẹp (designer làm), chỉ SHOW lên**. Bước `brandkit_preview` sau khi chốt màu/phong cách: hiện **2-3 mẫu tham khảo khớp ngành + phong cách** (kho ảnh tĩnh curated) + **slogan gợi ý** (text, `gen_slogans` rẻ) + nhắc mốc 3 ngày.
   - ⚠️ Khung rõ là **"mẫu THAM KHẢO phong cách"**, KHÔNG phải logo cuối của khách (kẻo khách tưởng đây là logo mình → hụt). Logo riêng vẫn do đội thiết kế làm, gửi sau 3 ngày.
   - Cần: 1 bộ ảnh mẫu (vài cái/ngành × phong cách) + map ngành+phong cách → mẫu + FE hiện ảnh. (Nhẹ, không tốn API.)
3. **9 tiêu chí = trò chuyện tư vấn:** sau brandkit → khung chuyển "để em tư vấn/đồng hành tốt hơn"; các câu C1-C9 OPTIONAL, cho tâm sự, đáp có giá trị; khách nghỉ sau brandkit cũng OK.
**Test:** full multi-turn 2 kịch bản (chốt brandkit sớm rồi nghỉ / đi tiếp tới review); đảm bảo không vỡ guard chốt-sớm + card đúng.
**Rủi ro:** CAO nhất Phase 9 (đụng lõi workflow). KHÔNG ship sát sự kiện. Cần load/regression test.

### TÁCH RIÊNG — TEAM FRONTEND (không thuộc backend)
- **Avatar / ảnh 3D Em Linh** cạnh chatbox → báo team FE. (Nút tích chọn: sếp BỎ, không cần.)
- *(Liên quan 9.4: FE cũng cần hiện được ẢNH MẪU logo trong khung chat.)*

### Thứ tự đề xuất
9.1 → 9.2 → 9.3 (Đợt 1, trước sự kiện) → [sự kiện] → 9.4 (Đợt 2, sau). Mỗi mục test xong mới sang mục sau; chưa commit tới khi sếp duyệt từng phần.

---

## 4. THAM KHẢO

### Runbook ngày sự kiện
1. Deploy bản đã load-test **trước ≥1 ngày**, không deploy sát giờ G.
2. Env: `SQLITE_PATH=/data/chatbot_v2.sqlite3` + `APP_ENV=production` + `CONVERSATION_RUNTIME=gemini`. **KHÔNG set `WEB_WORKERS`**.
3. Smoke 2-3 hội thoại prod trước giờ G.
4. Trong sự kiện: mở admin timeline + tail log Railway. **429 hàng loạt = quota** (không phải bug); **`db_busy` 503 = báo lại** để soi.

### Kiến trúc 2 bộ não + runtime
- **[1] Extraction** (Gemini nếu có key) → field + intent · **[2] Workflow engine** (code thuần) → objective · **[3] Reply gen** → `stub` (câu mẫu) hoặc `gemini` (LLM).
- `CONVERSATION_RUNTIME` ([config_v2.py:42](app/core/config_v2.py#L42)) default `parlant_local`=stub; `gemini`=LLM. Production = gemini.

### Gotcha (nhớ kẻo sập)
- 🔴 **KHÔNG `WEB_WORKERS>1` với SQLite** — load test đo được tail thảm hoạ (cross-process lock thrash).
- `CONVERSATION_RUNTIME=gemini` mới bật giọng LLM (local default = stub, sẽ thấy câu mẫu cứng).
- PowerShell `$env:X=""` = **XOÁ biến** (từng vô tình gọi Gemini thật khi tưởng đang chạy stub).
- `GEMINI_MAX_CONCURRENCY=50` là điểm ngọt (100 làm mỗi call chậm → tail x1.75).
