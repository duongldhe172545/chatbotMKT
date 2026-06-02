# Hướng fix Linh MKT: không đập đi xây lại, nhưng phải thay bộ não hội thoại

Ngày viết: 2026-05-29

File này giải thích chi tiết vì sao hướng sửa Linh MKT **không nên là xóa hết làm lại**, dù hiện tại Linh đang đi chệch khá nhiều ở tầng chat. Kết luận chính:

> Không đập đi xây lại không có nghĩa là vá lặt vặt. Hướng đúng là **giữ khung kỹ thuật có giá trị**, nhưng **thay bộ điều phối hội thoại slot-first bằng planner LLM-first**.

---

## 1. Linh đang chệch ở đâu?

Linh không chệch ở mục tiêu. Mục tiêu vẫn đúng:

- thu data dealer;
- chốt profile/brandkit;
- lưu lại session/profile;
- có admin review;
- có guard chống spam, prompt injection, hallucination, PII leak;
- có test khá nhiều.

Linh chệch ở **cách tổ chức hội thoại**.

Hiện tại happy path của Linh gần như là:

```text
user message
  -> detect intent
  -> nhìn current_slot
  -> extract theo current_slot
  -> state_machine decide_action
  -> LLM gen ACK ngắn
  -> engine append câu hỏi template slot kế
  -> reply_pipeline sửa/validate
  -> save session/profile
```

Flow này hợp với form có chat UI. Nhưng để giống "em MKT thông minh", flow đúng phải là:

```text
user message + full history + profile hiện tại
  -> LLM hiểu lượt nói như một người tư vấn
  -> rút mọi fact có ích, kể cả ngoài thứ tự
  -> quyết định nên hỏi gì tiếp theo
  -> viết một reply hoàn chỉnh
  -> code validate, chống bịa, lưu profile, kiểm tra required fields
```

Tức là Linh không cần bỏ schema/test/storage. Linh cần đổi vai trò: **LLM làm người điều phối hội thoại, code làm lan can kiểm soát**.

---

## 2. Vì sao không nên đập đi xây lại?

### 2.1. Vì vấn đề chính không nằm ở toàn bộ repo

Trong `D:/Chatbot_dealer`, app hiện có khoảng 80 file code và 51 file test. Cấu trúc cũng không tệ:

- `app/api/chat.py`: API contract và save flow đã có.
- `app/models/schema.py`: `DealerProfileRaw`, `SessionState` khá rõ.
- `app/storage/sqlite_store.py`: persistence đã chạy.
- `app/llm/client.py`, `app/llm/gemini.py`: LLM adapter đã tách.
- `app/llm/extractors/validators.py`: validator field có thể giữ.
- `app/slots/definitions.py`: danh sách field/slot là checklist tốt.
- `app/core/card_renderer.py`: confirmation card có thể dùng tiếp.
- `app/admin/*`: admin queue/review là giá trị thật.
- `tests/unit/*`, `tests/integration/*`, `tests/e2e/*`: có nền test để refactor an toàn.

Nếu xóa hết, ta mất cả những phần không sai. Sau đó lại phải xây lại:

- schema;
- session lifecycle;
- storage;
- API;
- admin;
- rate limit;
- guard;
- tests;
- confirmation card;
- LLM client;
- validators.

Những phần đó không làm Linh kém thông minh. Phần làm Linh kém thông minh là **orchestrator ASKING và cách dùng slot/template để lái hội thoại**.

### 2.2. Đập đi xây lại dễ lặp lại lỗi cũ

Nếu làm lại từ đầu mà vẫn bắt đầu bằng câu hỏi:

> cần những field nào, slot nào hỏi trước, retry thế nào?

thì rất dễ quay lại đúng kiến trúc hiện tại: schema-first, slot-first, state-machine-first.

Sai lầm không phải do code cũ xấu đơn thuần. Sai lầm là **đặt schema ở ghế lái**. Làm lại từ đầu mà vẫn đặt schema ở ghế lái thì vẫn ra một con Linh khác nhưng cùng bệnh.

