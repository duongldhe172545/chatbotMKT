# SYNC LOG — Em Linh MKT Documentation

> **Mục đích:** Log mọi lần sửa các file tài liệu lõi + kịch bản + luật
> kỹ thuật. Dùng để audit chéo + đảm bảo sync giữa các file.
>
> **Cập nhật file này mỗi khi sửa bất kỳ file tài liệu nào.**

---

## Versioning (semver)

Mỗi file có version `vMAJOR.MINOR.PATCH`:

| Type | Ý nghĩa | Ảnh hưởng file khác? |
|---|---|---|
| **MAJOR** (vX.0.0) | Thay đổi paradigm — đổi flow chính, đổi định nghĩa slot, đổi schema | ⚠️ **BẮT BUỘC review TOÀN BỘ file khác** |
| **MINOR** (vx.Y.0) | Thêm/đổi rule mới (vd thêm slot, thêm tiêu chí) | Review file phụ thuộc (cross-ref) |
| **PATCH** (vx.y.Z) | Sửa wording / typo / minor fix | Không cần review file khác |
| **NEW** | Tạo file mới | — |
| **DELETE** | Xoá file | Review CORE để bỏ ref |

---

## Quy tắc sync (BẮT BUỘC)

1. **Sửa CORE bump MAJOR/MINOR** → review CẢ File 1 (A/B/C) + File 2
   (A/B/C). Mỗi file review xong → bump PATCH (để xác nhận đã review).
2. **Sửa File 1 module X bump MAJOR/MINOR** → review File 2 module X
   cùng tên + CORE.
3. **Sửa File 2 module X bump MAJOR/MINOR** → review File 1 module X
   + CORE.
4. **PATCH** → chỉ log, không cần review file khác.

**Quan hệ module:**

```
File 1A (core script) ↔ File 2A (core logic)
File 1B (tone library) ↔ File 2B (LLM engineering)
File 1C (edge case) ↔ File 2C (infrastructure)
```

---

## Versions hiện tại

| File | Version | Ngày update | Trạng thái |
|---|---|---|---|
| `EM_LINH_MKT_CORE.md` | **v3.0.5** | 2026-05-15 | ✅ Active |
| `0_GLOSSARY.md` | **v1.4** | 2026-05-15 | ✅ Active — đọc trước khi sửa file khác |
| `0_STRATEGY.md` | **v1.4** | 2026-05-15 | ✅ Active — rationale **12 decision lớn (D1-D12)** |
| `KICH_BAN_1A_core.md` | **v0.3.0-draft** | 2026-05-18 | 📝 Draft — refactor "không khoá case" |
| `KICH_BAN_1B_tone.md` | **v0.1.1-draft** | 2026-05-15 | 📝 Draft đầy đủ (chờ duyệt) |
| `KICH_BAN_1C_edgecase.md` | **v0.1.3-draft** | 2026-05-15 | 📝 Draft đầy đủ (chờ duyệt) |
| `LUAT_2A_core.md` | **v0.2.5-draft** | 2026-05-18 | 📝 Draft — refactor "không khoá case" |
| `LUAT_2B_llm.md` | **v0.1.2-draft** | 2026-05-15 | 📝 Draft đầy đủ (chờ duyệt) |
| `LUAT_2C_infra.md` | **v0.1.5-draft** | 2026-05-18 | 📝 Draft — refactor "không khoá case" |

**Tài liệu nguồn (read-only, không sửa trong dự án này):**
- `EM_LINH_MKT_MVP_VOICE_INTAKE_DEALER_v01-1_1.md` — MVP v01 (Vinh)
- `EM_LINH_MKT_v7.md` — Em Linh v7 chính thức
- `chatbot_tieu_chi_dealer.md` — 9 tiêu chí scoring (Backend Scoring nội bộ)

---

## Log (mới nhất trên cùng)

Format mỗi dòng:

```
ngày | tác giả | file | version cũ → mới | type | ảnh hưởng | mô tả ngắn
```

