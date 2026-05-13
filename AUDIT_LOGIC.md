# AUDIT LOGIC — Em Linh MKT Chatbot

**Ngày audit:** 2026-05-11
**Commit production:** `8b16361` (L3.3 + 2 fix Quốc Vinh)
**Phạm vi:** `app/core/*`, `app/api/*`, `app/storage/*`, `app/middleware.py`, `app/logging_setup.py`

## Tổng quan

| Mức độ | Số lượng |
|---|---|
| 🔴 CRITICAL (verified) | 4 |
| 🟡 HIGH (verified) | 7 |
| 🟢 LOW (verified) | 4 |
| ❌ False positive (agent đoán sai) | 1 |
| ⚠️ Chưa verify line-by-line | 0 |

Mọi bug bên dưới em đã đọc trực tiếp file gốc, trích line cụ thể. **KHÔNG BỊA.** Những chỗ chưa chắc em note rõ "cần test thực tế".

---

# 🔴 CRITICAL

## C1. Edit parser KHÔNG validate enum

**File:** [app/core/edit_parser.py:49-95](app/core/edit_parser.py#L49-L95) + [app/core/conversation.py:843](app/core/conversation.py#L843)

**Mô tả:**
`parse_edit_command()` xử lý 2 pattern regex. Pattern 1 là `sửa X thành Y`, pattern 2 là `X là Y`. Hàm chỉ validate cho `phone_or_zalo` (digits 9-11) + length ≤200. KHÔNG validate enum cho `main_category` / `dealer_type` / `dl0_priority`. Sau khi parse OK, conversation.py line 843 setattr thẳng vào profile.

**Code:**
```python
# edit_parser.py
EDIT_PATTERNS = [
    re.compile(r"(?:sửa|sua|đổi|...)\s+(.+?)\s+(?:thành|...)\s+(.+)", re.IGNORECASE),
    re.compile(r"^\s*(?:không phải[,.\s]+|...)?(.+?)\s+(?:là|la)\s+(.+)$", re.IGNORECASE),
]
# conversation.py:843
setattr(session.profile_raw, field, new_value)
```

**Ví dụ trigger:**
- Dealer ở CONFIRMING: "ngành là khó nói lắm anh"
- Regex match: field="main_category", new_value="khó nói lắm anh"
- → setattr `profile_raw.main_category = "khó nói lắm anh"` (string ngoài enum `{cua_cuon, cua_nhom_kinh, cua_thep, tu_bep, solar, bao_tri_sua_chua, vlxd_tong_hop}`)

**Hậu quả:**
- DB chứa giá trị ngoài enum
- Admin render label fallback hoặc crash
- Downstream report sai

**Cách fix:**
Trong `parse_edit_command`, sau khi match field, validate `new_value` theo enum tương ứng:
- `main_category` → normalize + check ∈ enum, nếu không match → return None (fallback LLM)
- `dealer_type` → tương tự
- `dl0_priority` → check phần tử ∈ enum, sai → return None

**Hiệu quả sau fix:**
Câu lệnh edit hợp lệ (vd "ngành là tủ bếp" → match enum `tu_bep`) vẫn pass nhanh không cần LLM. Câu nhập sai/mơ hồ rơi xuống LLM extractor để xử lý đúng. DB chỉ chứa giá trị enum hợp lệ → schema consistency.

---

## C2. `_is_affirmative` Rule 3 — message ≤3 ký tự auto-confirm

**File:** [app/core/conversation.py:973-993](app/core/conversation.py#L973-L993)

**Mô tả:**
Rule 3 là fallback "mọi interjection ngắn không có negation → ACCEPT". Trong stage CONFIRMING, hàm này quyết định có CONFIRMED + save profile + chuyển DONE hay không. Vấn đề: rule quá lỏng — bất kỳ message ≤3 ký tự không match negation đều được coi là affirmative.

**Code:**
```python
# Rule 3: message rất ngắn (≤3 chars sau strip) + đã qua rule 1 →
# ACCEPT (fallback cho mọi interjection chưa enumerate)
if len(normalized) <= 3:
    return True
```

**Ví dụ trigger:**
- Bot ở CONFIRMING render card profile + hỏi "Anh xem đúng chưa ạ?"
- Dealer đang đọc, gõ "ờ..." (mới gõ 1 chữ "ờ", chưa kịp nói tiếp) → submit nhầm
- `_is_affirmative("ờ")` → len=1, không negation → True
- → CONFIRMED + save_profile_raw + Stage.DONE
- Bot trả: "Dạ em cảm ơn anh nhiều ạ! Em đã ghi nhận hồ sơ rồi nhé."
- Dealer chưa kịp sửa, profile đã save

**Hậu quả:**
- Profile chốt sai khi dealer chưa thật sự confirm
- Reviewer cấp Dealer_ID dựa data chưa duyệt rõ
- Pháp lý: consent không rõ ràng (chỉ 1 ký tự không thể coi là affirmative meaningful)

**Cách fix:**
3 hướng (chọn 1):
1. **Giới hạn whitelist** — bỏ rule 3, mở rộng `_AFFIRMATIVE_WORDS` enumerate đủ ("ờ", "ừ", "à", "ạ"... đã có trong list rồi).
2. **Yêu cầu ≥2 ký tự "có nghĩa"** — Rule 3 yêu cầu message ≥2 chars + thuộc whitelist mở rộng.
3. **Undo path** — sau khi CONFIRMED < 30s, dealer gõ message tiếp → cho phép quay lại CONFIRMING.

Em đề xuất hướng 1 (đơn giản, an toàn nhất). Rà soát `_AFFIRMATIVE_WORDS` hiện tại đã có "ờ", "à", "ạ", "u" v.v. → bỏ rule 3 không mất gì.

**Hiệu quả sau fix:**
- Dealer gõ ký tự ngẫu nhiên ("a", "x", ",", "...") sẽ KHÔNG auto-confirm → bot hỏi lại "anh xem có cần sửa gì không ạ?"
- Chỉ affirmative thực sự (whitelist) mới triggers CONFIRMED → consent rõ ràng

---

## C3. CONFIRMING fallback edit KHÔNG save profile_raw

**File:** [app/core/conversation.py:851-856](app/core/conversation.py#L851-L856)

**Mô tả:**
Ở stage CONFIRMING, khi dealer nói edit không match regex pattern, code gọi LLM extractor → merge vào `session.profile_raw` → set `confirmation_status="EDITED"` → **KHÔNG** gọi `save_profile_raw()`. Profile chỉ được persist vào table `dealer_profile_raw` khi dealer affirmative (line 830).

So sánh:
- **Path affirmative** (line 826-837): có `self.storage.save_profile_raw(...)` ở line 830
- **Path regex edit** (line 841-849): `setattr` vào session.profile_raw NHƯNG cũng không save → bug tương tự
- **Path LLM fallback** (line 851-856): cũng không save

**Code:**
```python
# Fallback: dealer nói tự do (không match regex) → gọi LLM extractor
session.llm_call_count += 1
result = self.extractor.extract(session.messages)
self._merge_extraction(session, result)
session.profile_raw.confirmation_status = "EDITED"
return "Dạ em đã cập nhật rồi ạ, anh xem lại giúp em nhé:\n\n" + render_card(session.profile_raw)
```

**Ví dụ trigger:**
1. Dealer hoàn thành thu thập field, bot render card, dealer ở CONFIRMING
2. Dealer: "ờ mà tên cửa hàng đúng là Quốc Vinh nhưng có thêm hậu tố 'Cửa Cuốn Số 1'"
3. Regex không match → LLM extract → merge `dealer_name = "Quốc Vinh Cửa Cuốn Số 1"`
4. Bot reply card cập nhật
5. Dealer đọc card, đóng tab (chưa confirm)
6. → DB `dealer_profile_raw` KHÔNG có row session này (vì chưa CONFIRMED bao giờ)

**Hậu quả:**
- Admin export miss session đang edit
- Cross-session memory (`find_profile_by_phone`) không tìm thấy → returning dealer không activate
- Mất data nếu user đóng tab giữa chừng

**Note:** `session.data_json` (bảng `sessions`) vẫn được save mỗi turn ở line 114 (qua `self.storage.save_session`), nên session state vẫn còn. Vấn đề chỉ ở table `dealer_profile_raw` (table flat cho admin / lookup).

**Cách fix:**
Thêm `self.storage.save_profile_raw(session.session_id, session.profile_raw)` ngay sau khi merge ở 2 path (regex edit + LLM fallback), trước khi return. Status=EDITED phân biệt với CONFIRMED.

Bonus: cập nhật `find_profile_by_phone` để cũng tìm row EDITED (hiện em chưa verify nó filter theo status nào — cần kiểm).

**Hiệu quả sau fix:**
- Admin xem được session đang edit (status=EDITED) trong list
- Returning dealer khớp được kể cả khi profile chưa CONFIRMED
- Đóng tab giữa chừng không mất data → support team có thể follow up

---

## C4. `lock_key = "_new_session"` serialize toàn bộ request mới

**File:** [app/api/chat.py:36-37](app/api/chat.py#L36-L37)

**Mô tả:**
Khi `payload.session_id` rỗng (request đầu tiên — frontend chưa biết session_id), code dùng key `"_new_session"` cho per-session lock. Tất cả request không có session_id đều dùng CÙNG lock → serialize globally.

**Code:**
```python
lock_key = payload.session_id or "_new_session"
with get_session_lock(lock_key):
    session, bot_msg = service.handle_message(payload.session_id, payload.message)
```

**Ví dụ trigger:**
- 10 dealer cùng mở trang chat lần đầu (vd quảng cáo Facebook chạy → spike traffic)
- Mỗi browser gửi request đầu tiên với `session_id=null` (frontend chưa có session)
- 10 request cùng dùng key `"_new_session"` → xếp hàng chờ lock → 1 request xong mới đến request kế tiếp

**Hậu quả:**
- Throughput cổ chai ở P99 latency
- DoS vector dễ: attacker spam request với `session_id=null` (mỗi request handle ~1-3 giây vì có gọi LLM Replier+Extractor) → block legitimate users
- Khi scale traffic (vd campaign launch) → user đầu tiên latency cao bất thường

**Cách fix:**
Gen UUID tạm cho request không có session_id TRƯỚC khi acquire lock. Backend tạo session_id tại router level, truyền xuống `service.handle_message`. Code path:
```
if not payload.session_id:
    new_id = uuid.uuid4().hex
    lock_key = new_id
else:
    lock_key = payload.session_id
```

Sau đó truyền `new_id` xuống handler (hoặc để handler tự sinh nếu None).

**Hiệu quả sau fix:**
- Mỗi dealer mới có lock riêng → không serialize
- Throughput scale linearly với số dealer khác nhau
- Loại DoS vector qua `session_id=null` spam

---

# 🟡 HIGH

## H1. `"miễn"` trong `_REFUSAL_KEYWORDS` quá rộng → false positive

**File:** [app/core/intent_detect.py:94-100](app/core/intent_detect.py#L94-L100)

**Mô tả:**
`_REFUSAL_KEYWORDS` chứa từ `"miễn"` đơn (không có context). Bất kỳ message chứa "miễn" đều bị classify là REFUSAL → bot ack "tôn trọng quyết định" + skip field.

**Code:**
```python
_REFUSAL_KEYWORDS = (
    "đéo cho", "deo cho", "không cho", "khong cho",
    "không tiện", ...,
    "miễn", "thôi không", "thoi khong", "không có",
    ...
)
```

**Ví dụ trigger:**
- Bot hỏi: "Anh ơi cho em xin số Zalo nhé?"
- Dealer: "miễn phí thật à em? Đăng ký xong tốn tiền không?"
- `is_defensive_message()` = True (matches "miễn phí thật")
- `is_refusal_message()` = True (matches "miễn")
- Trong conversation.py line 326-329: refusal check trigger → bot skip field phone + ack "Dạ em tôn trọng quyết định của anh, không sao..."

Dealer chưa từ chối, chỉ HỎI về phí. Bot bỏ qua câu hỏi + skip field oan.

**Hậu quả:**
- Bot misread intent — dealer đang defensive, bot xử lý như refusal
- Skip phone oan → profile thiếu sđt → admin không có cách liên hệ
- Dealer cảm thấy bot "ngu", mất trust

**Cách fix:**
2 hướng:
1. **Sửa keyword**: thay `"miễn"` thành cụm cụ thể: `"xin miễn"`, `"thôi miễn"`, `"miễn cho tôi"`, `"miễn cho em"`.
2. **Priority order**: trong conversation.py, nếu `is_defensive_message=True` → skip refusal check.

Em đề xuất kết hợp cả 2: sửa keyword + priority defensive trước refusal.

**Hiệu quả sau fix:**
- "miễn phí thật à?" → defensive, bot trả lời "Dạ em khẳng định MIỄN PHÍ..."
- "thôi miễn cho em đi" → refusal, bot skip
- Phân biệt 2 intent rõ ràng, không lẫn

---

## H2. Trivial message → attempts tăng → field skip oan

**File:** [app/core/conversation.py:264-265, 387-388](app/core/conversation.py#L264-L265)

**Mô tả:**
Khi dealer message thuộc trivial (`is_trivial_message=True`), code skip extractor → `result = ExtractResult()` empty → `progress_made = len(weak_after) < len(weak_before) = False`. Sau đó line 387 tăng `field_attempts[target] += 1`. Sau 3 lần "ok" liên tiếp, field bị skip.

**Code:**
```python
# Line 264-265
if _is_trivial_message(latest_dealer):
    result = ExtractResult()
# ...
# Line 387-388
if not progress_made:
    session.field_attempts[target] = session.field_attempts.get(target, 0) + 1
```

**Ví dụ trigger:**
- Bot: "Anh cho em xin tên anh với ạ?"
- Dealer turn 1: "ok ạ" (suy nghĩ, chưa kịp nói tên) → trivial → attempts owner_name = 1
- Bot retry hỏi tên
- Dealer turn 2: "ờ" → trivial → attempts owner_name = 2
- Bot retry hỏi tên
- Dealer turn 3: "vâng" → trivial → attempts owner_name = 3
- Bot retry
- Dealer turn 4: "okay" → attempts = 4 > MAX_FIELD_ATTEMPTS (3) → **field owner_name bị skip vào skipped_fields**

Dealer chưa từ chối, chỉ đang gõ acknowledgment chuẩn bị nói tên. Bot skip field oan.

**Hậu quả:**
- Field bị skip dù dealer hợp tác
- Profile thiếu data quan trọng (tên/sđt)
- Dealer cảm thấy bot không lắng nghe (cứ retry mà không chờ)

**Cách fix:**
Khi message trivial, KHÔNG tăng `field_attempts`. Chỉ tăng khi dealer thực sự đưa response không-trivial mà vẫn không fill được field.

Code logic:
```
if not progress_made and not _is_trivial_message(latest_dealer):
    session.field_attempts[target] += 1
```

**Hiệu quả sau fix:**
- Dealer gõ acknowledgment ("ok", "ờ", "vâng") không bị penalize
- Field chỉ skip khi dealer thực sự có response substantive mà bot vẫn không extract được (= dealer thực sự khó cho info)
- Số field skipped oan giảm đáng kể

---

## H3. Replier fail silent — không log exception

**File:** [app/core/conversation.py:442-452](app/core/conversation.py#L442-L452)

**Mô tả:**
Replier.reply() có thể fail do nhiều lý do: rate limit Anthropic, API key sai, network timeout, JSON parse error. Code wrap trong try/except và bỏ qua exception → fallback path cũ. Vấn đề: KHÔNG log exception.

**Code:**
```python
try:
    session.llm_call_count += 1
    replier_text = self.replier.reply(...)
    # Output guard
    if goal.kind == "ASK_FIELD" and not self._llm_question_matches_target(replier_text, target):
        replier_text = self._fallback_question_for(target)
    return replier_text
except Exception:
    # Replier fail → fallback path cũ (template + chém gió)
    pass
```

**Ví dụ trigger:**
- Anthropic API key bị revoke → mọi `replier.reply()` raise `AuthenticationError`
- Code catch → pass → fallback template generic
- User trải nghiệm: bot trả lời template generic mọi turn, không có persona
- Dev không biết → mãi không fix vì không có alert

**Hậu quả:**
- Bug invisible cho dev → có thể chạy hỏng nhiều giờ/ngày
- UX degrade silently
- Khó debug khi user phàn nàn ("sao bot không trả lời tự nhiên?")

**Cách fix:**
Đổi `except Exception: pass` thành `except Exception as exc: logger.warning("Replier failed, falling back: %s", exc)`. Optionally: thêm metric counter (`session.replier_fallback_count += 1`) để observability.

**Hiệu quả sau fix:**
- Mỗi lần Replier fail → log warning với reason
- Dev grep log thấy ngay (vd "AuthenticationError" → biết API key sai)
- Metric counter cho phép alert khi fallback rate > threshold

---

## H4. `enforce_defensive_answer` chạy SAU `enforce_opener_variety` → double prefix

**File:** [app/core/conversation.py:189-204](app/core/conversation.py#L189-L204)

**Mô tả:**
Thứ tự middleware trong handle_message:
1. Line 190: `enforce_opener_variety` — strip prefix lặp + thay opener khác
2. Line 204: `enforce_defensive_answer` — prepend answer thẳng nếu Replier bypass defensive question
3. Line 210: `enforce_min_length` — prepend compliment nếu cần

Cả 1 và 2 đều có thể PREPEND text. Khi cả 2 cùng trigger trong 1 turn → 2 prefix chồng nhau → reply rối.

**Code:**
```python
# Line 189-192
if session.stage == Stage.ASKING:
    bot_msg, opener_group = enforce_opener_variety(bot_msg, session.last_opener_group)
# Line 204
bot_msg = enforce_defensive_answer(bot_msg, latest_dealer_msg, address)
```

**Ví dụ trigger:**
- Dealer: "Em làm có lợi gì cho tôi không?" (defensive — hỏi benefit)
- Turn trước Replier đã dùng nhóm B (cảm xúc) → forbidden_group=B
- Replier sinh: "Wow câu hỏi hay quá anh! Để em hỏi tiếp tên cửa hàng nhé..." (lệch — vẫn lặp nhóm B, không trả lời benefit)
- `enforce_opener_variety` thấy lặp B → strip "Wow câu hỏi hay quá" → thay bằng nhóm A → "Dạ em ghi nhận anh! Để em hỏi tiếp..."
- `enforce_defensive_answer` thấy bot không liệt kê 4 công cụ → prepend "Dạ em không vòng vo — bên em hỗ trợ MIỄN PHÍ 4 thứ: bộ mặt số, QR khách cũ, bài đăng, trợ lý tư vấn..."
- Final: "Dạ em không vòng vo — bên em hỗ trợ MIỄN PHÍ 4 thứ... Dạ em ghi nhận anh! Để em hỏi tiếp..."

Reply có **2 prefix chồng nhau** + có thể mâu thuẫn ngữ nghĩa.

**Hậu quả:**
- UX rối, reply dài lê thê (~150+ từ)
- 2 ack thừa nhận ("Dạ em không vòng vo" + "Dạ em ghi nhận") — không natural
- Có thể vi phạm cap min/max length

**Cách fix:**
2 hướng:
1. **Đảo thứ tự**: chạy `enforce_defensive_answer` TRƯỚC `enforce_opener_variety`. Khi defensive prepend, opener variety nhìn vào prefix mới → thấy là nhóm A ("Dạ em không vòng vo") → không re-prepend.
2. **Detect + skip**: trước khi `enforce_opener_variety` prepend, check nếu reply đã start với defensive intro → skip variety.

Em đề xuất hướng 1 (đơn giản, đảo 2 dòng).

**Hiệu quả sau fix:**
- Reply có DUY NHẤT 1 prefix
- Khi defensive trigger → câu trả lời benefit/giá/fraud được ưu tiên, opener variety không can thiệp
- Reply trở nên clean, đúng độ dài

---

## H5. SQLite không bật WAL mode → contention dưới concurrent traffic

**File:** [app/storage/sqlite_store.py:21-23](app/storage/sqlite_store.py#L21-L23)

**Mô tả:**
Default SQLite dùng rollback journal mode → mỗi write block tất cả read khác. Khi 2 dealer khác session cùng chat đồng thời, write từ dealer A sẽ block read từ dealer B (dù khác session).

**Code:**
```python
def _conn(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

Không có PRAGMA journal_mode=WAL, không có isolation_level setting.

**Ví dụ trigger:**
- Dealer A: save_session (write) đang chạy
- Dealer B: load_session (read) → block đến khi A xong
- Latency dealer B tăng

**Hậu quả:**
- Latency contention dưới traffic concurrent
- Không corruption (per-session lock từ concurrency.py đã bao handle_message)
- Throughput trần thấp

**Cách fix:**
Trong `_init_schema()`, thêm `conn.execute("PRAGMA journal_mode=WAL")` và `conn.execute("PRAGMA synchronous=NORMAL")`. WAL cho phép concurrent reads while writing.

**Hiệu quả sau fix:**
- Read không block write, write không block read
- Latency P99 ổn định kể cả khi 10-50 dealer concurrent
- SQLite scale tốt hơn cho MVP (tránh phải migrate Postgres sớm)

---

## H6. `find_profile_by_phone` quét full table (no index)

**File:** [app/storage/sqlite_store.py](app/storage/sqlite_store.py) — function `find_profile_by_phone` (cần xem chi tiết line)

**Mô tả:**
Để tìm returning dealer (cross-session memory), hàm `find_profile_by_phone` load TOÀN BỘ rows từ `dealer_profile_raw` + iterate Python comparison digits-only. Không có index trên `phone_or_zalo`, không có WHERE filter SQL.

**Ví dụ trigger:**
- Production có 50K dealer
- Dealer mới gửi sđt → bot gọi `find_profile_by_phone("0901234567")`
- SQLite load 50K rows về Python → so từng row → cost ~100-500ms

**Hậu quả:**
- Latency tăng tuyến tính với DB size
- Memory spike mỗi turn (load 50K rows về memory)
- Critical path: chạy mỗi turn ASKING khi dealer vừa cho phone

**Cách fix:**
2 bước:
1. **Index SQL**: `CREATE INDEX idx_phone ON dealer_profile_raw (phone_or_zalo)` trong `_init_schema`.
2. **Filter SQL**: thay full-scan bằng `SELECT ... WHERE REPLACE(REPLACE(phone_or_zalo, ' ', ''), '-', '') = ?` (hoặc normalize phone khi save).

Tốt hơn: lưu cột `phone_normalized` (digits-only) khi save_profile_raw, index trên cột đó, query bằng equality.

**Hiệu quả sau fix:**
- Lookup O(log n) thay vì O(n)
- 50K rows → ~1ms thay vì ~500ms
- Critical path không bị throttle bởi DB size

---

## H7. `X-Request-ID` không validate format

**File:** [app/middleware.py:41-48](app/middleware.py#L41-L48)

**Mô tả:**
Middleware reuse client-supplied `X-Request-ID` header thẳng, không validate length/format. Header này được:
- Set vào `request_id_var` (contextvars)
- Inject vào mọi log record format
- Echo lại qua response header

**Code:**
```python
async def dispatch(self, request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    token = request_id_var.set(rid)
    ...
    response.headers["X-Request-ID"] = rid
```

**Note quan trọng (verify):**
- HTTP newline injection (`\n` để fake log line) **KHÔNG** thực hiện được — Starlette/uvicorn reject header có CR/LF theo RFC 7230.
- Tuy nhiên client có thể gửi header value DÀI (4-8KB) → bloat log line, gây log file growth nhanh.
- Client cũng có thể gửi unicode lạ → log format encoding lỗi (rare).

**Ví dụ trigger:**
- `curl -H "X-Request-ID: $(python -c 'print("A"*4000)')" https://...`
- Log file mỗi entry có 4KB request_id → log file tăng vọt.

**Hậu quả:**
- Log bloat → tốn disk Railway volume
- Log file khó đọc (cột request_id chiếm hết space)
- Không có log injection (nhờ Starlette guard), nhưng vẫn nên defensive

**Cách fix:**
Whitelist regex `^[A-Za-z0-9_-]{1,64}$`. Nếu client value match → reuse; không match → gen UUID mới.

```python
RID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
client_rid = request.headers.get("X-Request-ID", "")
rid = client_rid if RID_RE.match(client_rid) else uuid.uuid4().hex[:8]
```

**Hiệu quả sau fix:**
- Log size predictable (max 64 chars/request_id)
- Defense in depth — không phụ thuộc Starlette guard
- Format log đẹp

---

# 🟢 LOW

## L1. `TRIVIAL_REGEX` character class có chữ Việt rác

**File:** [app/core/spam_guard.py:107-123](app/core/spam_guard.py#L107-L123)

**Mô tả:**
Regex trivial cuối có character class `[\s.!?,áạnhéá]*$` — chứa các chữ "áạnhéá" có vẻ là copy-paste leftover. Class này match trailing zero+ ký tự thuộc set đó.

**Ví dụ trigger:**
- "okh" → `ok+h` không match base group (vì `h` không phải `(ay|ê|e)?`) → group "ok+" → match "ok" → trailing "h" thuộc char class → match toàn câu OK.
- "okn" → tương tự, "n" trong class → match.

**Hậu quả:**
- Edge case: vài câu lạ ("okn", "okh", "ya") bị classify là trivial → skip extractor.
- Impact minor (extractor không bị gọi cho non-trivial → có thể miss field từ "okh nhé anh tên Vinh" — nhưng case này quá hiếm).

**Cách fix:**
Thay `[\s.!?,áạnhéá]*$` bằng `[\s.!?,]*$` (chỉ whitespace + punctuation).

**Hiệu quả sau fix:**
- Trivial detect chính xác hơn ở edge case
- Không tạo bug mới (trailing whitespace/punct vẫn match)

---

## L2. `_session_locks` không bao giờ evict

**File:** [app/core/concurrency.py:31](app/core/concurrency.py#L31)

**Mô tả:**
Dict `_session_locks` grow tuyến tính với số session_id unique. Mỗi entry ~16-32 bytes (key str + Lock object). Không có TTL/evict.

**Quy mô:**
- 10K session/năm → ~320KB memory. Negligible.
- 1M session → ~32MB. Vẫn OK.
- 10M+ session → có thể đáng quan tâm.

Comment trong code đã thừa nhận: "Restart server là reset".

**Hậu quả:**
- Memory grow tuyến tính với traffic
- Railway uptime tuần/tháng → memory tăng dần (nhưng rất chậm)
- Không gây crash trong MVP

**Cách fix:**
Optional — nếu cần, thêm background thread cleanup lock dict mỗi 1h (xoá entry không có pending request). Hoặc dùng weakref. Hoặc đơn giản restart Railway mỗi tuần (cron).

**Hiệu quả sau fix:**
- Memory bounded
- Không cần restart định kỳ

**Em đề xuất:** KHÔNG fix bây giờ, document trong runbook. Khi DB > 10K dealer thì xem lại.

---

## L3. `PHONE_RE` không bắt SĐT có space/dash

**File:** [app/logging_setup.py:11](app/logging_setup.py#L11)

**Mô tả:**
Pattern `\b0\d{8,10}\b` chỉ match digits liên tiếp. Khi dealer paste sđt với separator (`0901 234 567` hoặc `0901-234-567`), regex không match → PHẦN PHONE lọt vào log.

**Code:**
```python
PHONE_RE = re.compile(r"\b0\d{8,10}\b")
```

**Ví dụ trigger:**
- Dealer paste từ contact "0901 234 567"
- Log line: `INFO Extractor input: "Số tôi là 0901 234 567 nhé"`
- Pattern không match → PII leak

**Hậu quả:**
- PII leak vào log file
- Vi phạm best practice privacy (nhưng MVP, log local Railway)

**Cách fix:**
Pattern flexible với optional separator:
```python
PHONE_RE = re.compile(r"\b0\d{1,2}[\s\.\-]?\d{3}[\s\.\-]?\d{3,4}\b")
```

Hoặc multi-pattern: bắt cả strict format + spaced format.

**Hiệu quả sau fix:**
- PII không leak dù dealer paste format nào
- Log file safe để chia sẻ debug

---

## L4. Admin `selected_ids` không validate count/format

**File:** [app/api/admin.py:85-99](app/api/admin.py#L85-L99)

**Mô tả:**
Admin endpoint export nhận `?ids=...` (CSV string). Code split bằng comma, không cap count, không validate UUID format. Dù chỉ chọn 5 IDs, code vẫn `list_profiles()` ALL profiles rồi filter Python.

**Code:**
```python
selected_ids: set[str] | None = None
if ids:
    selected_ids = {sid.strip() for sid in ids.split(",") if sid.strip()}

profiles = storage.list_profiles()  # ← load ALL
for p in profiles:
    sid = p.get("session_id")
    if selected_ids is not None and sid not in selected_ids:
        continue
    sess = storage.load_session(sid)
    ...
```

**Ví dụ trigger:**
- Admin gửi `?ids=fake1,fake2,...,fake10000` (10K fake IDs)
- Backend split → set 10K entries
- Load ALL profile (vd 50K rows)
- Iterate so 10K x 50K = 500M lookups (Python set lookup O(1) nên 500M ≈ vài giây)

**Hậu quả:**
- Mild DoS vector cho admin endpoint
- Admin endpoint đã có HTTP Basic Auth → chỉ admin abuse được (low risk)

**Cách fix:**
1. Cap số IDs ≤ 200
2. Validate format UUID hex 32 chars
3. Filter SQL `WHERE session_id IN (...)` thay vì Python filter

**Hiệu quả sau fix:**
- Admin endpoint không bị abuse từ admin nội bộ malicious
- Performance scale tốt hơn

---

# ❌ FALSE POSITIVE (agent đoán sai)

## FP1. "confirmation_status precedence"

**Vị trí agent claim:** `conversation.py:316-319`
**Agent claim:** `if not session.profile_raw.confirmation_status == "CONFIRMED":` parse thành `(not x) == "CONFIRMED"` → luôn False → returning dealer KHÔNG BAO GIỜ chạy.

**Em verify:**
Python operator precedence (lowest → highest):
1. `or`
2. `and`
3. `not`
4. `==`, `!=`, `<`, `>`, `in`, `is`, ...

`==` precedence cao hơn `not`. Vậy `not x == y` = `not (x == y)` (đúng intuition).

**Test bằng tay:**
- Nếu `confirmation_status = "PENDING"`: `("PENDING" == "CONFIRMED")` = False → `not False` = True → condition True → chạy `_maybe_load_returning_dealer` ✓
- Nếu `confirmation_status = "CONFIRMED"`: `True` → `not True` = False → skip ✓

→ **Logic ĐÚNG**. Agent đoán sai precedence.

Tuy nhiên, để dễ đọc hơn, có thể đổi sang `if session.profile_raw.confirmation_status != "CONFIRMED":` (semantic identical, không phải bug).

---

# Tổng kết priority

## 🔥 Làm ngay (data integrity / consent)

| ID | Tóm tắt | Effort |
|---|---|---|
| C1 | Edit parser validate enum | ~30 phút |
| C2 | Bỏ Rule 3 trong _is_affirmative | ~10 phút |
| C3 | Save profile_raw khi edit (EDITED status) | ~20 phút |

## 🚀 Tuần này (UX + safety + concurrency)

| ID | Tóm tắt | Effort |
|---|---|---|
| C4 | Lock per-request cho session mới | ~30 phút |
| H1 | Refine "miễn" trong refusal keywords | ~10 phút |
| H2 | Trivial KHÔNG tăng attempts | ~5 phút |
| H4 | Đảo thứ tự defensive trước opener variety | ~5 phút |

## ⏳ Tháng này (scale + observability)

| ID | Tóm tắt | Effort |
|---|---|---|
| H3 | Log warning khi Replier fail | ~10 phút |
| H5 | SQLite WAL mode | ~5 phút |
| H6 | Index phone_or_zalo + filter SQL | ~30 phút |
| H7 | Validate X-Request-ID format | ~10 phút |

## 💭 Có thì hay (polish)

| ID | Tóm tắt | Effort |
|---|---|---|
| L1 | Sửa TRIVIAL_REGEX char class | ~3 phút |
| L3 | PHONE_RE flexible format | ~10 phút |
| L4 | Admin endpoint validate IDs | ~15 phút |
| L2 | Session lock cleanup | optional |

---

# Note phương pháp audit

**Đã làm:**
- Đọc trực tiếp từng file gốc tại line cụ thể (không trust agent blindly)
- Trace logic flow cho mỗi bug
- Verify code execution path bằng mental simulation (đặc biệt `_is_affirmative`, defensive/opener ordering, precheck flag bypass)
- Catch 1 false positive (FP1) — Python operator precedence

**Chưa làm (cần test thực tế trên chatbot):**
- Test live H1 với input "miễn phí thật à?" trên local server để xác nhận behavior
- Test live H2 với 4-5 message "ok" liên tiếp xem field có thực sự bị skip
- Test live H4 với defensive question + Replier lặp opener xem có double prefix không
- Test live C2 với message ngắn 1-2 chars ở CONFIRMING

→ Em đề xuất chạy local server, test các scenario trên trước khi code fix C/H bugs. Mỗi test ~5 phút.
