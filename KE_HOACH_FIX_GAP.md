# KẾ HOẠCH FIX GẤP — trước deploy event (2026-06-30)

> Từ test live "Dương Cửa Cuốn". 3 việc GẤP. Mục tiêu: chốt nhanh, deploy được trong ~1 tiếng. Polish (9.2/10.4/10.5/11.5) để SAU.

---

## FIX 1 🔴 Phone: số sai bị LLM tự cắt cho khớp, KHÔNG hỏi lại
**Hiện tượng:** khách gõ `091383589545` (12 số) → bot lưu `09138358954` (11 số) → lên thẻ luôn, KHÔNG báo sai/hỏi lại.
**Gốc (đã xác minh):** prompt extractor [intake_fact_extractor.py:233](app/llm/intake_fact_extractor.py#L233) ghi *"chỉ lấy 1 số CHÍNH vào phone_or_zalo **(10-11 chữ số)**"* → LLM **tự cắt 12→11 số** cho khớp gợi ý → `validate_phone` (nhận 10-11) cho qua. Validator đúng, nhưng bị LLM "qua mặt".
**Fix:**
1. Bỏ gợi ý "(10-11 chữ số)" + "chỉ lấy 1 số chính" trong prompt → LLM lấy **NGUYÊN số dealer gõ**, KHÔNG tự sửa/cắt. (rules.yaml slot 1.3 dòng 80-81 chỉnh tương ứng.)
2. `validate_phone` là **cổng chặn DUY NHẤT**: số ≠ đúng định dạng → reject → workflow tự hỏi lại (task phone_invalid 10.1 "cần 10-11 số").
3. **CHỐT (sếp): (a) 10-11 số** — giữ `validate_phone` hiện tại, chỉ sửa prompt để LLM không tự cắt.
**Test:** `091383589545`→hỏi lại · `0913835895`(10)→nhận · `09138358954`(11)→nhận · `abc`→hỏi lại · "0913 835 895"→nhận (strip space).
**File:** `intake_fact_extractor.py`, `config/rules.yaml`, (có thể) `validators.py` nếu chọn (b).

---

## FIX 2 🔴 ĐỔI LUỒNG: bỏ show ảnh preview + CHỐT NGAY sau brandkit (gộp issue 2 + 3)
**Lý do:** kho ảnh mẫu KHÔNG kịp làm; đoạn chuyển sang tư vấn C1-C9 (cần 11.1) chưa mượt + dài.

**Luồng MỚI (sếp chốt 2026-06-30) — GIỮ 9 tiêu chí, chỉ chuyển thẻ chốt LÊN sớm:**
```
CŨ:  logo → preview ảnh → 9 tiêu chí → thẻ chốt → handoff
MỚI: required → brandkit (consent→màu→phong cách→slogan)
       → câu "nhân viên bên em sẽ cho anh xem ảnh mẫu qua Zalo" (KHÔNG show ảnh)
       → THẺ CHỐT (HỒ SƠ CƠ BẢN — anh duyệt)   ← chuyển LÊN ngay sau logo
       → (duyệt) → 9 TIÊU CHÍ tư vấn (GIỮ NGUYÊN, chuyển XUỐNG sau thẻ) → handoff
```
→ Thẻ chốt không bị 9 tiêu chí chặn phía trước (thẻ chỉ có info cơ bản → chốt được ngay). 9 tiêu chí **vẫn hỏi đủ**, chỉ nằm SAU thẻ.

**Cụ thể (code):**
1. [workflow_engine.py](app/parlant/workflow_engine.py) `iter_pending_steps`: bỏ bước `show_brandkit_preview` + **chuyển vòng C1-C9 ra SAU review** → sau brandkit, `steps` (pre-review) rỗng → ra `show_profile_review` ngay.
2. `compute_objective`: sau khi `review_status=CONFIRMED` mà C1-C9 còn pending → trả `collect_optional_field` (tư vấn tiếp); C1-C9 xong/"đủ rồi" → `zalo_handoff`. (Tức C1-C9 chạy ở pha SAU-CONFIRMED.)
3. Câu "nhân viên sẽ cho xem ảnh": nhét vào task chốt slogan / `show_profile_review` ([context_builder.py](app/parlant/context_builder.py)) — "đội ngũ gửi mẫu + bộ hoàn chỉnh qua Zalo trong 3 ngày".
4. Bỏ pick_samples/đính ảnh ở [chat_service.py](app/services/chat_service.py). Marker `brandkit_preview_shown` thành dead — để lại vô hại.

**Hệ quả:** 11.1 (bridge) tạm KHÔNG cần (9 tiêu chí giờ sau thẻ chốt, không phải đoạn chuyển trước chốt). Reframe tư vấn (9.4c) GIỮ — áp cho 9 tiêu chí sau chốt.

**Test (full multi-turn):** required → brandkit → "nhân viên gửi ảnh qua Zalo" → **thẻ chốt NGAY** (chưa hỏi đội thợ) → "duyệt" → **rồi mới hỏi 9 tiêu chí** (đội thợ/hãng/…) → "đủ rồi" → handoff.

---

## THỨ TỰ THỰC THI (≈1 tiếng)
1. **FIX 1** (phone) — sửa prompt + rules, test.
2. **FIX 2** (đổi luồng) — sửa `iter_pending_steps` (bỏ preview + C1-C9) + câu "sẽ cho xem ảnh" + bỏ pick_samples ở chat_service.
3. **Cập nhật test** đang khoá thứ tự cũ (test_p94, test_phase4/5, test_p7...) cho luồng mới + full suite xanh.
4. **Live smoke** 1 hội thoại đúng luồng mới + phone sai.
5. **COMMIT + push** (Railway lấy từ git).
6. **Deploy Railway** + env (`SQLITE_PATH=/data/...`, `APP_ENV=production`, `CONVERSATION_RUNTIME=gemini`, `GEMINI_API_KEY`, `ZALO_GROUP_URL`; KHÔNG `WEB_WORKERS`) → smoke prod.

## ĐÃ CHỐT (sếp 2026-06-30)
1. **Phone:** 10-11 số — LLM lấy nguyên số, validate chặn, sai → hỏi lại.
2. **9 tiêu chí:** GIỮ NGUYÊN, chuyển XUỐNG sau thẻ chốt (logo → thẻ chốt → 9 tiêu chí → handoff).
