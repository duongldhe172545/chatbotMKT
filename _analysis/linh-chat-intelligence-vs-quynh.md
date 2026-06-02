# Phân tích sâu: vì sao chat Linh MKT kém Quỳnh MKT

Ngày phân tích: 2026-05-29

Phạm vi file này chỉ xét **năng lực chat thu thập thông tin**. Không lấy việc Quỳnh đã có luồng gen ảnh, Linh có voice, hay Linh có xuất file markdown làm lý do chính. Ở tầng chat, hai con có cùng bản chất: nói chuyện với đại lý để lấy đủ dữ liệu đầu vào.

Kết luận ngắn: **Quỳnh MKT để LLM làm bộ não hội thoại. Linh MKT để state machine/slot/template làm bộ não hội thoại, còn LLM bị chia nhỏ thành extractor, ack generator và vài handler phụ.** Vì vậy Linh có thể nhiều luật hơn, nhiều test hơn, nhiều guard hơn, nhưng lại dễ kém thông minh hơn ngay trong đoạn hỏi đáp.

---

## 1. Khác biệt cốt lõi không nằm ở downstream

Nhìn từ sản phẩm, Quỳnh và Linh có thể khác nhau:

- Quỳnh thu thông tin rồi finalize để tạo logo/asset.
- Linh thu thông tin rồi chốt profile/brandkit, có voice, có admin queue, có thể xuất markdown.

Nhưng đó không giải thích được chuyện người dùng cảm thấy Linh "đần" hơn trong chat. Lý do thật nằm ở **ai đang quyết định lượt hội thoại tiếp theo**:

- Quỳnh: LLM đọc lịch sử, tự viết câu trả lời tiếp theo, tự nối ý, tự hỏi theo mạch.
- Linh: code xác định `current_slot`, detect intent, extract field, gọi `decide_action`, rồi ghép ACK với câu hỏi template của slot kế.

Nói cách khác:

- Quỳnh = **LLM-first, schema-after**.
- Linh = **schema-first, LLM-as-parser**.

---

## 2. Quỳnh MKT: một bộ não hội thoại liền mạch

### 2.1. Một prompt lớn ôm toàn bộ vai trò, nghiệp vụ và cách hỏi

Trong Quỳnh, file `Conversation_service/app/core/llm.py` tạo một `ChatGoogleGenerativeAI`, một `ConversationBufferMemory`, một prompt chính và một `LLMChain`.

Dẫn chứng:

- `be-release-v17.11.25/be-release-v17.11.25/Conversation_service/app/core/llm.py:9-14`
- `be-release-v17.11.25/be-release-v17.11.25/Conversation_service/app/core/llm.py:19-88`
- `be-release-v17.11.25/be-release-v17.11.25/Conversation_service/app/core/llm.py:98-99`

Prompt của Quỳnh không chỉ nói "hãy hỏi thông tin". Nó mô tả:

- nhân vật Quỳnh là chuyên gia marketing;
- cách xưng hô;
- nguyên tắc không dùng từ học thuật;
- hỏi từng câu một;
- luôn giải thích lý do trước khi hỏi;
- dùng ví dụ để khách dễ hiểu;
- tránh cảm giác thẩm vấn;
- cấu trúc thông tin cần lấy;
- xử lý khi khách chưa biết;
- tổng hợp lại khi đủ thông tin rồi hỏi xác nhận.

Điểm mạnh ở đây là prompt này trao cho LLM **quyền điều phối toàn bộ lượt nói**. Model không chỉ điền một ô dữ liệu, mà hiểu "mình đang làm tư vấn thương hiệu".

### 2.2. Mỗi session có memory riêng, LLM nhìn được mạch trò chuyện

Trong `chat_router.py`, mỗi request lấy session theo `userID`, lấy `sess_memory`, rồi tạo `LLMChain` theo session:

- `Conversation_service/app/api/v1/chat_router.py:21-31`

Trong `services/session.py`, mỗi session có `ConversationBufferMemory(memory_key="history", input_key="user_input")`:

- `Conversation_service/app/services/session.py:8-24`

Điều này làm Quỳnh có một lợi thế lớn: LLM được đọc mạch hội thoại như một cuộc nói chuyện. Nếu đại lý trả lời lệch, trả lời dài, đưa nhiều thông tin trong một câu, hoặc sửa thông tin cũ, model có khả năng tự nối lại vì nó đang nhìn toàn bộ history.

