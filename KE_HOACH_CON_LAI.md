# KẾ HOẠCH CÒN LẠI — Em Linh MKT (gộp 1 file, 2026-06-24)

> **Ràng buộc:** khoá LUẬT không khoá case · test full multi-turn + adversarial trước khi báo done · KHÔNG đụng/mất data prod · chưa commit tới khi sếp duyệt.
> File này gộp mọi việc CÒN LẠI (đã xoá các plan con đã done: 9.4 / field-rác / logo-gen / fix-luồng-tư-vấn).

---

## 0. ĐÃ XONG — CHƯA COMMIT (tra git diff)
1. **P0–P9.1** (commit `0372292`) + **Phase 10 đợt 🔴** (commit `ebd8c7e`).
2. **9.4 brandkit-first** — reorder `required → brandkit → C1-C9 (bonus) → review` + preview kho mẫu SVG (`brandkit_samples.py`) + "đủ rồi"→review.
3. **Dọn 5 field rác** — district/phone_secondary/zalo/customer_segment_signal/category_stack; admin hiện full; phone đa-số (PA-A giữ validate_phone).
4. **Fix 11.2/11.3/11.4** — consent=no không chào kết + hook tư vấn · admin xưng hô thật (hết hard-code "anh") · bỏ ô "Danh mục (ngành) suy ra".
5. **Dọn cụm tự-gen-logo** — xoá `logo_generator.py`/`logo_jobs.py` + 5 field (logo_initials/brand_name_short/initials_full/initial_single/slogan_options) + endpoints `/logos`.

→ **685 test pass** + live verified. ~40 file đổi, đang **uncommitted**. (Đề xuất commit tách 4 cụm: 9.4 / field-rác / fix-11 / logo-gen.)

---

## 1. ƯU TIÊN LÀM TIẾP

### 11.1 🔴 Bridge brandkit → tư vấn cho MƯỢT + bot KHÔNG bịa quà — ⏸️ CHỜ SẾP trình bày chi tiết
**Gốc:** sau preview, bot nhảy sang hỏi tư vấn ("mấy chị thợ?") mà khách không hiểu trả lời để LÀM GÌ → khi gặng "được gì" thì bot **bịa quà** (mẫu hợp đồng/quy trình) → vi phạm luật chỉ-hứa-bộ-nhận-diện.
**Định hướng "lý do tiếp tục" (sếp 2026-06-24) — 2 ý:**
1. **Trò chuyện TÂM SỰ** chuyện nghề/đời — gần gũi (nhiều dealer nam thích tám với "em Linh").
2. **Để em hiểu cửa hàng → tư vấn/gợi ý** cách bán–vận hành tốt hơn từ kinh nghiệm cộng đồng.
   - *Bên mình CÓ báo giá thật → được KHOE; khách đòi xem ngay → "để em tư vấn kỹ rồi gửi sau" (không bịa thêm quà).*
**Khung fix (chờ sếp chi tiết rồi code):**
1. Câu tư vấn ĐẦU TIÊN = **bridge rõ** trong [context_builder.py](app/parlant/context_builder.py): truyền cờ `is_first_consultation` (không C1-C9 nào filled/skipped) → thêm câu "bộ thương hiệu xong rồi, giờ hỏi thêm vài điều để tư vấn/đồng hành; bận thì dừng cũng được".
2. Luật vào `principles_reply`: khách hỏi "được gì" → giải thích THẬT (tư vấn/đồng hành), **cấm hứa tài liệu/sản phẩm ngoài bộ nhận diện**.
3. Siết `safety` ([rules.yaml](config/rules.yaml)): "KHÔNG bịa mẫu hợp đồng / quy trình quản lý / biểu mẫu".
> *Tạm thời 11.2 đã làm task tư vấn bớt-chào-kết + hook chung; 11.1 sẽ nâng cấp bằng 2 ý cụ thể trên.*

### 9.2 🟡 Khen "giống người" + văn phong tự nhiên (đụng nhiều người nhất)
> **CHỐT (sếp 2026-06-16): KHÔNG bớt độ dài** — giữ khuôn 30-50 từ/2-3 câu + icon. CHỈ chỉnh khen + văn phong tự nhiên.
**Vấn đề:** khen generic, lặp tính từ sáo ("uy tín/chuyên nghiệp/tiềm năng") mỗi lượt → máy móc.
**Fix (CHỈ sửa `tone.general` — sếp chốt 2026-06-24, KHÔNG đụng principles_reply):**
- `tone.general` ([rules.yaml](config/rules.yaml)): khen BÁM cái cụ thể khách vừa nói (KHÔNG tính từ sáo "uy tín/chuyên nghiệp/tiềm năng"), đa dạng cách nói giữa các lượt, văn nói đời thường, không bắt buộc khen mỗi lượt. **Giữ độ dài 30-50 từ + icon.**
**Test:** chạy lại 3 kịch bản team, đọc CẢM GIÁC tự nhiên + hết lặp tính từ sáo. Rủi ro: siết quá tay → bot khô.

