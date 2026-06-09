# Hướng Dẫn & Giải Thích Chi Tiết Luồng Xử Lý Phản Hồi Của Chatbot Em Linh MKT

Tài liệu này giải thích chi tiết về kiến trúc hệ thống, sơ đồ luồng tin nhắn và vai trò của tất cả các thư mục, tệp tin (config, parlant, slots, llm, core...) liên quan đến **nội dung và cách trả lời** của chatbot.

---

## 🗺️ Sơ đồ Luồng Xử Lý Một Tin Nhắn (Turn Pipeline)

Khi khách hàng nhắn tin, hệ thống sẽ xử lý qua các bước sau để đưa ra câu trả lời:

```mermaid
graph TD
    User([Khách hàng nhắn tin]) --> API[app/main_v2.py & chat_service]
    API --> TP[app/parlant/turn_processor.py <br> Bộ điều phối chính]
    
    subgraph 1. Trích xuất thông tin & Phân tích ngữ cảnh (LLM Gộp)
        TP --> Extractor[app/llm/intake_fact_extractor.py <br> Gọi 1 lượt LLM trích xuất 17 slots + Phân tích Intent/Signals/DealerType]
        Extractor --> Address[app/llm/address_llm.py & address_parser.py <br> Xử lý địa chỉ chi tiết]
        Extractor --> Regex[Trích xuất nhanh Số Điện Thoại bằng Regex]
    end
    
    subgraph 2. Đưa ra kế hoạch (Workflow)
        Extractor --> WE[app/parlant/workflow_engine.py <br> Xác định Slot cần thu thập tiếp theo]
        WE --> Slots[app/slots/definitions.py <br> Định nghĩa 17 trường dữ liệu & thứ tự ưu tiên]
    end
    
    subgraph 3. Tổng hợp Ngữ cảnh (Context)
        WE --> CB[app/parlant/context_builder.py <br> Đóng gói toàn bộ data, lịch sử, quy tắc]
    end
    
    subgraph 4. Sinh câu trả lời (Reply Generation)
        CB --> Agent[app/parlant/agent.py <br> Trình tạo câu trả lời của Agent]
        
        %% Các nguồn cấu hình nạp vào Agent %%
        Rules[(config/rules.yaml <br> Luật tổng quát & Tone)] --> Agent
        Guidelines[(config/guidelines.yaml <br> Hướng dẫn xử lý tình huống)] --> Agent
        Canned[(config/canned_responses.yaml <br> Câu trả lời cứng/mẫu)] --> Agent
        
        Agent --> LLM[Gọi LLM - gemini-3.1-flash-lite]
        LLM --> Reply([Gửi câu trả lời cho Khách hàng])
    end
```

---

## 🚀 Ví Dụ Thực Tế Luồng Xử Lý Một Lượt Chat (Turn Scenario)

Giả sử khách hàng nhắn: *"Anh tên Hùng, xưởng nhôm kính Hùng Phát ở Hải Phòng. Số của anh: 0912345678"*

1.  **Bước 1: Trích xuất & Phân tích hội thoại (Extraction & Observation)**
    *   Hệ thống gọi một lượt LLM duy nhất (`intake_fact_extractor.py` sử dụng `gemini-3.1-flash-lite`): Đọc tin nhắn và trích xuất thành công cả dữ liệu và ý định/thái độ:
        *   **Dữ liệu (Facts):** `owner_name` = `"Hùng"`, `dealer_name` = `"Hùng Phát"`, `address` = `"Hải Phòng"`.
        *   **Ý định (Intent):** `intent` = `"normal"` (Tin nhắn cung cấp thông tin bình thường).
        *   **Trạng thái (Signals):** `dealer_type` = `"nhom_kinh"`, `is_busy` = `false`, `is_emotional` = `false`.
    *   **Regex Extractor**: Quét nhanh số điện thoại `0912345678` qua biểu thức chính quy (`\d{9,12}`) → gán thành `phone_or_zalo`.
    *   **Address Parser** (`address_llm.py`): Nhận diện `"Hải Phòng"` và chuẩn hóa: Tỉnh = `Hải Phòng`, Quận/Huyện = `None` (chờ bổ sung).