### 2.3. Extract sau hội thoại, không ép slot từ đầu

Quỳnh không bắt mỗi lượt phải fill đúng `current_slot`. Sau khi LLM thấy người dùng xác nhận, `auto_finalize()` lấy toàn bộ memory history rồi gọi `extract_info(final_summary)`:

- `Conversation_service/app/services/chatbot_service.py:100-134`
- `Conversation_service/app/services/chatbot_service.py:137-150`

`extract_info()` nhận **cả đoạn hội thoại** và xuất JSON profile:

- `Conversation_service/app/services/chatbot_service.py:11-47`

Đây là điểm rất quan trọng. Quỳnh cho phép hội thoại tự nhiên trước, sau đó mới rút dữ liệu. Nếu người dùng đưa nhiều thông tin không đúng thứ tự, vẫn có thể parse lại từ toàn bộ transcript.

### 2.4. Finalize cũng là quyết định theo ngữ cảnh

`should_finalize(conversation_history, last_user_input)` dùng LLM để quyết định người dùng có thật sự xác nhận chốt chưa:

- `Conversation_service/app/services/chatbot_service.py:100-124`

Nó không chỉ check regex "ok", "chốt". Prompt còn nói rõ chỉ finalize khi người dùng trả lời xác nhận cho phần tóm tắt, còn các câu chọn phương án "1", "2", "5" thì không tính.

Tức là ngay cả điểm kết thúc cũng là một quyết định có ngữ cảnh, không phải chỉ do một biến state cứng.

---

## 3. Linh MKT: hội thoại bị chia thành nhiều máy nhỏ

Linh có nhiều phần tốt về kỹ thuật: persistence SQLite, schema rõ, state machine, tests, guard, admin queue. Nhưng ở tầng chat tự nhiên, chính việc chia quá nhỏ làm bot mất "trí thông minh hội thoại".

### 3.1. Mục tiêu trong spec vẫn là thu data bằng hội thoại

Tài liệu Linh ghi rất rõ:

- chatbot là "máy thu data đại lý có kiểm soát";
- chatbot thu data + chốt thông tin + dẫn sang Zalo/ứng dụng nhỏ;
- không render logo/video trực tiếp trong chat;
- bot phải dùng ngữ cảnh + LLM hiểu nghĩa, không hỏi lại nếu nội dung rõ.

Dẫn chứng:

- `D:/Chatbot_dealer/EM_LINH_MKT_CORE.md:75-85`
- `D:/Chatbot_dealer/EM_LINH_MKT_CORE.md:220`

Vậy yêu cầu gốc của Linh không sai. Vấn đề là implementation hiện tại làm ngược tinh thần "LLM hiểu nghĩa" ở nhiều chỗ.

### 3.2. Linh bị trục `current_slot` kéo đi

Trong schema Linh, `SessionState` giữ `current_slot`, `slot_attempts`, `deferred_slots`, `skipped_slots`, `flags`, `history`, `turn_count`:

- `D:/Chatbot_dealer/app/models/schema.py:150-189`

Slot definitions định nghĩa thứ tự 17 slot forward-only:

- `D:/Chatbot_dealer/app/slots/definitions.py:23-32`

Spec cũng nói rõ 17 slot, 6 required, 10 optional:

- `D:/Chatbot_dealer/EM_LINH_MKT_CORE.md:471-499`

Về mặt dữ liệu, checklist này hợp lý. Nhưng khi `current_slot` trở thành trung tâm của hội thoại, bot sẽ có xu hướng hỏi theo checklist thay vì theo ý người dùng vừa nói.

### 3.3. Orchestrator xử lý quá nhiều lớp trước khi tới câu trả lời

`handle_message()` trong Linh là dispatcher theo stage, thêm nhiều bước tiền xử lý:

- timeout;
- voice fail;
- STT correction;
- address form detection;
- prompt injection guard;
- garbage detection;
- abuse detection;
- append history;
- rồi mới dispatch theo stage.

Dẫn chứng:

- `D:/Chatbot_dealer/app/core/conversation.py:61-164`

Những thứ này không sai. Nhưng chúng cho thấy hội thoại Linh đi qua một pipeline rất kỹ thuật trước khi có response. Nếu pipeline này điều khiển luôn việc hỏi câu tiếp theo, LLM chỉ còn là bộ phận phụ.

