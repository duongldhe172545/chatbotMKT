"""Extractor — gọi LLM để bóc Dealer Profile RAW từ hội thoại."""
from __future__ import annotations

from app.llm.base import LLMProvider
from app.models.schema import ChatMessage, ChatRole, ExtractResult

from . import prompts

# Số message gần nhất gửi cho extractor. v7 flow có 16 micro-turn = 32+
# messages → 30 window cũ cut mất turn đầu. Tăng 50 để cover full v7 conv.
# Cost extra: ~+1500 tokens × $1/M (Haiku) = ~$0.0015/call, full v7 convo
# extra ~$0.05 (~1200 VND) — chấp nhận được.
HISTORY_WINDOW = 50

# Mô tả ngắn 4 nhóm opener — inject vào prompt để LLM hiểu directive cấm.
_GROUP_DESC = {
    "A": "A (acknowledge: Dạ em ghi nhận / Em note / Oke / Dạ vâng / Em rõ rồi)",
    "B": "B (cảm xúc: Wow / Uầy / Hay quá / Tên hay / Em phục)",
    "C": "C (đồng cảm: Em hiểu mà / Em nghe mà thương / Vất vả thật)",
    "D": "D (chuyển ý: Tiện đây em hỏi / À mà anh ơi / Em tò mò / Nhân tiện)",
}

# Mapping target_field → mô tả thân thiện cho LLM hiểu phải hỏi gì
_TARGET_FIELD_HINT = {
    "dealer_name": "tên cửa hàng (dealer_name)",
    "owner_name": "tên người chủ/người đang chat (owner_name)",
    "phone_or_zalo": "số Zalo hoặc SĐT khách hay liên hệ (phone_or_zalo)",
    "province": "tỉnh/thành phố (province)",
    "district": "quận/huyện (district)",
    "main_category": "ngành chính (main_category — cua_cuon/cua_nhom_kinh/cua_thep/tu_bep/solar/bao_tri_sua_chua/vlxd_tong_hop)",
    "dealer_type": "loại hình kinh doanh (dealer_type — đại lý/chủ xưởng/thợ đội/nhà thầu nhỏ/dịch vụ)",
    "customer_base_estimate": "ước lượng số khách cũ (customer_base_estimate)",
    "pain_points": "khó khăn/nỗi đau lớn nhất hiện tại (pain_points — vd: khách cũ ít quay lại, marketing yếu, ế ẩm, dịch bệnh)",
    "dl0_priority": "ưu tiên hỗ trợ trước (dl0_priority — bộ mặt số/QR khách cũ/bài đăng/trợ lý tư vấn)",
}