| Ngày | Tác giả | File | Version | Type | Ảnh hưởng | Mô tả |
|---|---|---|---|---|---|---|
| 2026-05-26 | duong + Antigravity | **BUG FIX BATCH — 6 bugs từ live test** | code patch | PATCH | Prompt + ack + address confirm + address_form dynamic | **6 bugs confirmed qua API test:** (1) `system_prompt.py` — tune reply 40-50 từ, nịnh nhẹ có căn cứ, mở đầu đa dạng (không luôn "Dạ"), CẤM bịa context/địa phương/cập nhật vào danh sách, CẤM "cái tên nghe rất [adj]", CẤM bịa "đông đảo/công trình lớn/cơ hữu". (2) `_conv_helpers.py` — `_gen_direct_ack()` + `_PARTIAL_FIELD_QUESTIONS` dùng dynamic address_form thay hard-code "anh"; thêm `_adapt_address_form()` regex replace pronoun trong template questions; mở rộng `_strip_storage_cliche()` bắt "cập nhật vào danh sách/hệ thống". (3) `_conv_asking.py` — address confirm check raw message (LLM extractor hay tự thêm tỉnh); dùng dynamic address_form trong confirm question; mở rộng `_DISTRICT_PROVINCE_GUESSES` thêm quận HCM + Đà Nẵng. (4) Test update: `test_system_prompt.py` + `test_ack_generator.py` cập nhật assertion cho tone mới. **Tests: 1194 pass.** |
| 2026-05-18 | duong + Claude | **REFACTOR "KHÔNG KHOÁ CASE" (3 spec + 4 code file)** | xem các file riêng | MINOR | Loại bỏ pattern hard-code mapping "X → Y" cụ thể khỏi cả spec + code | User chốt nguyên tắc: "không khoá case, chỉ khoá luật — chỉ giữ enum/validation/regex, mọi suy luận case-by-case phải để LLM gen với context". Audit phát hiện 4 code vi phạm + 2 spec vi phạm. **Spec:** (1) **1A v0.2.2→v0.3.0-draft** — § 7.2 cấu trúc Closing "Hook đặc sản tỉnh (lookup)" → "Hook địa phương (LLM gen tự do)"; § 7.3 thay `{province_specialty_hook}` bằng `{local_hook}`; § 7.4 viết lại — BỎ lookup table 50 tỉnh, đổi sang LLM_FAST gen 1-2 câu, Phase 1 luôn rỗng; § 7.6 thêm "Cấm hardcode mapping tỉnh → đặc sản". (2) **2A v0.2.4→v0.2.5-draft** — F2A.3 Scope 2 bỏ `province_specialty: str`; F2A.8 viết lại — BỎ `PROVINCE_SPECIALTY_TABLE` 50 entries + 3-tier fallback, thay = LLM gen local_hook hoặc rỗng; acceptance test mới PASS = "không chứa hard-code đặc sản". (3) **2C v0.1.4→v0.1.5-draft** — F2C.7 bỏ `data/province_specialty.json` khỏi danh sách + thêm note "data file chỉ chứa LUẬT/ENUM, cấm lookup table"; F2C.5 cache bỏ "Province specialty" entry, thêm "Local hook (LLM)" Phase 2 cache 7d. **Code:** (4) **`app/core/closing.py`** — bỏ `_build_specialty_hook()`, bỏ `{specialty_hook}` từ 2 template, signature `render_closing(province=None, consent=None)` giữ nguyên backward compat nhưng `province` arg chưa dùng. (5) **`app/cache/data_loaders.py`** — xoá `get_specialty()`, `get_province_specialty_map()`, `find_category_by_keyword()`. Thêm `get_category_name(code)`. (6) **`data/province_specialty.json`** — XOÁ file. (7) **`data/main_category_enum.json` v1.0→v1.1** — bỏ `keywords[]` array khỏi 7 category, chỉ giữ `code` + `name`. (8) **`app/models/schema.py`** + **`migrations/001_init.sql`** — bỏ field `province_specialty` trong Pydantic; DB column DEPRECATED giữ backward compat. (9) **`app/core/md_exporter.py`** — bỏ render "Đặc sản tỉnh". (10) Tests update: `test_data_loaders.py` bỏ 5 test specialty/keyword, thêm test guard `no_keywords_field`; `test_greeting_closing.py` đổi `test_closing_with_specialty_hook` thành `test_closing_does_not_lock_specialty` (assert KHÔNG chứa "phở"/"vịt quay" trong output); `test_schema.py` đổi 12 derive fields → 11 + guard `province_specialty NOT IN fields`. **Tests: 560 pass / 0 fail.** |
| 2026-05-18 | duong + Claude | **PHASE 1 IMPLEMENTATION COMPLETE** (29 source file + 17 test file, 8 commit) | code v0.1.0 (branch refactor/v8) | NEW | Toàn bộ codebase Phase 1 v8 — branch refactor/v8, KHÔNG push remote (local only theo chỉ đạo user) | Phase 1 MVP done — 6 round commit, **534 tests pass** (unit + integration + e2e). **Round 1 (`202d39c`, `35eecee`, `ec78b42`)**: spec baseline + bootstrap (.env.example v8 LLM_FAST/QUALITY, requirements.txt google-genai, pytest.ini, .gitignore) + migrations/001_init.sql (3 bảng sessions/dealer_profile_raw/admin_queue). **Round 2 (`894ae90`)**: schema Pydantic (10 enum incl 6 action + 15 flag + 5 dealer type) + state (Stage/Action/Intent/Flag) + session lifecycle (lazy timeout) + 17 slot definitions (6 REQUIRED + 10 OPTIONAL + 1 THÔNG BÁO). 92 unit tests. **Round 3 (`0c7d8c0`)**: intent regex Layer 1 (7 intent) + state machine 6 action (PARTIAL_RETRY + DEFER) + 17 slot templates (Phase 1 đầy đủ 3 slot 1.1/1.2/4.0) + system prompt builder ≤600 token. +181 tests. **Round 4 (`e30cc23`)**: LLM client unified 2-tier (LLM_FAST/QUALITY full Gemini) + 3 tool extractor schemas + validators (phone digits 10-11, address blacklist, consent enum strict) + ack generator (tier routing per dealer_type) + fallback safe_ack + retry exponential backoff. +154 tests. **Round 5 (`e025ff4`, `a3a0265`, `8c416c7`)**: data loaders (63 tỉnh + 50 specialty + 7 category JSON) + sanity 5-point + greeting (3 biến thể) + closing (yes/no/soft-end + hook đặc sản) + card_renderer 5 phần ASCII + conversation orchestrator 296 dòng (stage dispatcher). +85 tests. **Round 6 (`<commit>`)**: SQLiteStore CRUD 3 bảng (JSON serialize cho slot_attempts/flags/history) + FastAPI endpoint POST /api/chat + status endpoint + main.py wire (CORS + static + health) + config Pydantic Settings + static/chat.js adapt v8 response format + integration tests (sqlite_store CRUD + cascade delete + find_by_phone) + e2e tests (FastAPI TestClient happy flow + consent=no path). +22 tests. **Total: 534 tests pass, 0 fail, ~5s run**. Code build trên spec consistency batch 1-4 (CORE v3.0.5 + STRATEGY D1-D12 + 6 file rule). **App boot verified**: GET /health = 200, POST /api/chat init session = greeting trả về, stage GREETING. Pilot demo: `python -m app.main` → http://localhost:8000. **KHÔNG push remote** — user yêu cầu test local trước, lên production sau. |
| 2026-05-15 | duong + Claude | **SPEC CONSISTENCY BATCH 4 (8 file)** | xem các file riêng | MINOR | Tài liệu lõi — audit lần cuối 3 agent tìm thêm 6 CRITICAL + 17 MEDIUM + minor. Fix toàn bộ + add retry rule mới (DEFER 2-consecutive) + 4 quyết định lớn (D9-D12) | Audit lần cuối phát hiện 6 CRITICAL: schema DB conflict, PARTIAL_RETRY enum miss 5 chỗ, "17 tool" thay vì 16, F2C.8 thiếu 4 trigger, broken pointer § B.2/§ J.6/§ J.7. User feedback NUANCE retry: "3 tổng nhưng không hỏi 3 lần liên tiếp, sau 2 lần tạm dừng rồi quay lại — dealer turn đầu hay test không skip vội". Chi tiết: **(1) CORE v3.0.4→v3.0.5** — A.3 "4-6 phút" → "4-5 phút" (sync 1A Greeting); § H.1 OPTIONAL heading "16+6=22" → "16 OPTIONAL" + add note Scope 1 tổng = 28; § L.1 sync § A.3 (bot không "dựng xong" mà "ghi nhận + chuẩn bị qua Zalo"); § L.2/L.3/L.4 PENDING → v1 draft (clarify bot không render). **(2) GLOSSARY v1.3→v1.4** — § Action 5 → 6 (thêm DEFER + columns consecutive/total); § Session timeout "30 phút" → "1 giờ"; § Cache TTL thêm row "System prompt build". **(3) STRATEGY v1.3→v1.4** — add D9 (Phase 1 cut 3 REQUIRED), D10 (consent=no skip 4.1/4.2), D11 (retry 3/2/DEFER + PARTIAL_RETRY), D12 (flag 15 chia 4 nhóm); D8 cross-ref wiki-link → markdown. **(4) 1A v0.2.1→v0.2.2-draft** — § 1.1 retry "2 lần" → "3 tổng, 2 liên tiếp"; § 1.4 + § 1.6 mới — quy ước retry DEFER với why box (dealer turn đầu test/nghịch không skip vội); § 1.5 thêm note 6 slot multi-field còn lại + 2 ví dụ; § 2.2 "12 cụm" → "11 + 1 no-bridge"; slot 4.1 "OPTIONAL" → "THÔNG BÁO"; slot 2.5 biến thể 3 đổi "Tiện đây" → "À cho em hỏi". **(5) 1B v0.1.0→v0.1.1-draft** — § 3.3 `HIGH_THRESH` → `PIVOT_DELTA_REQUIRED`. **(6) 2A v0.2.3→v0.2.4-draft** — F2A.4 list 6 action (thêm DEFER) + step 2.7/2.8 mới (DEFER + re-check); tham số config thêm `MAX_RETRY_CONSECUTIVE=2`, `DEFER_RECHECK_AFTER_N_SLOTS=2`, `MAX_DEFER_PER_SLOT=1`; F2A.1 tuple 6 action; F2A.5 retry algorithm refactor (consecutive + total separate); F2A.7 thêm `SLOT_TO_REQUIRED_FIELDS` mapping (fix undefined function); F2A.1 Cross-ref § B.2 → § J.1; F2A.2 fix broken markdown table; F2A.3 + F2A.7 "3 scope" → "4 scope"; F2A.3 Scope 4 "Gemini" → "LLM_QUALITY". **(7) 2B v0.1.1→v0.1.2-draft** — F2B.2 "17 tool" → "16 tool"; F2B.4b mới — Defensive + tâm sự handler prompt template + LLM_QUALITY tier + acceptance test. **(8) 2C v0.1.3→v0.1.4-draft** — F2C.1 schema refactor: 1 bảng JSON → **3 bảng riêng** (sessions/dealer_profile_raw 28 trường/admin_queue), sync KE_HOACH § 2.4 DDL canonical, index `phone_or_zalo`; F2C.8 admin queue trigger 9 → 13 (thêm hallucinate/pii_leak HIGH, brand_not_in_whitelist MEDIUM, voice_quality_poor LOW); note 2 flag KHÔNG trigger queue. **(9) KE_HOACH_REFACTOR v1.3→v1.4** — § PHẦN 5 thêm task 0a/0b/0c/0d bootstrap (.env.example, requirements.txt, pytest.ini + .gitignore, .pre-commit-config.yaml optional); cross-ref header bump CORE v3.0.5. |
| 2026-05-15 | duong + Claude | **SPEC CONSISTENCY BATCH 3 (6 file)** | xem các file riêng | PATCH/MINOR | Tài liệu lõi — user feedback 4 điểm sau khi đọc CORE: (1) bot KHÔNG render quà trực tiếp, (2) case là ví dụ tượng trưng, (3) slot multi-field partial fill handler, (4) 6 vs 7 REQUIRED — chọn giữ 6 | User đọc CORE phát hiện 4 vấn đề. Fix 3 điểm (1/2/3), giữ điểm 4 (6 REQUIRED). Chi tiết: **(1) CORE v3.0.3→v3.0.4** — § A.3 Promise: thêm note "bot KHÔNG render logo/video/kế hoạch trong chat — luôn qua Zalo / ứng dụng nhỏ + designer team / hệ thống ngoài". Cấu trúc lại 6 item quà thành 2 nhóm rõ "Sau cuộc trò chuyện (qua Zalo)" + "3 ngày sau (team + hệ thống push)". Thêm vào "KHÔNG hứa": "Render logo/video/kế hoạch ngay trong chat". **(2) 1A v0.2.0→v0.2.1-draft** — § 3.2 Greeting 3 biến thể: thêm câu "Bộ thương hiệu này em sẽ gửi anh **qua Zalo** ngay sau khi mình chốt thông tin xong" + lưu ý chung "mọi promise gắn với Zalo, không phải trong chat ngay". § 1.5 mới: quy ước slot multi-field PARTIAL fill (KHÔNG count retry). § 4 slot 1.1: add "PARTIAL fill handler" template (3 case: cho owner_name thiếu dealer_name / ngược lại / mơ hồ). **(3) 1C v0.1.2→v0.1.3-draft** — § DISCLAIMER mở rộng: nhấn mạnh ack mẫu + marker + threshold + script là VÍ DỤ TƯỢNG TRƯNG, KHÔNG khóa cứng. **(4) 2A v0.2.2→v0.2.3-draft** — F2A.4 thêm action thứ 5 `PARTIAL_RETRY` + step 2.6 algorithm: slot multi-field (1.1, 1.2, 2.1, 2.4, 2.5, 2.6, 3.3) dealer fill 1 phần → ack + hỏi field còn thiếu, KHÔNG count `slot_attempts`. **(5) 2C v0.1.2→v0.1.3-draft** — thêm § DISCLAIMER toàn cục về config value/threshold/schema example. **(6) GLOSSARY v1.2→v1.3** — bảng `Action` mở rộng 4 → 5 action (thêm `PARTIAL_RETRY`) với column `slot_attempts` để clarify khi nào count, khi nào không. |
| 2026-05-15 | duong + Claude | **SPEC CONSISTENCY BATCH 2 (5 file)** | xem các file riêng | PATCH | Tài liệu lõi — sau audit lần 2 phát hiện 12 finding mới + 4 gap, fix toàn bộ trước Phase 1 implement (user yêu cầu "làm tài liệu gốc ok đi đã, không commit") | Audit lần 2 (sau batch 1) tìm thêm 2 CRITICAL + 5 MEDIUM + 5 MINOR + 4 gap inconsistency mới. Apply theo nguyên tắc user: "CORE = nguyên tắc chung, file con = mở rộng detail". Chi tiết: **(1) CORE v3.0.2→v3.0.3** — N2 § H.2 Card 5 phần: rút gọn template ASCII chi tiết → principle ngắn (5 phần là gì) + pointer File 1A § 6.3 cho template chi tiết. Sync card 5 phần đúng theo 1A/GLOSSARY (gộp "Kênh online" + thêm "Trong 3 ngày tới"); N4 § J.4 sanity "5/7 trường cơ bản" → "6 REQUIRED slot (1.1,1.2,1.3,2.1,2.2,4.0) hoặc flag required_missing"; N5 § H.1 Nhóm 4 "Gemini chấm" → "LLM_QUALITY chấm (pilot Gemini 2.5 Pro)" (hoàn tất model-agnostic refactor); N6 § H.1 "~14 OPTIONAL" → "16 OPTIONAL + 6 RAW signal = 22"; N7 § H.1 Nhóm 4 camelCase (dealerStatus/adminAreaCode/editorName) → snake_case (Pydantic convention); N8 4 dead anchor `[PENDING](#phần-o--pending)` → text plain; N9 § I.2 thêm note "C4 source `chatbot_tieu_chi_dealer.md` gọi 'Trách nhiệm cuối'"; G2 § I.2 thêm row "Tổng trọng số 1.00 ✓"; G3 § B.3 thêm cross-ref → File 2A § F2A.6. **(2) STRATEGY v1.2→v1.3** — N3 D3 trade-off "11 LLM extractor + 11 retry handler" → "10 + 10 (slot 4.1 không có extractor)". **(3) 2A v0.2.1→v0.2.2-draft** — N1 bỏ 2 broken pointer "CORE § J.6" + thêm hierarchy note; N5 Scope 4 model-agnostic; N6 "~14" → "16+6=22"; N10 F2A.1 pointer "§ B.2 (workflow)" → "§ J.1 + § G" (đúng 2 chỗ); G4 F2A.4 algorithm thêm step 2.5 — branch sớm slot 4.0 consent=no → mark skip 4.1/4.2 + đi CONFIRMING (sync File 1A handler). **(4) 2C v0.1.1→v0.1.2-draft** — N1 bỏ 3 broken pointer "§ J.7" → "§ K.5 (spam guard 4 layers)" + thêm hierarchy note (F2C.2 heading + Cross-ref + bảng cuối). **(5) 1C v0.1.1→v0.1.2-draft** — N1+N11 fix 3 broken pointer trong bảng cross-ref § 13: row 5 Abuse "§ E.4" → "§ B.4", row 6 Troll/Inject "§ J.7" → "§ K.5", row 10 Address blacklist "§ J.6" → "§ E.5". **(6) KE_HOACH_REFACTOR v1.2→v1.3** — KE_HOACH-1 bump cross-ref header sang version mới sau batch + thêm pointer GLOSSARY/STRATEGY; KE_HOACH-2 viết lại changelog v1.2 đầy đủ; KE_HOACH-3 § 2.3 Flag enum thêm column "Nhóm" (4+5+4+2=15). Bump 5 file spec ACTIVE + 1 file plan. |
| 2026-05-15 | duong + Claude | **SPEC CONSISTENCY refactor (8 file)** | xem các file riêng | PATCH/MINOR | Toàn bộ spec/plan — fix cross-ref inconsistency phát hiện qua cross-ref audit, KHÔNG đổi paradigm/rule | Cross-ref audit phát hiện 3 CRITICAL + 5 MEDIUM + 4 MINOR inconsistency. Fix toàn bộ trước Phase 1 implement (user yêu cầu "kỷ luật trước"). Chi tiết: **(1) `EM_LINH_MKT_CORE.md` v3.0.1→v3.0.2** — § H.1 tiêu đề "schema chia 3 scope" → "4 scope" (sync nội dung đã có 4 scope). **(2) `0_GLOSSARY.md` v1.1→v1.2** — § 1 đổi count "11 OPTIONAL" → "10 OPTIONAL + 1 THÔNG BÁO" (slot 4.1 không fill field); § 4 mở rộng flag table 8 → 15 flag chia 4 nhóm (sync 2A enum + 2C trigger); § 7 tách entry KE_HOACH_REFACTOR thành 4 pointer chi tiết (overview/schema/action/folder). **(3) `0_STRATEGY.md` v1.1→v1.2** — D3 rationale đổi count "6+11" → "6+10+1 thông báo". **(4) `LUAT_2A_core.md` v0.2.0→v0.2.1-draft** — F2A.3 Scope 3 `flags` enum mở rộng 6 → 15 flag (sync 1C edge cases + 2C admin queue triggers + KE_HOACH § 2.3). Trước đây thiếu 9 flag gây Pydantic validation error runtime. **(5) `LUAT_2B_llm.md` v0.1.0→v0.1.1-draft** (gộp cả model-agnostic 2026-05-15 chưa bump header) — F2B.2 province "50 tỉnh" → "63 tỉnh" + clarify 2 file dataset (`province_list.json` 63 vs `province_specialty.json` 50); F2B.8 G3 drift guard `FORBIDDEN_VOCAB_WITH_DEALER` thêm "Marketing"/"Namecard"/"Slogan"/"batch" + mở rộng `AUTO_REWRITE`. **(6) `LUAT_2C_infra.md` v0.1.0→v0.1.1-draft** — F2C.3 Concurrency thêm "Phase deployment" table (Phase 1-3 in-memory, Phase 4 Redis). Sync STRATEGY phụ lục "Redis defer". **(7) `KICH_BAN_1C_edgecase.md` v0.1.0→v0.1.1-draft** — bump header (model-agnostic injection marker đã sửa nhưng version chưa bump). **(8) `KE_HOACH_REFACTOR.md` v1.1→v1.2** — cross-ref `EM_LINH_MKT_CORE.md` bump v3.0.0 → v3.0.1 (đồng bộ với SYNC_LOG). |
| 2026-05-15 | duong + Claude | **MODEL-AGNOSTIC refactor (8 file)** | xem các file riêng | MINOR/PATCH | Toàn bộ spec/plan — không đổi rule, chỉ đổi cách tham chiếu model | User quyết pilot dùng **Gemini API** (rẻ) nhưng yêu cầu spec **model-agnostic** ("đưa rule/lõi cho mọi model"). Refactor 8 file: (1) `0_STRATEGY.md` v1.0→v1.1 — thêm **D8 model strategy** (2-tier `LLM_FAST`/`LLM_QUALITY`) + reverse Phụ lục "Vì sao bỏ Gemini" → "Vì sao model-agnostic". (2) `0_GLOSSARY.md` v1.0→v1.1 — thêm 5 thuật ngữ (Session, Greeting, Closing, Card, History) + LLM tier abstraction; fix Scope 4 vendor + Redis → infra cache + clarify scope "Marketing" cấm chỉ trong dialog. (3) `LUAT_2B_llm.md` v0.1.0→v0.1.1-draft — 6 chỗ model config Haiku/Sonnet → `LLM_FAST`/`LLM_QUALITY`. (4) `KICH_BAN_1C_edgecase.md` v0.1.0→v0.1.1-draft — injection marker "bot Claude" → "bot Claude/Gemini/ChatGPT/GPT". (5) `EM_LINH_MKT_CORE.md` v3.0.0→v3.0.1 — PHẦN N stack info đổi sang tier abstraction, ghi rõ pilot Gemini + fallback Claude. (6) `KE_HOACH_REFACTOR.md` v1.0→v1.1 — § 0.7 reverse (GIỮ gemini.py làm pilot adapter, không drop); § 0.9 routing table dùng tier; action 12 + risk row + folder tree cập nhật. (7) `BOI_CANH_DU_AN.md` v1.0→v1.1 — tech stack ghi model-agnostic + pilot Gemini + fallback Claude + Backend Scoring riêng. (8) `DANH_GIA_TAI_LIEU.md` v1.0→v1.1 — gap ADR từ ❌THIẾU → ⚠️PARTIAL (đã có STRATEGY D1-D8); task ADR riêng defer. |
| 2026-05-14 | duong + Claude | 0_GLOSSARY + 0_STRATEGY | — → v1.0 | NEW | Bổ sung cho 6 file kịch bản/luật | Tạo 2 file foundation: `0_GLOSSARY.md` (định nghĩa thuật ngữ chung — slot/turn/field, scope, dealer_type, intent, flag, escalation, sanity, guards, cache TTL, forbidden vocab, lookup table) + `0_STRATEGY.md` (7 decision lớn với rationale + trade-off + when to reconsider: D1 tách 2 tier file, D2 stage forward-only, D3 17 slot, D4 retry asymmetric, D5 default tone Bận, D6 1 tool/slot, D7 tách Scope 4 Backend Scoring). Mục đích: cho cả Duong + Claude làm việc CHÍNH XÁC nhất, không hiểu nhầm thuật ngữ, 3-6 tháng sau đọc lại còn nhớ vì sao chọn approach. |
| 2026-05-14 | duong + Claude | BOI_CANH_DU_AN | — → v1.0 | NEW | (file cho AI khác, không bump spec) | Tạo file `BOI_CANH_DU_AN.md` — bối cảnh dự án + 7 câu hỏi cross-validation gửi AI khác đánh giá độc lập approach tài liệu hiện tại. Self-contained, AI khác đọc không cần đọc thêm file nào. |
| 2026-05-14 | duong + Claude | DANH_GIA_TAI_LIEU | — → v1.0 | NEW | (file meta-evaluation, không bump spec) | Tạo file `DANH_GIA_TAI_LIEU.md` — em (Claude) tự đánh giá approach 6 file đối chiếu industry standard (arc42 / PatternFly / BDD-Gherkin / Rasa / Anthropic). Score 6.6/10. Đề xuất 5 task adjust: + Glossary + ADR + Strategy + Gherkin acceptance test + sửa transparency policy. |
| 2026-05-14 | duong + Claude | KE_HOACH_REFACTOR | — → v1.0 | NEW | (kế hoạch refactor, không bump spec) | Tạo file `KE_HOACH_REFACTOR.md` — kế hoạch refactor v7 → v8: phân tích phản biện (12 điểm adjust so với plan agent), schema mapping cụ thể (33 cột cũ → schema mới 4 scope), cấu trúc folder mới (12 sub-folder app/), 4 phase migration (Phase 1 MVP 6-8 ngày), 24 action items Phase 1 concrete, 7 risk + mitigation, 8 open questions cần Duong quyết |
| 2026-05-14 | duong + Claude | File 2C | — → v0.1.0-draft | NEW | (đã có đủ 6 file 1A/1B/1C/2A/2B/2C — sẵn sàng review chéo) | Tạo File 2C — 8 rule infrastructure: F2C.1 session lifecycle + DB schema, F2C.2 spam guard (rate limit IP/message + abuse score), F2C.3 concurrency (Redis lock per session + queue), F2C.4 timeout + retry policy (LLM/DB/Redis + fallback safe ack), F2C.5 cache (LLM intent + STT + address + slogan), F2C.6 monitoring + alerting (4 dimension health/perf/quality/business), F2C.7 data files (9 JSON files versioning), F2C.8 admin queue + review workflow (priority + SLA) |
| 2026-05-14 | duong + Claude | File 1C | — → v0.1.0-draft | NEW | (chưa có 2C để review chéo) | Tạo File 1C — 12 edge case + escalation script: defensive lặp, tâm sự dài, refusal lặp, abuse cá nhân, troll/inject, garbage, voice fail, im lặng, address blacklist, brand unknown, phone invalid + 3 cấp escalation L1/L2/L3 |
| 2026-05-14 | duong + Claude | File 2B | — → v0.1.0-draft | NEW | (chưa có 1C/2C để review chéo) | Tạo File 2B — 8 rule LLM engineering: F2B.1 system prompt template, F2B.2 extractor schema 1-tool-per-slot, F2B.3 intent classifier Layer 2, F2B.4 ack generator per dealer type, F2B.5 voice STT brand correction, F2B.6 address parser 63 tỉnh, F2B.7 auto-derive brand_name_short/initials/slogan, F2B.8 4 guard (injection + hallucinate + drift + PII leak) |
| 2026-05-14 | duong + Claude | File 1B | — → v0.1.0-draft | NEW | (chưa có 1C để review chéo) | Tạo File 1B — Tone Library 4 nhóm dealer (Lửa Lò + Khoe + Lo + Bận) với ack pattern, cấm, edge case, pivot rule khi đại lý chuyển nhóm giữa session, default mode "Bận" cho 3 turn đầu |
| 2026-05-14 | duong + Claude | File 2A | v0.1.0-draft → v0.2.0-draft | MINOR | (chưa có file khác để review chéo) | Hoàn thành 8 rule: F2A.1 Stages + F2A.2 Intent detection + F2A.5 Slot priority + retry + F2A.6 Dealer type detection + F2A.7 Sanity check + F2A.8 Greeting/Closing engine (có PROVINCE_SPECIALTY_TABLE 50 tỉnh) |
| 2026-05-14 | duong + Claude | File 1A | v0.1.0-draft → v0.2.0-draft | MINOR | (chưa có file khác để review chéo) | Hoàn thành: Section 3 Greeting (3 biến thể) + đủ 17 slot Section 4 + Section 5 Phản ứng đặc biệt (note rule cao) + Section 6 Confirmation Card (5 phần ASCII + render rule null + cấm C-code) + Section 7 Closing (3 biến thể + hook tỉnh + path consent=no) |
| 2026-05-14 | duong + Claude | File 2A | — → v0.1.0-draft | NEW | — | Tạo file 2A — viết khung + 2 rule mẫu (F2A.3 schema 4 scope + F2A.4 smart advance state machine) |
| 2026-05-14 | duong + Claude | File 1A | — → v0.1.0-draft | NEW | — | Tạo file 1A — viết khung Section 1+2 + mẫu 3 slot (1.1, 1.2, 4.0) cho user duyệt style |
| 2026-05-14 | duong + Claude | CORE | v2.0.0 → v3.0.0 | MAJOR | (chưa có file 1/2 để review) | 17 slot (thêm 3.5 cho C4) + Required/Optional logic + chia schema 4 scope (chatbot/Scoring backend/Designer team) + bỏ rubric chấm điểm khỏi CORE (chỉ Backend Scoring nội bộ) + bỏ PHẦN O PENDING + cảnh báo "không hiển thị mã C-code với đại lý" |
| 2026-05-14 | duong + Claude | CORE | v1.0.0 → v2.0.0 | MAJOR | — | Rewrite từ V7 + MVP v01 hợp nhất. Bỏ happy case Anh Tùng. Add PHẦN D (tâm lý đại lý), E (ranh giới bot), F (domain knowledge), J (luật khóa), K (recovery), M (voice TTS), N (vận hành). Đổi từ "16 micro-turn fixed" → "4 chủ đề + flexible flow". |
| 2026-05-14 | duong + Claude | CORE | — → v1.0.0 | NEW | — | Tạo file CORE v1 — hợp nhất MVP v01 + V7. |
| 2026-05-14 | duong + Claude | SYNC_LOG | — → v1.0.0 | NEW | — | Tạo file SYNC_LOG này — quy ước versioning + sync rule. |