### 3.4. `handle_asking()` là nơi lộ rõ kiến trúc slot-first

Trong `_conv_asking.py`, flow chính là:

1. detect intent;
2. lấy `current_slot`;
3. xử lý hàng loạt case đặc biệt;
4. extract field theo slot hiện tại;
5. gọi state machine `decide_action`;
6. nếu advance/skip/defer thì gen ACK;
7. lấy câu hỏi slot kế bằng template;
8. ghép `ack + question`.

Dẫn chứng:

- `D:/Chatbot_dealer/app/core/_conv_asking.py:71-80`
- `D:/Chatbot_dealer/app/core/_conv_asking.py:198-217`
- `D:/Chatbot_dealer/app/core/_conv_asking.py:246-274`
- `D:/Chatbot_dealer/app/core/_conv_asking.py:276-310`

Đây là khác biệt lớn nhất với Quỳnh.

Ở Quỳnh, LLM nhận: "đây là toàn bộ cuộc nói chuyện, hãy trả lời như Quỳnh".

Ở Linh, LLM thường nhận các nhiệm vụ nhỏ hơn:

- classify intent;
- extract field cho slot hiện tại;
- generate một câu ACK;
- defensive/tâm sự handler trong một số case.

LLM không còn là người quyết định "lượt này nên nói gì cho hợp ngữ cảnh nhất".

### 3.5. Extractor của Linh nhìn hẹp hơn Quỳnh

Trong `_extract_and_merge()`, Linh chỉ gọi extractor nếu có `current_slot` và slot có schema:

- `D:/Chatbot_dealer/app/core/_conv_asking.py:858-879`

`extract_slot()` nhận `slot_id`, `user_message`, `profile_context`, rồi build task kiểu "Extract field cho slot {slot_id} từ message của dealer":

- `D:/Chatbot_dealer/app/llm/extractors/runner.py:26-62`
- `D:/Chatbot_dealer/app/llm/extractors/runner.py:77-105`

Nghĩa là extractor được tối ưu cho câu hỏi: "người dùng có trả lời đúng slot hiện tại không?"

Trong khi Quỳnh extract từ toàn bộ conversation khi finalize. Vì vậy nếu đại lý nói một câu kiểu:

> Anh tên Hùng, cửa hàng Nhôm Kính Hùng Phát ở Cầu Giấy, chuyên cửa nhôm Xingfa với cửa cuốn Austdoor, khách chủ yếu nhà dân.

Quỳnh có thể hiểu đó là một cụm thông tin thương hiệu. Linh có nguy cơ chỉ ưu tiên slot đang hỏi, rồi phần còn lại phải nhờ deterministic fixes, profile context, skip slot đã fill, hoặc các rule vá sau.

### 3.6. ACK và câu hỏi bị tách rời

`ack_generator.py` ghi rõ nhiệm vụ chỉ sinh một câu ACK ngắn và **không tự ask slot kế** vì engine sẽ append:

- `D:/Chatbot_dealer/app/llm/ack_generator.py:26-66`

Sau đó `_conv_asking.py` lấy `question = get_slot_question_for_attempt(next_slot, session)` rồi return `ack + question`:

- `D:/Chatbot_dealer/app/core/_conv_asking.py:260-274`

Đây là nguyên nhân làm Linh dễ bị cụt mạch.

Một câu trả lời tự nhiên thường cần quyết định đồng thời:

- nên công nhận thông tin nào;
- nên nối sang chủ đề nào;
- có nên hỏi tiếp ngay không;
- nên giải thích lý do hỏi như thế nào;
- có cần tóm tắt ngắn không;
- câu hỏi tiếp theo nên dựa vào câu trả lời vừa rồi hay checklist.

Linh lại tách thành: ACK do LLM, câu hỏi do template/slot. Hai nửa này đúng riêng lẻ nhưng ghép lại dễ không thành một lượt hội thoại thông minh.

### 3.7. Template nói là fallback, nhưng thực tế tham gia sâu vào response

`templates.py` nói template là câu hỏi mặc định/fallback, safety net:

- `D:/Chatbot_dealer/app/slots/templates.py:1-15`

Nhưng trong flow ASKING, câu hỏi slot kế và retry question được lấy trực tiếp từ template helper:

- `D:/Chatbot_dealer/app/core/_conv_asking.py:266-274`
- `D:/Chatbot_dealer/app/core/_conv_asking.py:291-299`
- `D:/Chatbot_dealer/app/core/reply_pipeline.py:377-382`
- `D:/Chatbot_dealer/app/core/reply_pipeline.py:489-503`

Điều này làm câu hỏi của Linh dễ trở thành "kịch bản hỏi form". Dù ACK có mềm, câu hỏi kế vẫn bị kéo về wording có sẵn và slot kế.

### 3.8. State machine đang làm vai trò người viết kịch bản

`decide_action()` quyết định `ADVANCE`, `RETRY`, `PARTIAL_RETRY`, `DEFER`, `SKIP`, `PAUSE`, đồng thời mutate `session.current_slot`:

- `D:/Chatbot_dealer/app/core/state_machine.py:45-67`

Logic retry/defer/skip cho required/optional rất chi tiết:

- `D:/Chatbot_dealer/app/core/state_machine.py:154-157`
- `D:/Chatbot_dealer/app/core/state_machine.py:314-379`

Luật này có ích để không mất dữ liệu, nhưng nếu nó là tầng quyết định câu hỏi tiếp theo thì bot sẽ ưu tiên "đi đúng state" hơn "nói đúng mạch". Quỳnh không có sự chắc chắn này, nhưng lại được tự nhiên vì một LLM call được phép quyết định toàn bộ response.

### 3.9. `_conv_asking.py` phình to vì phải vá sự cứng của kiến trúc

`_conv_asking.py` hiện chứa rất nhiều xử lý đặc biệt: technical inquiry, L2 intent fallback, dealer type detect, address blacklist, repeat complaint, flirt, confusion, mid-flow correction, slot suggestion, extract/merge, reference fill, deterministic fixes, pause, partial retry, rush mode...

Dẫn chứng ngay đầu flow:

- `D:/Chatbot_dealer/app/core/_conv_asking.py:81-196`

Đoạn correction còn phải có pattern riêng:

- `D:/Chatbot_dealer/app/core/_conv_asking.py:316-330`

Đây là dấu hiệu kiến trúc. Khi hội thoại chính quá cứng, các tình huống người dùng nói tự nhiên sẽ liên tục phát sinh "case cần vá".

---

## 4. Vì sao người dùng cảm thấy Linh kém thông minh hơn

### 4.1. Linh hiểu theo "ô đang cần điền", không hiểu theo "ý người dùng đang muốn nói"

Quỳnh đọc lịch sử để tiếp tục tư vấn. Linh trước hết hỏi: current slot là gì, message này fill được field nào của slot đó không.

Hệ quả:

- Người dùng trả lời dư thông tin: Linh dễ chỉ lấy một phần.
- Người dùng nói vòng vo: Linh dễ rơi vào retry hoặc fallback.
- Người dùng trả lời ngoài thứ tự: Linh phải nhờ rule skip/merge/vá.
- Người dùng muốn được giải thích: Linh có handler, nhưng sau đó vẫn quay lại current slot.

### 4.2. Linh ghép câu trả lời từ nhiều bộ phận nên mất nhịp

Một lượt nói của Quỳnh là một output thống nhất của LLM.

Một lượt nói của Linh có thể là:

- intent regex hoặc L2 intent;
- extractor JSON;
- state machine action;
- ACK từ LLM;
- question template;
- reply pipeline sửa lại nếu thiếu ACK, quá nhiều câu hỏi, hoặc rủi ro.

Ghép đúng về mặt kỹ thuật không đồng nghĩa với nghe thông minh.

### 4.3. Prompt Linh không được dùng để điều phối full response

`system_prompt.py` của Linh có role/persona/tone/context/task, nhưng khi gọi ACK, task lại là "Gen 1 câu ACK ngắn":

- `D:/Chatbot_dealer/app/llm/system_prompt.py:17-54`
- `D:/Chatbot_dealer/app/llm/system_prompt.py:169-205`
- `D:/Chatbot_dealer/app/llm/ack_generator.py:85-107`

Tức là prompt có vẻ giàu, nhưng quyền của LLM trong call đó rất hẹp. Nó không được phép tự hỏi slot kế. Engine append câu hỏi sau.

