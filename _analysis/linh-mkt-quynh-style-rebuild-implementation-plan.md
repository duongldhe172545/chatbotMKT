# Linh MKT Quynh-Style Rebuild Implementation Plan

## Mục tiêu

- Giữ `llm_first` làm engine ASKING mặc định và giữ `legacy` để rollback.
- Dùng coverage theo field làm checklist ngầm, không đọc slot như một biểu mẫu cứng.
- Hiểu đúng câu trả lời ngắn theo field bot vừa hỏi, không hỏi lặp hoặc gán nhầm sang field cũ.
- Tạo 3 logo cho job mới và bảo đảm pytest mặc định không gọi API trả phí.

## Chat intake

- Session lưu cả `current_slot` và `current_focus_field`; field là ngữ cảnh chính xác của câu hỏi gần nhất.
- Fact extractor đọc lịch sử, profile, slot và field focus; field focus có ưu tiên cao nhất với câu trả lời ngắn như `có em`, `không có em`, `anh không`.
- `resolved_optional_fields` là nguồn sự thật cho optional field; `resolved_optional_slots` chỉ giữ để tương thích flow cũ.
- Câu phủ định dữ liệu được lưu cho đúng field, không bị coi là từ chối:
  - Không có nguồn dự phòng → `supplier_negotiation_signal`.
  - Không dùng Facebook → `facebook`, đồng thời `fb_marketing_status=not_applicable`.
  - Không có mạng lưới → `community_network_signal`.
- Slot kênh liên hệ chỉ cần `primary_contact_channel`. Chỉ lưu `zalo` khi dealer tự cung cấp số khác hoặc nói rõ dùng cùng số chính.
- `recommended_focus` và `can_summarize` vẫn là guard bắt buộc; chưa đủ coverage thì không render card.

## Chất lượng reply

- LLM viết toàn bộ reply intake bình thường, kết nối với thông tin dealer vừa cung cấp và chỉ hỏi một câu hỏi chính.
- Lý do hỏi chỉ xuất hiện khi hữu ích theo chủ đề, không ép ở mọi lượt và không ép độ dài câu.
- Validator hẹp kiểm tra đúng focus, không có nhiều câu hỏi, không hỏi lại field đã có/đã resolve và không dùng lời khen suy diễn.
- Khi reply vi phạm cấu trúc hoặc provider lỗi, dùng fallback deterministic; không gọi thêm một lượt LLM để sửa.

## Logo và chi phí

- Job mới tạo 3 layout: `monogram-frame`, `wordmark-block`, `premium-mark`.
- Cả 3 layout dùng `logo_style` dealer chọn làm phong cách chính.
- Progress mới là `0/3 -> 3/3`; manifest 5 logo cũ vẫn đọc được và không bị rewrite.
- `LOGO_GENERATION_MODE=local` là mặc định. `hybrid` là opt-in có thể phát sinh chi phí.
- Pytest mặc định ép local mode, tắt scheduler và fail nếu chạm Gemini hoặc Imagen thật.
- Test trả phí chỉ chạy khi có marker `live_api` và `RUN_LIVE_API_TESTS=1`.
- Số call dự kiến: mocked/full pytest mặc định `0`; một turn ASKING `llm_first`
  live thường có `2` Gemini call; một logo job `hybrid` live mới có tối đa `3`
  Imagen call.

## Kiểm tra hoàn thành

- Transcript nguồn dự phòng và Facebook/Zalo không còn hỏi lặp.
- Dealer nói dùng Zalo để tư vấn không bị hỏi thêm số Zalo.
- Summary vẫn bị chặn khi thiếu coverage.
- Job mới trả đúng 3 logo; manifest 5 logo cũ vẫn đọc được.
- Unit/integration/e2e mặc định có 0 paid API calls.

## Rollback và dữ liệu cũ

- Rollback runtime nhanh bằng `CONVERSATION_ENGINE=legacy`.
- Cột `current_focus_field` migration additive, session cũ có thể giữ `NULL` đến lượt tiếp theo.
- Không bulk rewrite profile hoặc manifest logo cũ; session lỗi cụ thể được reset hoặc sửa thủ công khi cần.