### 2.3. Cần thay não, không cần thay xương

So sánh dễ hiểu:

- Xương của Linh: API, DB, schema, tests, admin, validators.
- Não hiện tại của Linh: `current_slot + state_machine + ack_generator + templates`.

Xương vẫn dùng được. Não đang lái sai. Vậy nên hướng fix là **cấy bộ não hội thoại mới**, không phá toàn thân.

### 2.4. Refactor từng bước giúp kiểm chứng được

Nếu làm lại toàn bộ, khi kết quả kém ta không biết lỗi ở đâu:

- prompt mới chưa tốt?
- schema mới sai?
- storage mới bug?
- UI/API mới lỗi?
- logic save chưa đúng?

Nếu giữ khung cũ và thay dần orchestration, ta đo được rõ:

- cùng API;
- cùng DB;
- cùng profile schema;
- cùng validator;
- chỉ khác bộ điều phối chat.

Lúc đó nếu Linh thông minh hơn, ta biết đúng là do planner mới. Nếu chưa hơn, ta chỉnh planner/prompt/eval, không lạc sang các tầng khác.

---

## 3. Mục tiêu kiến trúc mới

Mục tiêu không phải bỏ hết deterministic logic. Mục tiêu là đổi thứ tự ưu tiên:

```text
Hiện tại:
  code quyết định hội thoại
  LLM phụ trách extract/ACK

Mục tiêu:
  LLM quyết định hội thoại
  code kiểm chứng, chặn sai, lưu dữ liệu
```

Tên tạm: **Planner-first conversation engine**.

Flow mới:

```text
POST /api/chat
  -> load session + profile
  -> global guards cơ bản
  -> intake_planner nhìn full context
  -> planner trả về facts + reply + next_focus
  -> validator kiểm tra facts
  -> merge profile an toàn
  -> coverage/state guard cập nhật missing fields
  -> reply guard chống bịa/vocab/PII
  -> save session/profile
  -> trả response y như API cũ
```

API frontend không cần đổi ngay. `ChatResponse` vẫn có:

- `session_id`;
- `reply`;
- `stage`;
- `current_slot`;
- `is_first_turn`.

Nhưng `current_slot` từ trung tâm điều khiển sẽ chuyển thành **debug/checklist pointer**, không còn là người quyết định toàn bộ câu hỏi.

---

## 4. Những phần nên giữ

### 4.1. Giữ `app/api/chat.py`

Lý do:

- đã xử lý tạo/load session;
- đã save session/profile;
- đã gọi `compose_and_validate_reply`;
- đã trigger admin queue;
- frontend đang dựa vào contract này.

Chỉ cần đổi bên trong `handle_message()` hoặc route qua engine mới. Không cần thay API trước.

### 4.2. Giữ `DealerProfileRaw`

Lý do:

- field list đã phản ánh nghiệp vụ Linh;
- có phân tách required/optional/raw signal;
- admin/card/export đang dựa vào schema này.

Không nên xóa schema. Chỉ nên đổi cách fill schema: từ slot-by-slot sang planner extract nhiều field trong một turn.

### 4.3. Giữ `SessionState`, nhưng giảm vai trò `current_slot`

`SessionState` vẫn cần:

- `stage`;
- `history`;
- `flags`;
- `turn_count`;
- `confirmation_status`;
- `review_status`;
- `detected_dealer_type`;
- `address_form`.

Nhưng `current_slot` không nên là trục chính nữa. Nó có thể giữ để:

- tương thích admin/debug;
- biết field focus gần nhất;
- hỗ trợ fallback legacy;
- phục vụ test chuyển tiếp.

### 4.4. Giữ validators và guards

Linh có các test guard/validator khá nhiều:

- `test_validators.py`;
- `test_guards.py`;
- `test_reply_pipeline.py`;
- `test_intent.py`;
- `test_state_machine.py`;
- `test_sanity.py`;
- `test_extractors.py`.

Những thứ này là tài sản. Planner LLM có thể thông minh hơn nhưng cũng dễ bịa hơn, nên càng cần validators/guards.

### 4.5. Giữ storage/admin/card

Các phần này không phải nguyên nhân chat kém:

- SQLite store;
- admin queue;
- card renderer;
- md exporter;
- scheduler.

Đập đi xây lại các phần này chỉ tốn thời gian và tăng rủi ro.

---

## 5. Những phần cần đổi vai trò

### 5.1. `_conv_asking.py`

Hiện đây là trung tâm của ASKING. Nó đang chứa quá nhiều trách nhiệm:

- intent;
- edge cases;
- extraction;
- state machine;
- ACK;
- question template;
- correction;
- slot suggestion;
- pause;
- partial retry;
- fallback.

Hướng sửa:

- Không xóa ngay.
- Giữ làm **legacy fallback**.
- Tạo engine mới chạy song song qua feature flag.
- Khi planner ổn, rút dần logic happy path ra khỏi `_conv_asking.py`.

### 5.2. `state_machine.py`

Không nên xóa. Nhưng phải đổi vai trò:

Hiện tại:

```text
state_machine quyết định hỏi gì tiếp
```

Mục tiêu:

```text
planner đề xuất hỏi gì tiếp
state_machine/coverage guard kiểm tra còn thiếu gì, có loop không, có bỏ required không
```

Nó trở thành guardrail, không phải đạo diễn.

### 5.3. `ack_generator.py`

Hiện ACK generator có instruction "không tự ask slot kế, engine sẽ append". Đây là một nguyên nhân lớn làm reply mất tự nhiên.

Hướng sửa:

- Không dùng ACK generator trong happy path planner.
- Chỉ giữ cho fallback hoặc các case nhỏ.
- Planner phải sinh một reply hoàn chỉnh: ACK + bridge + question trong cùng một mạch.

### 5.4. `slots/templates.py`

Template nên là:

- fallback khi LLM lỗi;
- hint cho planner;
- nguồn wording tham khảo;
- test fixture.

Không nên là câu hỏi chính trong happy path.

---

## 6. Module mới cần thêm

### 6.1. `app/core/intake_planner.py`

Vai trò:

- nhận session, profile, message, client;
- build context;
- gọi LLM planner;
- validate output planner;
- trả về `PlannerResult`.

Nó là điểm thay thế chính cho happy path của `_conv_asking.py`.

Interface đề xuất:

```python
def plan_intake_turn(
    session: SessionState,
    profile: DealerProfileRaw,
    message: str,
    client: LLMClient,
) -> PlannerResult:
    ...
```

### 6.2. `app/models/planner.py`

Pydantic models cho planner output.

Đề xuất:

```python
class PlannedFact(BaseModel):
    field: str
    value: Any
    evidence: str
    confidence: Literal["low", "medium", "high"]

class PlannerResult(BaseModel):
    move: Literal[
        "continue_intake",
        "answer_then_ask",
        "clarify",
        "summarize_confirm",
        "pause_sensitive",
        "close"
    ]
    facts: list[PlannedFact]
    corrections: list[PlannedFact] = []
    next_focus_fields: list[str] = []
    assistant_reply: str
    needs_human_review: bool = False
    risk_flags: list[str] = []
```

Quan trọng: planner phải trả `assistant_reply` hoàn chỉnh.

### 6.3. `app/llm/planner_prompt.py`

Prompt riêng cho planner. Không dùng prompt ACK hiện tại.

Prompt phải ép các nguyên tắc:

- Bạn là Em Linh, chuyên thu data dealer như một tư vấn marketing.
- Đọc full context trước khi quyết định.
- Không hỏi lại field đã rõ.
- Nếu user cho nhiều thông tin, extract hết.
- Nếu user hỏi "là sao", giải thích rồi hỏi lại nhẹ.
- Hỏi tối đa 1 câu chính mỗi lượt.
- Schema là checklist ngầm, không phải kịch bản cứng.
- Không bịa field; fact nào không có evidence thì không xuất.
- Reply phải tự nhiên, không được ghép kiểu ACK + template.

### 6.4. `app/core/profile_merge.py`

Tách merge profile thành module rõ ràng:

- nhận `PlannerResult.facts`;
- validate từng field;
- detect correction;
- không ghi đè field cũ nếu confidence thấp;
- nếu conflict thì hỏi xác nhận hoặc flag.

Hiện merge đang nằm rải trong `_conv_asking.py` và extractor flow. Planner cần merge sạch hơn.

### 6.5. `app/core/missing_fields.py`

Thay vì slot order điều khiển hội thoại, module này tính checklist còn thiếu:

```python
def compute_missing_fields(profile, session) -> MissingFieldState:
    ...
```

Output nên gồm:

- required còn thiếu;
- optional còn thiếu;
- fields đã đủ;
- field nên ưu tiên hỏi tiếp;
- vì sao ưu tiên.

Planner dùng thông tin này để hỏi tự nhiên.

### 6.6. `app/eval/transcripts/`

Thêm bộ transcript đánh giá cảm giác hội thoại.

Không nên chỉ unit test exact text. Cần test theo tiêu chí:

- có hỏi lại field đã rõ không;
- có nhận ra nhiều field trong một câu không;
- có hỏi đúng thứ còn thiếu không;
- có giữ tone tự nhiên không;
- có bịa không;
- có append câu hỏi template lệch mạch không.

---

## 7. Planner output nên trông như thế nào?

Ví dụ user nói:

> Anh tên Hùng, cửa hàng Nhôm Kính Hùng Phát ở Cầu Giấy, chuyên cửa nhôm Xingfa với cửa cuốn Austdoor.

Planner nên trả:

```json
{
  "move": "continue_intake",
  "facts": [
    {
      "field": "owner_name",
      "value": "Hùng",
      "evidence": "Anh tên Hùng",
      "confidence": "high"
    },
    {
      "field": "dealer_name",
      "value": "Nhôm Kính Hùng Phát",
      "evidence": "cửa hàng Nhôm Kính Hùng Phát",
      "confidence": "high"
    },
    {
      "field": "address",
      "value": "Cầu Giấy",
      "evidence": "ở Cầu Giấy",
      "confidence": "high"
    },
    {
      "field": "main_product",
      "value": "cửa nhôm Xingfa, cửa cuốn Austdoor",
      "evidence": "chuyên cửa nhôm Xingfa với cửa cuốn Austdoor",
      "confidence": "high"
    }
  ],
  "corrections": [],
  "next_focus_fields": ["phone_or_zalo"],
  "assistant_reply": "Dạ em ghi được tên anh Hùng, cửa hàng Nhôm Kính Hùng Phát ở Cầu Giấy, mạnh về cửa nhôm Xingfa và cửa cuốn Austdoor rồi ạ. Để lát nữa team liên hệ đúng người, anh cho em xin số Zalo hoặc điện thoại mình hay dùng nhất nhé?",
  "needs_human_review": false,
  "risk_flags": []
}
```

Điểm khác với Linh hiện tại: không chỉ fill slot 1.1 rồi hỏi địa chỉ nữa. Nó extract hết dữ liệu user đã tự nói.

---

## 8. Migration plan chi tiết

### Phase 0: Đóng băng baseline

Mục tiêu: trước khi sửa, biết Linh hiện đang kém ở đâu.

Việc cần làm:

- Tạo 10-20 transcript mẫu từ tình huống thực tế.
- Chạy qua Linh hiện tại, lưu output.
- Chấm bằng tiêu chí behavior, không chấm exact text.

Transcript tối thiểu:

1. User trả lời nhiều field trong một câu.
2. User trả lời cực ngắn.
3. User hỏi "là sao?".
4. User sửa thông tin cũ.
5. User nói ngoài thứ tự.
6. User từ chối optional.
7. User nghi ngờ spam/lừa đảo.
8. User tâm sự nhưng có dữ liệu nằm trong câu.
9. User dùng không dấu/viết tắt.
10. User trả lời bằng một danh sách sản phẩm dài.

Tiêu chí:

- không hỏi lại field đã rõ;
- không bỏ sót field rõ ràng;
- không hỏi quá 1 câu chính;
- reply có mạch tự nhiên;
- không bịa;
- vẫn đủ required trước confirm.

### Phase 1: Thêm planner song song, chưa thay legacy

Thêm module:

- `app/models/planner.py`;
- `app/llm/planner_prompt.py`;
- `app/core/intake_planner.py`;
- `app/core/missing_fields.py`;
- `app/core/profile_merge.py`.

Feature flag:

```text
CONVERSATION_ENGINE=legacy | planner_shadow | planner
```

Ý nghĩa:

- `legacy`: chạy như hiện tại.
- `planner_shadow`: vẫn trả lời bằng legacy, nhưng gọi planner song song và log kết quả để so.
- `planner`: dùng planner cho happy path.

Phase này chưa đụng nhiều `_conv_asking.py`.

### Phase 2: Shadow evaluation

Chạy `planner_shadow` trên transcript test:

- so facts planner extract với legacy extract;
- so next question planner với legacy question;
- kiểm tra planner có bịa không;
- kiểm tra planner có hỏi lại field đã rõ không.

Không cần đưa user thật vào ngay.

Acceptance:

- planner extract đúng nhiều field trong một câu;
- planner không hỏi lại field đã rõ;
- planner reply tự nhiên hơn legacy ở ít nhất 70-80% transcript;
- không tăng hallucination.

### Phase 3: Planner cho happy path

Chỉ route những turn bình thường qua planner:

- không abuse;
- không prompt injection;
- không rate limit;
- không session DONE;
- không admin/security override;
- không technical inquiry nguy hiểm.

Các case khó vẫn dùng legacy handler tạm thời.

Flow:

```text
handle_message()
  -> global guards hiện có
  -> nếu stage ASKING và engine=planner
       -> plan_intake_turn()
       -> merge facts
       -> update checklist/current_focus
       -> append reply
     else
       -> legacy handle_asking()
```

### Phase 4: State machine thành coverage guard

Tách phần "required còn thiếu" khỏi phần "hỏi slot kế".

State guard nên trả:

```json
{
  "required_missing": ["phone_or_zalo", "business_model_signal"],
  "can_confirm": false,
  "must_ask_before_confirm": "phone_or_zalo",
  "warnings": []
}
```

Planner dùng guard này làm input. Nhưng reply vẫn do planner viết.

### Phase 5: Bỏ ACK + template trong happy path

Khi planner ổn:

- không gọi `gen_ack_safe()` trong happy path;
- không append `get_slot_question_for_attempt()` sau planner reply;
- templates chỉ còn fallback khi planner LLM fail.

Đây là bước quan trọng nhất để Linh hết cảm giác form.

### Phase 6: Thu nhỏ `_conv_asking.py`

Sau khi planner chạy ổn:

- giữ các handler bảo mật/abuse/technical;
- giữ correction logic nào thật sự cần deterministic;
- bỏ dần các patch chỉ để chống slot-first bị cứng;
- chuyển helper còn giá trị sang module nhỏ.

Mục tiêu cuối:

```text
_conv_asking.py không còn là não chính.
Nó chỉ là router/compat layer hoặc bị thay bằng planner_engine.py.
```

---

## 9. Những thứ tuyệt đối không nên làm

### 9.1. Không chỉ viết prompt dài hơn cho ACK generator

Sai vì ACK generator vẫn bị cấm hỏi slot kế. Dù prompt hay hơn, reply cuối vẫn bị ghép với template.