Quỳnh thì ngược lại: prompt chính là kịch bản nghiệp vụ + phong cách + nguyên tắc hỏi, và LLM được phép viết cả lượt trả lời.

### 4.4. Spec Linh muốn linh hoạt, implementation lại forward-only

Spec Linh nói:

- nếu đại lý cho data đa-field cùng lúc thì ack + smart skip;
- nếu rẽ tâm sự/defensive thì engage trước, tạm dừng câu hỏi current;
- không advance cứng 1 turn/1 lượt khi chưa có data.

Dẫn chứng:

- `D:/Chatbot_dealer/EM_LINH_MKT_CORE.md:418-426`

Nhưng cùng spec cũng định nghĩa flow chọn slot tiếp bằng cách sort theo priority order và lấy slot đầu tiên:

- `D:/Chatbot_dealer/EM_LINH_MKT_CORE.md:550-565`

Hai mục tiêu này căng nhau. Muốn tự nhiên thì cần planner nhìn toàn cảnh. Muốn deterministic thì dùng slot priority. Implementation hiện tại nghiêng nhiều về deterministic nên cảm giác chat thua Quỳnh.

---

## 5. Bảng so sánh ngắn

| Trục so sánh | Quỳnh MKT | Linh MKT | Ảnh hưởng tới cảm giác chat |
|---|---|---|---|
| Bộ não lượt nói | LLM chính viết toàn bộ reply | Code/state machine quyết định, LLM phụ từng mảnh | Quỳnh tự nhiên hơn |
| Ngữ cảnh | Full conversation memory | `current_slot` + message hiện tại + profile context nhỏ | Linh dễ hẹp ý |
| Cách thu dữ liệu | Nói chuyện trước, extract sau từ transcript | Extract từng slot trong từng turn | Linh giống form |
| Câu hỏi tiếp theo | LLM tự nối theo mạch | Template slot kế | Linh dễ cụt nhịp |
| Finalize | LLM đọc history để chốt | Stage/state/checklist | Quỳnh mềm hơn |
| Guard | Ít guard hơn | Nhiều guard/regex/edge case | Linh chắc hơn nhưng nặng hơn |
| Rủi ro chính | Có thể thiếu chắc chắn, khó kiểm chứng | Cứng, nhiều vá, mất tự nhiên | Cần dung hòa |

---

## 6. Nhận định kiến trúc

Linh không "lỏ" vì thiếu code. Linh kém thông minh ở chat vì **có quá nhiều code chen vào vị trí đáng lẽ là của bộ não hội thoại**.

Quỳnh có thể không chuẩn kỹ thuật bằng Linh ở persistence/test/guard, nhưng tại đoạn chat, Quỳnh có một lợi thế rất thực dụng: user nói gì thì LLM được quyền hiểu toàn cuộc trò chuyện rồi trả lời như một người tư vấn.

Linh đang cố biến hội thoại thành một state machine có LLM hỗ trợ. Điều này hợp với form, không hợp với cảm giác "em MKT thông minh".

---

## 7. Hướng sửa Linh để bắt kịp Quỳnh ở bước chat

Không nên vứt hết slot/schema của Linh. Phần đó vẫn có giá trị để đảm bảo đủ dữ liệu. Nhưng cần đổi vai trò của nó.

### 7.1. Thêm tầng `intake_planner`

Tạo một planner LLM ở tầng trước state machine, nhận:

- full recent history;
- profile hiện tại;
- danh sách field còn thiếu;
- field nào required/optional;
- user message mới nhất;
- stage hiện tại.

Planner trả về một object kiểu:

```json
{
  "understood_user_intent": "dealer provided name, shop name, address and product",
  "new_facts": {
    "owner_name": "Hùng",
    "dealer_name": "Nhôm Kính Hùng Phát",
    "address": "Cầu Giấy",
    "main_product": "cửa nhôm Xingfa, cửa cuốn Austdoor"
  },
  "next_missing_priority": ["phone_or_zalo", "business_model_signal"],
  "reply_strategy": "ack_and_ask_one",
  "assistant_reply": "Dạ em ghi được tên cửa hàng, khu vực Cầu Giấy và mảng sản phẩm chính rồi anh. Để lát nữa team liên hệ đúng người, anh cho em xin số Zalo hay số điện thoại mình hay dùng nhất nhé?"
}
```

Điểm quan trọng: planner được quyền viết **cả reply**, không chỉ ACK.