### 9.3 🟡 Mốc 3 ngày + trả "cần gì / quy trình / bao lâu"
**(A)** Task `zalo_handoff` (+ chốt brandkit) nêu rõ mốc: "logo + danh thiếp + video gửi qua Zalo **trong 3 ngày tới**".
**(B)** Luật vào `principles_reply`: khách hỏi quy trình/cần gì/bao lâu → trả RÕ rồi quay lại câu đang hỏi (vd "cần vài thông tin cơ bản ~4-5 phút; đội thiết kế làm logo+danh thiếp+video, gửi Zalo 3 ngày").
**Test:** "cần gì để có brandkit?", "bao lâu?", "quy trình?" → liệt kê rõ, không lảng.

### 10.4 🟡 est_team_size "vài ba người" bị MẤT (không lưu)
**Hiểu đúng:** KHÔNG phải LLM không hiểu — extractor trích "vài ba người" OK, nhưng **validator Python** `validate_est_team_size` ([validators.py:151](app/llm/extractors/validators.py#L151)) chỉ nhận **chữ số/range** (regex). "vài ba người" không có số → trả INVALID → **không lưu** → C3 rỗng dù khách đã trả lời.
**Fix (rule-driven, KHÔNG hardcode bảng tra — đúng gu):** sửa MÔ TẢ field `est_team_size` trong extractor ([schemas.py](app/llm/extractors/schemas.py)) → yêu cầu LLM **tự xuất SỐ ước lượng** từ cụm mơ hồ (vài/vài ba/dăm ba→3, một mình→1, chục→10, vài chục→30, "đông lắm"→bỏ trống, không bịa). LLM xuất số → validator nhận. Tuỳ LLM suy, không khoá case.
**Test:** "vài ba người"→~3, "chục người"→~10, "5-6 ông"→5-6, "đông lắm"→bỏ qua.

### 10.5 🟡 Khách CHỬI giữa chừng → bot "bỏ cuộc" chào kết
**Là gì:** đang hỏi 1 field mà khách chửi/cáu → bot ĐÔI KHI buông câu chào tiễn ("đã ghi nhận đủ rồi, chúc anh kinh doanh phát đạt") rồi dừng → **bỏ dở, mất lead**. Đáng lẽ phải xoa dịu + hỏi LẠI field. (Phần consent=no đã xong ở 11.2; đây là phần "chửi giữa chừng" còn lại.)
**Fix 2 phần:**
1. **Marker** `r"chúc.*(kinh doanh|buôn may|phát đạt|phát triển|thành công|may mắn|đắt hàng)"` vào `_PREMATURE_CLOSING_PATTERNS` ([turn_processor.py:55](app/parlant/turn_processor.py#L55)) — gate CHỈ chặn khi objective còn `_COLLECTING_*` (handoff thật vẫn cho "chúc"). Marker hẹp để khỏi tái lỗi 7.6 ("gửi mẫu qua Zalo").
   - ⚠️ Smoke 2026-06-17: bot hay nói "chúc … phát triển" lành tính giữa chừng → cân nhắc cụm hẹp hơn, test kỹ.
2. **Luật** `principles_reply`: khách chửi/bức xúc lúc đang hỏi 1 field → xoa dịu 1 câu, KHÔNG chào kết/chúc, hỏi LẠI đúng field. (Phase 8 đã chặn chửi-thành-field ở tầng extraction — đây là tầng REPLY, độc lập.)
**Test:** chửi giữa chừng → bot deflect + hỏi lại field; "gửi mẫu qua Zalo" KHÔNG bị bắt; handoff thật vẫn cho "chúc".

### 11.5 🟢 Slogan/nội dung — CHỈ 1 LUẬT "không bậy bạ" (tuỳ LLM hiểu)
**Sếp chốt:** giữ "số 1 VN"/khoa trương; CHỈ cần 1 luật chung "nội dung tục tĩu/bậy bạ → KHÔNG nhận làm field", để **LLM tự nhận diện** (KHÔNG liệt kê từ cấm, không khoá case).
**Fix:** phần lớn đã có ở luật 8.1 `principles_extraction` ([rules.yaml:40](config/rules.yaml#L40)) → chỉ **verify + thêm test** "slogan là &lt;chữ tục&gt;" không lưu. Nếu chưa đủ rõ → bổ sung 1 dòng luật tổng quát. KHÔNG đụng so-sánh/khoa trương.

---

## 2. VẬN HÀNH (trước sự kiện)
- [ ] **Deploy Railway** + env: `SQLITE_PATH=/data/chatbot_v2.sqlite3`, `APP_ENV=production`, `CONVERSATION_RUNTIME=gemini`. **KHÔNG set `WEB_WORKERS`**.
- [ ] **Load test 1 vòng TRÊN Railway** (`scripts/load_test.py` trỏ URL prod, ~$0.3).
- [ ] **Smoke 2-3 hội thoại thật prod** + check quota Gemini, trước giờ G.

---

## 3. CHỜ SẾP QUYẾT
- [ ] **#2** — C1: câu trả lời định tính ("khách quen nhiều") bị skip thay vì ghi nhận.
- [ ] Giọng: thỉnh thoảng còn "Dạ không sao anh" — siết thêm hay để vậy (tránh over-steer).
- ~~#4 Slogan "số 1 VN"~~ → **ĐÃ CHỐT: GIỮ** (chỉ chặn bậy nặng — xem 11.5).

---

## 4. SAU SỰ KIỆN (không khẩn)
- [ ] **P4.5** — thu lại field khi khách hợp tác về sau (combo A+C). Đổi hành vi runtime → cần test UX riêng.
- [ ] **Perf/infra:** log rotate (M4), close connection ở health_check (M5), gộp 2 write-tx idempotency (H5), read-only tx cho `poll_events`/`authorize` (H4). Redis (M6) chỉ khi nhiều worker.
- [ ] **Minor 9 tiêu chí:** tín hiệu phụ C3/C5/C9 (nhẹ).
- [ ] **Dọn 🔵 còn lại:** injection guard chỉ FLAG chưa chặn (H); `_BRANDKIT_CHOICE_FIELDS` định nghĩa 2 nơi (J); dọn sâu `_TONE_RULES` per-type; dedup 2 cờ phone_unverified. *(show_logo_brief/logo states + logo subsystem đã dọn ở cụm logo-gen.)* Xem [KIEN_TRUC_TONG_QUAN.md](KIEN_TRUC_TONG_QUAN.md) §5.
- [ ] **main_category không derive trong luồng gemini** — đã bỏ ô khỏi admin (11.4-B). Nếu Backend Scoring cần → derive NGOÀI write-tx (tránh nút thắt LLM-in-tx).

---

## 5. CHORES
- [ ] **Commit** — tách 4 cụm (9.4 / field-rác / fix-11 / logo-gen), chạy test trước mỗi commit.
- [ ] **Dọn 4 script nháp:** `scripts/_diag.py`, `_live_p6.py`, `_smoke_p6.py`, `_verify_extract.py` (giữ `load_test.py`, `profile_turn.py`).
- [ ] **Spec .md sync** (doc-only): LUAT_2A/2B/2C, EM_LINH_MKT_CORE/v7, KICH_BAN_1A — gỡ field đã xoá (district, phone_secondary, zalo, customer_segment_signal, category_stack, logo_initials, brand_name_short, initials_full, initial_single, slogan_options) cho khớp code.
- [ ] **FE (team khác):** render ảnh `component.samples` (preview 9.4b) trong khung chat + avatar/ảnh 3D Em Linh.

---

## 6. THAM KHẢO

### Runbook ngày sự kiện
1. Deploy bản đã load-test **trước ≥1 ngày**.
2. Env như §2. **KHÔNG `WEB_WORKERS`**.
3. Smoke 2-3 hội thoại prod trước giờ G.
4. Trong sự kiện: admin timeline + tail log Railway. **429 hàng loạt = quota** (không phải bug); **`db_busy` 503 = báo lại**.

### Kiến trúc + Gotcha
- **2 bộ não:** [1] Extraction (Gemini) → field+intent · [2] Workflow engine (code) → objective · [3] Reply gen (stub/gemini).
- `CONVERSATION_RUNTIME` default `parlant_local`=stub; prod=`gemini`.
- **Giữ SQLite, KHÔNG Postgres** (ràng buộc không đụng data prod + SQLite+WAL đủ vài trăm dealer/1 node).
- 🔴 **KHÔNG `WEB_WORKERS>1` với SQLite** (cross-process lock thrash).
- PowerShell `$env:X=""` = **XOÁ biến**. `GEMINI_MAX_CONCURRENCY=50` là điểm ngọt.
- ⚠️ Test `tests/` (root) có 2 smoke (phase4/5) — nhớ chạy CẢ `tests/` chứ không chỉ `tests/unit/`.
