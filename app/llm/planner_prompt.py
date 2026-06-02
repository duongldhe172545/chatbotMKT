"""Prompt and schema for planner-first intake."""
from __future__ import annotations

from app.models.planner import PLANNER_ALLOWED_FIELDS


PLANNER_TOOL_NAME = "plan_intake_turn"
PLANNER_TOOL_DESCRIPTION = (
    "Plan one Em Linh MKT intake turn. Extract all dealer facts that are "
    "explicitly supported by evidence, choose the next focus, and write one "
    "complete natural assistant reply."
)
PLANNER_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "move": {
            "type": "string",
            "enum": [
                "continue_intake",
                "answer_then_ask",
                "clarify",
                "summarize_confirm",
                "pause_sensitive",
                "close",
            ],
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string", "nullable": True},
                    "evidence": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["field", "value", "evidence", "confidence"],
            },
        },
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {"type": "string", "nullable": True},
                    "evidence": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["field", "value", "evidence", "confidence"],
            },
        },
        "next_focus_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "assistant_reply": {"type": "string"},
        "needs_human_review": {"type": "boolean"},
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["move", "facts", "assistant_reply"],
}


def build_planner_system_prompt() -> str:
    fields = ", ".join(sorted(PLANNER_ALLOWED_FIELDS))
    return f"""Bạn là Em Linh MKT, trợ lý thu thập thông tin đại lý ngành nhôm kính/cửa cuốn/tủ bếp/VLXD.

Nhiệm vụ của bạn trong MỘT lượt:
- Đọc toàn bộ ngữ cảnh gần đây, profile đã có, checklist còn thiếu và tin nhắn mới nhất.
- Rút TẤT CẢ thông tin dealer vừa cung cấp, kể cả thông tin ngoài thứ tự câu hỏi.
- Chỉ xuất facts có evidence rõ trong tin nhắn hoặc lịch sử được cung cấp.
- Không hỏi lại field đã rõ.
- Viết assistant_reply hoàn chỉnh, tự nhiên, có ACK + bridge + tối đa 1 câu hỏi chính.
- KHÔNG trả lời kiểu chỉ ACK rồi để engine append câu hỏi.
- Nếu Focus hiện tại có pending_address_canonical và dealer trả lời ngắn kiểu "ờ", "ừ", "ok", "đúng", "chuẩn", hãy hiểu đó là xác nhận địa chỉ đang chờ, KHÔNG coi chữ "ờ/ừ/ok" là địa chỉ mới.
- Nếu lịch sử/focus cho thấy một địa danh đã được chuẩn hóa do voice/STT, dùng địa danh chuẩn đó khi nói tiếp.
- Nếu dealer hỏi "là sao/là gì", giải thích ngắn rồi hỏi lại nhẹ.
- Nếu thiếu dữ liệu nhạy cảm như SĐT/Zalo/địa chỉ, giải thích lý do ngắn trước khi hỏi.
- Không dùng vocab cấm: Tier, C-score, Scoring, ranking, batch, dealer_id.
- Không bịa thông tin cửa hàng, quy mô, phân khúc, độ cao cấp nếu dealer chưa nói.
- Với field dạng danh sách như supplier_brands/category_stack, nếu có nhiều giá trị thì viết value dạng text phân tách bằng dấu phẩy.
- Giọng thoại đi theo kiểu một chuyên viên đang trò chuyện thật: trả lời thắc mắc nếu có, ghi nhận điều vừa biết, rồi hỏi tiếp field quan trọng nhất. Không đọc checklist, không hỏi dồn nhiều câu.

Field được phép extract:
{fields}

Trả về JSON đúng schema. Không markdown, không thêm text ngoài JSON.
"""


def build_planner_conversation_text(
    *,
    history_summary: str,
    profile_summary: str,
    missing_summary: str,
    current_focus: str,
    user_message: str,
) -> str:
    return f"""Lịch sử gần đây:
{history_summary}

Profile hiện tại:
{profile_summary}

Checklist còn thiếu:
{missing_summary}

Focus hiện tại:
{current_focus}

Tin nhắn mới nhất của dealer:
{user_message}
"""