class Extractor:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def extract(
        self,
        messages: list[ChatMessage],
        forbidden_opener_group: str | None = None,
        target_field: str | None = None,
        is_tam_su: bool = False,
        is_defensive: bool = False,
    ) -> ExtractResult:
        conversation_text = self._format_conversation(messages)

        # Inject directive luân phiên opener vào CUỐI conversation_text (user
        # message), KHÔNG vào system prompt — để giữ prompt caching hoạt động.
        # System prompt giữ nguyên 13K tokens cache 5 phút → save 70% input cost.
        directives = []
        if forbidden_opener_group and forbidden_opener_group in _GROUP_DESC:
            directives.append(
                f"⛔ TURN NÀY confirm_questions[0] CẤM mở đầu bằng nhóm "
                f"{forbidden_opener_group}: {_GROUP_DESC[forbidden_opener_group]}. "
                "PHẢI chọn 1 trong 3 nhóm còn lại."
            )
        if is_defensive:
            # Dealer đang HỎI NGƯỢC / PHÒNG VỆ (Loại B) → BẮT BUỘC trả lời TRƯỚC.
            directives.append(
                "🚨 DEALER VỪA HỎI NGƯỢC / NGHI NGỜ (LOẠI B). BẮT BUỘC:\n"
                "  Câu 1-2: TRẢ LỜI THẲNG câu hỏi của dealer (cô đọng, value-focused).\n"
                "    - 'được lợi gì?' → liệt kê 4 công cụ MIỄN PHÍ (bộ mặt số, QR\n"
                "      khách cũ, bài đăng, trợ lý tư vấn).\n"
                "    - 'lừa đảo à?' → khẳng định KHÔNG, là Cộng Đồng Thợ 4.0 thật,\n"
                "      anh tự tra được.\n"
                "    - 'lấy data làm gì?' → CHỈ để team support, không bán/spam.\n"
                "  Câu 3: SAU khi đã giải đáp, NHẸ NHÀNG xin info hoặc dẫn field.\n"
                "TUYỆT ĐỐI KHÔNG bỏ qua câu hỏi của dealer rồi hỏi field thẳng."
            )
        elif is_tam_su:
            # Dealer đang kể chuyện đời thường → BẮT BUỘC engage, KHÔNG bypass.
            directives.append(
                "🌷 DEALER VỪA NÓI CHUYỆN ĐỜI THƯỜNG (không phải data cửa hàng).\n"
                "BẮT BUỘC confirm_questions[0] phải:\n"
                "  Câu 1: ENGAGE THẬT về điều dealer vừa kể (chia sẻ/đồng cảm/pha trò\n"
                "         như bạn bè — vd: 'Wow anh chơi bóng à, vui ghê', 'Em đồng cảm\n"
                "         lắm anh ơi', 'Hihi anh trêu em rồi'). KHÔNG bỏ qua chi tiết.\n"
                "  Câu 2-3: Sau khi engage, mới NHẸ NHÀNG dẫn về câu hỏi field.\n"
                "TUYỆT ĐỐI KHÔNG mở đầu bằng câu hỏi field thẳng — phải engage trước."
            )
        elif target_field:
            target_label = _TARGET_FIELD_HINT.get(target_field, target_field)
            directives.append(
                f"💡 Gợi ý: field còn thiếu trong hồ sơ là {target_label}. "
                "Em vẫn theo NGUYÊN TẮC CHUNG (lắng nghe dealer trước). Sau khi "
                "ack điều dealer vừa nói, dẫn về field này."
            )
        if directives:
            conversation_text = conversation_text + "\n\n" + "\n\n".join(directives) + "\n"

        raw = self.llm.extract_structured(
            system_prompt=prompts.EXTRACTOR_SYSTEM_PROMPT,
            conversation_text=conversation_text,
            tool_name=prompts.EXTRACTION_TOOL_NAME,
            tool_description=prompts.EXTRACTION_TOOL_DESCRIPTION,
            input_schema=prompts.EXTRACTION_TOOL_SCHEMA,
        )

        # Sanitize confidence dict — LLM đôi khi trả "N/A" / "UNKNOWN" / "MED"
        # cho field không xác định. Coerce về LOW để tránh pydantic reject.
        confidence_raw = raw.get("confidence") or {}
        if isinstance(confidence_raw, dict):
            valid = {"LOW", "MEDIUM", "HIGH"}
            mapping = {"MED": "MEDIUM", "M": "MEDIUM", "H": "HIGH", "L": "LOW"}
            sanitized = {}
            for k, v in confidence_raw.items():
                if not isinstance(v, str):
                    continue
                v_upper = v.strip().upper()
                if v_upper in valid:
                    sanitized[k] = v_upper
                elif v_upper in mapping:
                    sanitized[k] = mapping[v_upper]
                else:
                    sanitized[k] = "LOW"
            raw["confidence"] = sanitized

        result = ExtractResult(**raw)
        # raw_transcript ghép TOÀN BỘ dealer message (không truncate) — đây là
        # bản raw cho audit/trace, không phải input LLM.
        result.raw_transcript = "\n".join(
            m.content for m in messages if m.role == ChatRole.DEALER and m.content
        )
        return result

    @staticmethod
    def _format_conversation(messages: list[ChatMessage]) -> str:
        lines = ["Đây là hội thoại giữa Em Linh (bot) và dealer:\n"]
        # Truncate: chỉ gửi N message gần nhất cho LLM. Phần cũ có summary line.
        if len(messages) > HISTORY_WINDOW:
            cut = len(messages) - HISTORY_WINDOW
            lines.append(
                f"(... đã có {cut} tin nhắn cũ trước đó — "
                "thông tin tên/SĐT/địa chỉ đã trao đổi nếu có ...)"
            )
            recent = messages[-HISTORY_WINDOW:]
        else:
            recent = messages

        for m in recent:
            speaker = "Em Linh" if m.role.value == "bot" else "Dealer"
            lines.append(f"{speaker}: {m.content}")
        lines.append(
            "\nHãy trích xuất Dealer Profile RAW theo schema. "
            "Gọi tool save_dealer_extraction với đầy đủ field."
        )
        return "\n".join(lines)