### 7.2. State machine chuyển thành guardrail

State machine vẫn giữ vai trò:

- không bỏ sót required field;
- tránh loop;
- đánh dấu required missing;
- kiểm soát retry tối đa;
- không cho LLM bịa field chưa có;
- validate output planner.

Nhưng state machine không nên là người viết kịch bản hỏi. Nó chỉ nên kiểm tra: planner hỏi như vậy có hợp lệ không, còn thiếu field nào, có vi phạm guard không.

### 7.3. Slot trở thành checklist ngầm

Slot order vẫn dùng để ưu tiên khi thiếu dữ liệu, nhưng không dùng như thứ tự câu hỏi cứng.

Ví dụ:

- Nếu người dùng tự nói tên, địa chỉ, sản phẩm trong cùng một câu, planner ghi nhận cả 3 và hỏi phone hoặc mô hình kinh doanh.
- Nếu người dùng nói về khách hàng mục tiêu trước khi tới slot đó, planner vẫn ghi nhận, không bắt họ chờ tới đúng slot.
- Nếu người dùng hỏi "là sao?", planner giải thích ngắn rồi hỏi lại theo cách dễ hiểu hơn, không append template máy móc.

### 7.4. Extract nên chuyển từ slot-only sang turn/history-aware

Hiện `extract_slot()` đang xoay quanh `slot_id`. Nên bổ sung extractor cấp cao hơn:

- input: message mới + history gần + profile hiện tại;
- output: mọi field có thể extract được;
- validator vẫn kiểm soát từng field;
- nếu conflict với profile cũ thì đánh dấu correction/needs_confirm.

Slot extractor hiện tại có thể giữ làm fallback hoặc validator hẹp, nhưng không nên là đường duy nhất.

### 7.5. Gộp ACK + bridge + question

Không nên để LLM gen ACK rồi engine append câu hỏi template. Nên để planner sinh một reply hoàn chỉnh theo constraint:

- tối đa 1 câu hỏi chính;
- phải acknowledge thông tin mới;
- nếu hỏi dữ liệu nhạy cảm thì giải thích lý do ngắn;
- không dùng vocab cấm;
- không hỏi lại field đã rõ;
- nếu chưa rõ thì hỏi lại bằng ví dụ.

Đây chính là điều Quỳnh đang làm tốt nhờ prompt chính.

---

## 8. Cách kiểm chứng sau khi sửa

Nên tạo bộ transcript test so trực tiếp Linh vs Quỳnh, không chỉ unit test state machine.

Các case cần có:

1. Đại lý trả lời nhiều field trong một câu.
2. Đại lý trả lời ngắn: "Hùng, Hùng Phát, Cầu Giấy".
3. Đại lý hỏi "là sao?" trước câu hỏi nhạy cảm.
4. Đại lý sửa thông tin cũ: "không phải Cầu Giấy, là Nam Từ Liêm".
5. Đại lý nói ngoài thứ tự: kể khách hàng/sản phẩm trước khi cho số điện thoại.
6. Đại lý nói không biết ở optional field.
7. Đại lý nghi ngờ spam/lừa đảo.
8. Đại lý tâm sự lan man nhưng vẫn có dữ liệu nằm trong câu.

Acceptance không chỉ là "đủ field", mà là:

- không hỏi lại thông tin đã rõ;
- hỏi tiếp đúng thứ còn thiếu;
- câu trả lời nghe như một người tư vấn, không như form;
- không append câu hỏi template lệch mạch;
- vẫn lưu đủ required fields;
- không bịa dữ liệu.

---

## 9. Kết luận

Linh hiện tại không thua Quỳnh vì thiếu gen ảnh. Linh thua ở chat vì đang dùng kiến trúc **form engine có LLM phụ trợ**, trong khi Quỳnh dùng kiến trúc **LLM conversation agent có extract hậu kỳ**.

Muốn Linh thông minh như Quỳnh nhưng vẫn giữ độ chắc của schema/test, hướng đúng là:

1. cho LLM planner điều phối lượt nói;
2. giữ slot/schema làm checklist và validator;
3. extract theo turn/history thay vì chỉ theo `current_slot`;
4. bỏ kiểu ACK riêng + template question riêng trong happy path;
5. dùng transcript evaluation để đo cảm giác hội thoại, không chỉ đo unit test.