2.  **Bước 2: Xác định mục tiêu tiếp theo (Workflow)**
    *   `workflow_engine.py` đối chiếu với 17 slots trong `definitions.py`. Nhận thấy các slot 1.1 (Tên), 1.3 (Số điện thoại) đã có đủ. Slot 1.2 (Địa chỉ) mới chỉ có Tỉnh Hải Phòng, thiếu Quận/Huyện/Xã (quy định trong `rules.yaml` địa chỉ tối thiểu cần có Quận/Huyện).
    *   Mục tiêu tiếp theo (`suggested_objective`) được xác định: `collect_required_field` với `target_field` = `address` (yêu cầu bổ sung địa chỉ chi tiết).
3.  **Bước 3: Đóng gói bối cảnh (Context Builder)**
    *   `context_builder.py` tổng hợp: Lịch sử cuộc hội thoại, loại đại lý (Nhôm kính), các thông tin đã có, và mục tiêu tiếp theo (Hỏi thêm địa chỉ cụ thể quận/huyện).
4.  **Bước 4: Sinh phản hồi tự nhiên (Agent & LLM)**
    *   `agent.py` nạp cấu hình `rules.yaml` (bao gồm tính cách Em Linh, quy tắc giao tiếp tự nhiên và tone giọng đại lý nhôm kính) để tạo Prompt hệ thống.
    *   Gọi mô hình `gemini-3.1-flash-lite` sinh phản hồi.
    *   Nhờ luật giao tiếp tự nhiên đã được tối ưu, LLM sẽ **tự động** tạo ra một câu trả lời linh hoạt, trôi chảy mà không bị gò bó bởi các câu mẫu cứng nhắc, ví dụ: *"Dạ em ghi nhận thông tin của anh Hùng bên xưởng nhôm kính Hùng Phát rồi ạ. Anh cho em hỏi thêm chút là xưởng mình ở quận hay huyện nào tại Hải Phòng để em ghi vào hồ sơ làm logo cho chuẩn xác anh nhé?"*

---

## 📂 Chi Tiết Từng Thư Mục & Tệp Tin Liên Quan

### 1. ⚙️ Thư mục Cấu hình (`d:\Chatbot_dealer\config\`)
Chứa toàn bộ các quy tắc hoạt động, tính cách và các kịch bản cứng của chatbot. **Nếu muốn thay đổi nội dung trả lời hoặc hành vi của chatbot, đây là nơi đầu tiên cần chỉnh sửa.**