### 9.2. Không thêm nhiều regex để Linh "thông minh hơn"

Regex chỉ vá case đã thấy. Càng vá, `_conv_asking.py` càng phình và càng khó hiểu. Vấn đề chính là planner thiếu quyền điều phối, không phải thiếu thêm 20 pattern.

### 9.3. Không để planner chỉ chọn `next_slot`

Nếu planner chỉ trả `next_slot`, còn câu hỏi vẫn do template sinh, bệnh vẫn còn.

Planner phải trả **assistant_reply hoàn chỉnh**.

### 9.4. Không bỏ validators/guards vì tin LLM

Quỳnh tự nhiên hơn nhưng kém chắc hơn. Linh nên học Quỳnh ở tầng hội thoại, không học sự thiếu guard.

LLM planner cần bị kiểm soát bởi:

- field validators;
- hallucination guard;
- vocab guard;
- PII guard;
- required coverage guard;
- transcript eval.

### 9.5. Không đổi API/frontend sớm

Nếu đổi cả UI/API trong lúc đổi engine, bug sẽ khó truy. Giữ `/api/chat` như cũ cho tới khi planner ổn.

---

## 10. Acceptance criteria cho hướng fix

Một bản Linh đã quay đúng hướng phải đạt:

### 10.1. Về cảm giác chat

- Không còn cảm giác mỗi lượt là một câu hỏi form.
- Không ghép ACK rời rạc với câu hỏi template lệch mạch.
- Biết dùng thông tin user vừa nói để hỏi tiếp.
- Biết giải thích lý do hỏi dữ liệu nhạy cảm.
- Không hỏi lại thông tin đã rõ.
- Nếu user trả lời nhiều ý, bot ghi nhận nhiều ý.

### 10.2. Về dữ liệu

- Required fields vẫn đủ trước confirming.
- Optional không làm bot bị dài dòng.
- Correction không ghi đè bừa.
- Field nào planner extract phải có evidence từ user text/history.

### 10.3. Về kỹ thuật

- API response không đổi.
- Storage/admin/card vẫn chạy.
- Existing unit tests không vỡ hàng loạt.
- Thêm transcript tests cho planner.
- Có feature flag rollback về legacy.

---

## 11. Lộ trình thực tế nên làm trước

Nếu bắt tay vào code, thứ tự nên là:

1. Thêm transcript eval trước để có thước đo.
2. Thêm `PlannerResult` model.
3. Viết `planner_prompt` cho full-turn reply.
4. Viết `missing_fields` để biến slot schema thành checklist.
5. Viết `profile_merge` dùng validators cũ.
6. Chạy `planner_shadow`, chưa trả lời user bằng planner.
7. So 10-20 transcript với legacy.
8. Bật planner cho happy path.
9. Bỏ ACK+template append trong happy path.
10. Rút gọn `_conv_asking.py` sau khi có bằng chứng.

Không nên bắt đầu bằng việc sửa `_conv_asking.py` trực tiếp. File đó đang là hậu quả của kiến trúc cũ. Sửa nó trước sẽ dễ thành vá tiếp.

---

## 12. Kết luận

Bạn nghi ngờ là đúng: Linh đang chệch hướng khá nhiều ở tầng chat. Nhưng chệch hướng không đồng nghĩa phải xóa hết.

Phần đáng bỏ không phải toàn bộ dự án. Phần đáng bỏ là giả định:

> hội thoại = đi qua 17 slot theo state machine, LLM chỉ extract/ACK.

Phần đáng giữ là:

> schema, validators, storage, admin, tests, guards, API contract.

Hướng sửa đúng là:

> biến Linh từ **slot machine có LLM phụ trợ** thành **LLM conversation planner có schema/guard kiểm soát**.

Đây là thay đổi lớn về kiến trúc hội thoại, nhưng không phải đập đi xây lại toàn bộ sản phẩm.