---

## Quy trình edit (workflow)

```
1. ĐỀ XUẤT sửa
   ├─ Nêu rõ: file nào / section nào / lý do
   └─ Discuss với owner (Duong)

2. APPLY sửa
   ├─ Bump version (MAJOR/MINOR/PATCH theo bảng trên)
   ├─ Update changelog đầu file (nếu file có changelog section)
   └─ Update cross-ref table cuối file (nếu cần)

3. ĐÁNH GIÁ tác động
   ├─ Check cross-ref → list file khác cần review
   └─ Nếu MAJOR/MINOR → đi tới bước 4
   └─ Nếu PATCH → skip tới bước 5

4. REVIEW file khác (nếu MAJOR/MINOR)
   ├─ Đọc file khác, check có cần sửa theo không
   └─ File khác cần sửa → quay lại bước 2 cho file đó
   └─ File khác KHÔNG cần sửa → bump PATCH file đó để mark "đã review"

5. LOG vào SYNC_LOG.md (file này)
   └─ Thêm 1 dòng mới ở đầu bảng Log
```

---

## Convention naming

| File | Path | Mô tả |
|---|---|---|
| CORE | `/EM_LINH_MKT_CORE.md` | Tài liệu lõi (đã có) |
| SYNC_LOG | `/SYNC_LOG.md` | File log này |
| File 1A | `/RULE_KICH_BAN/KICH_BAN_1A_core.md` | Core script — 17 slot question/ack |
| File 1B | `/RULE_KICH_BAN/KICH_BAN_1B_tone.md` | Tone library — 4 nhóm dealer |
| File 1C | `/RULE_KICH_BAN/KICH_BAN_1C_edgecase.md` | Edge case — troll/abuse/escalation/explain |
| File 2A | `/RULE_KICH_BAN/LUAT_2A_core.md` | Core logic — state machine + intent + schema |
| File 2B | `/RULE_KICH_BAN/LUAT_2B_llm.md` | LLM engineering — prompt + extractor + guards |
| File 2C | `/RULE_KICH_BAN/LUAT_2C_infra.md` | Infrastructure — spam guard + concurrency + storage + monitoring |

---

## Cross-ref hint (sẽ điền khi viết các file)

| Khi sửa | Có thể ảnh hưởng |
|---|---|
| CORE PHẦN G (slot mapping) | File 1A (câu hỏi mẫu), File 2A (state machine) |
| CORE PHẦN H (schema) | File 2A (schema validation), File 2B (extractor) |
| CORE PHẦN I (9 tiêu chí) | File 2A (raw signal mining), File 2B (extractor schema) |
| CORE PHẦN B (tone) | File 1B (tone library), File 2B (prompt) |
| CORE PHẦN D (tâm lý) | File 1B (4 nhóm dealer), File 1C (escalation) |
| CORE PHẦN E (ranh giới) | File 1C (escalation script), File 2B (boundary guard) |
| CORE PHẦN J (luật khóa) | File 2A (sanity check), File 2C (spam guard) |
| CORE PHẦN K (recovery) | File 2C (timeout, retry, fallback) |

---

**LƯU Ý:** Đừng để log grow vô hạn. Mỗi 50 dòng log → tạo section
"Archived" + chỉ giữ 20 dòng gần nhất ở bảng chính.