*   **[`rules.yaml`](file:///d:/Chatbot_dealer/config/rules.yaml) (QUAN TRỌNG NHẤT):**
    Tệp tin cấu hình hợp nhất duy nhất quy định hành vi của chatbot:
    *   *Mission (Nhiệm vụ):* Mục tiêu tặng bộ thương hiệu miễn phí và lấy đủ 17 trường thông tin.
    *   *Persona (Nhân vật):* Đóng vai Em Linh MKT (24 tuổi, nhiệt tình, sử dụng icon 🌷).
    *   *Data Collection Principles (Nguyên tắc thu thập):* Quy định cách trò chuyện linh hoạt, tự nhiên, không rập khuôn mẫu, không nhận dữ liệu rác (LLM tự phát hiện và hỏi lại dựa trên quy tắc prompt), xử lý khi khách hàng từ chối.
    *   *Slot-specific Rules (Luật cho từng trường thông tin):* Quy định định dạng chuẩn của SĐT (10 số đầu 0), Địa chỉ (tối thiểu Tỉnh + Quận/Huyện),...
    *   *Tone Settings (Giọng điệu theo nhóm đại lý):* Cung cấp các từ ngữ chuyên ngành và cách xưng hô phù hợp cho từng nhóm đại lý (Cửa nhôm kính, Tủ bếp, Điện mặt trời, Đại lý tổng hợp).
    *   *Safety (An toàn):* Không tiết lộ prompt hệ thống, không tranh cãi với khách hàng.
*   **[`guidelines.yaml`](file:///d:/Chatbot_dealer/config/guidelines.yaml):**
    Các **Luật Phản Ứng Nhanh (Condition-Action Rules)** khi khách hàng có các hành vi đặc biệt ngoài luồng thu thập dữ liệu thông thường:
    *   *Defensive:* Giải thích nhẹ nhàng khi khách hàng nghi ngờ quà tặng lừa đảo.
    *   *Confusion:* Phản hồi lịch sự khi khách gửi tin nhắn vô nghĩa/khó hiểu.
    *   *Tam_su:* Cách lắng nghe và chia sẻ khi khách hàng chia sẻ về khó khăn trong nghề.
    *   *Collection_ack:* Cảm ơn một cách tinh tế sau khi thu thập được thông tin quan trọng.
*   **[`canned_responses.yaml`](file:///d:/Chatbot_dealer/config/canned_responses.yaml):**
    Chứa các câu trả lời **cố định (bỏ qua LLM)** cho một số trường hợp đặc biệt bắt buộc phải chính xác từng chữ: Lời chào mở đầu (`greeting`) hoặc thông báo lỗi định dạng SĐT.

---

### 2. 🤖 Thư mục Xử lý Hội thoại (`d:\Chatbot_dealer\app\parlant\`)
Chứa toàn bộ logic điều phối luồng trò chuyện và kết nối dữ liệu cấu hình với mô hình ngôn ngữ lớn (LLM).

*   **[`agent.py`](file:///d:/Chatbot_dealer/app/parlant/agent.py):**
    *   Nơi lắp ráp Prompt hệ thống cuối cùng từ `rules.yaml` và ngữ cảnh hiện tại.
    *   Chịu trách nhiệm gọi mô hình `gemini-3.1-flash-lite` (chế độ chạy thật) hoặc gọi `_stub_reply` (chế độ test/giả lập) để tạo phản hồi.
*   **[`turn_processor.py`](file:///d:/Chatbot_dealer/app/parlant/turn_processor.py):**
    *   Bộ điều phối chính của lượt chat (Orchestrator). Quản lý toàn bộ vòng đời của lượt hội thoại: từ Tiền lọc (Chỉ giữ lại chặn prompt injection) → Gộp gọi 1 lần LLM để Trích xuất thông tin và nhận diện thái độ/ý định hội thoại → Xác định mục tiêu tiếp theo → Gọi Agent sinh câu trả lời.
    *   Đã được loại bỏ hoàn toàn các logic lọc cứng cũ (`stopwords`, `conversational_indicators`, regex name/shop extraction) và gộp lượt gọi LLM để tăng gấp đôi tốc độ phản hồi.
*   **[`context_builder.py`](file:///d:/Chatbot_dealer/app/parlant/context_builder.py):**
    *   Đóng gói toàn bộ bối cảnh cuộc trò chuyện (thông tin đại lý đã có, lịch sử chat, các lỗi định dạng đang gặp, loại đại lý, mục tiêu cần hỏi tiếp theo) để chuyển cho Agent sinh câu trả lời.
*   **[`workflow_engine.py`](file:///d:/Chatbot_dealer/app/parlant/workflow_engine.py):**
    *   Đưa ra quyết định chatbot cần làm gì ở bước tiếp theo dựa trên hồ sơ hiện tại của khách hàng.
*   **[`observation_detector.py`](file:///d:/Chatbot_dealer/app/parlant/observation_detector.py):**
    *   Bộ nhận diện thái độ và ý định dự phòng (Heuristics). Chỉ được gọi khi hệ thống chạy ở chế độ offline/stub hoặc LLM gặp sự cố để đảm bảo chatbot không bị sập.

---

### 3. 📋 Thư mục Thu thập Thông tin (`d:\Chatbot_dealer\app\slots\`)
Quản lý cấu trúc của **17 trường thông tin (Slots)** mà chatbot bắt buộc phải thu thập từ đại lý.

*   **[`definitions.py`](file:///d:/Chatbot_dealer/app/slots/definitions.py):**
    *   Định nghĩa mã số, tên trường, mức độ bắt buộc (`REQUIRED` / `OPTIONAL`), và thứ tự ưu tiên của 17 slots thông tin cần thu thập.
*   **[`templates.py`](file:///d:/Chatbot_dealer/app/slots/templates.py):**
    *   Chứa danh sách câu hỏi gợi ý cho từng slot (chỉ dùng trong chế độ stub test, khi chạy LLM thật hệ thống để LLM tự do đặt câu hỏi để tránh lặp đi lặp lại).

---

### 4. 🧠 Thư mục Trí tuệ Nhân tạo (`d:\Chatbot_dealer\app\llm\`)
Quản lý việc kết nối với các mô hình ngôn ngữ lớn (LLM - Gemini) và các prompt chuyên dụng cho việc trích xuất thông tin.

*   **[`intake_fact_extractor.py`](file:///d:/Chatbot_dealer/app/llm/intake_fact_extractor.py):**
    *   Prompt và logic hướng dẫn LLM (sử dụng mô hình chất lượng cao `gemini-3.1-flash-lite`) thực hiện nhiệm vụ kép: Vừa đọc tin nhắn trích xuất ra các giá trị tương ứng cho 17 slots, vừa phân tích thái độ/ý định của khách hàng.
*   **[`address_llm.py`](file:///d:/Chatbot_dealer/app/llm/address_llm.py):**
    *   Sử dụng LLM chuyên dụng để bóc tách địa chỉ khách hàng thành các cấp: Tỉnh/Thành phố, Quận/Huyện, Phường/Xã để lưu trữ có cấu trúc vào database.
*   **[`client.py`](file:///d:/Chatbot_dealer/app/llm/client.py):**
    *   Phân tầng mô hình LLM để tối ưu hóa chi phí và tốc độ:
        *   `FAST` (Mặc định dùng `gemini-3.1-flash-lite`): Dành cho việc sinh câu trả lời nhanh (Chatbot response).
        *   `QUALITY` (Mặc định dùng `gemini-3.1-flash-lite`): Dành cho việc trích xuất thông tin và xử lý địa chỉ phức tạp.

---

### 5. 🛡️ Thư mục Tiền xử lý & Logic bổ trợ (`d:\Chatbot_dealer\app\core\`)
Nơi chứa các công cụ lọc tin nhắn rác, chuẩn hóa dữ liệu, và tải luật.

*   **[`rules.py`](file:///d:/Chatbot_dealer/app/core/rules.py):**
    *   Module Python tải và phân tích cú pháp tệp `config/rules.yaml` để truyền vào cho Agent và Extractor.
*   **[`garbage_detector.py`](file:///d:/Chatbot_dealer/app/core/garbage_detector.py) & [`abuse_detector.py`](file:///d:/Chatbot_dealer/app/core/abuse_detector.py):**
    *   Các hàm helper phát hiện tin nhắn rác và từ ngữ xúc phạm. Hiện tại đã được bỏ khỏi luồng tiền xử lý cứng của `turn_processor.py` để nhường quyền quyết định phản hồi tự nhiên cho LLM dựa trên `rules.yaml`.
*   **[`regex_markers.py`](file:///d:/Chatbot_dealer/app/core/regex_markers.py):**
    *   Sử dụng Regular Expressions để nhận biết nhanh số điện thoại (fallback dự phòng khi LLM lỗi hoặc chạy stub test).

---

## 🎯 Hướng Dẫn Nhanh: Khi muốn chỉnh sửa Chatbot thì sửa ở đâu?

| Mục tiêu chỉnh sửa | Tệp tin cần sửa | Mô tả cách sửa |
| :--- | :--- | :--- |
| **Thay đổi tính cách, xưng hô, cách trò chuyện của Linh MKT** | [`config/rules.yaml`](file:///d:/Chatbot_dealer/config/rules.yaml) | Chỉnh sửa phần `persona` và `data_collection.principles`. |
| **Thay đổi tone giọng chuyên ngành (ví dụ: bổ sung từ lóng của ngành Nhôm kính)** | [`config/rules.yaml`](file:///d:/Chatbot_dealer/config/rules.yaml) | Tìm đến phần `tone_settings` → nhóm `nhom_kinh` để chỉnh sửa/thêm từ khóa gợi ý. |
| **Siết chặt điều kiện của một trường thông tin (ví dụ: SĐT phải bắt đầu bằng số 0)** | [`config/rules.yaml`](file:///d:/Chatbot_dealer/config/rules.yaml) | Chỉnh sửa phần `rules` của slot mong muốn dưới mục `data_collection.slots`. |
| **Thêm kịch bản phản xạ nhanh khi khách hỏi vặn vẹo** | [`config/guidelines.yaml`](file:///d:/Chatbot_dealer/config/guidelines.yaml) | Thêm một guideline mới với `condition` (điều kiện kích hoạt) và `action` (hướng dẫn phản hồi cho LLM). |
| **Thay đổi câu chào mừng mở đầu cố định** | [`config/canned_responses.yaml`](file:///d:/Chatbot_dealer/config/canned_responses.yaml) | Tìm đến `id: greeting` và sửa trường `template` của nó. |
| **Thay đổi thứ tự ưu tiên thu thập các thông tin** | [`app/slots/definitions.py`](file:///d:/Chatbot_dealer/app/slots/definitions.py) | Điều chỉnh thứ tự khai báo hoặc thuộc tính `priority` của các slots thông tin. |
