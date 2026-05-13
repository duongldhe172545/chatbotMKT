"""Replier — sinh reply tiếng Việt cho dealer (Bước 1 refactor).

Triết lý:
- Tách trách nhiệm với Extractor: Replier CHỈ sinh text, Extractor CHỈ trích field.
- System prompt gọn (~3K token thay vì ~10K) → attention focused, ít bịa.
- Goal cụ thể của turn được inject runtime — không phải nhồi mọi case vào prompt.
- Chuyển logic "đếm intent / chọn target_field" sang Python (Conductor),
  Replier chỉ làm "Performer" tuân theo goal đã chọn.

Cách dùng:
    replier = Replier(llm)
    reply = replier.reply(
        messages=session.messages,
        goal=Goal(kind="ASK_FIELD", field="phone_or_zalo", ...),
        profile=session.profile_raw,
        address="anh",
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core import prompts
from app.llm.base import LLMProvider
from app.models.schema import ChatMessage, ChatRole, DealerProfileRaw

# Số message gần nhất gửi cho LLM. Replier không cần xa như Extractor
# vì không phải reconstruct toàn bộ profile — chỉ cần context gần để reply.
HISTORY_WINDOW = 12


GoalKind = Literal[
    "ASK_FIELD",          # hỏi field cụ thể (target_field) — legacy v6
    "V7_TURN",            # đi theo flow v7 — instruction load từ v7_turns.py
    "ANSWER_DEFENSIVE",   # dealer hỏi ngược → trả lời thẳng + dẫn về field
    "ENGAGE_TAM_SU",      # dealer kể chuyện đời → engage + dẫn về field
    "HANDLE_REFUSAL",     # dealer từ chối field → respect + skip + hỏi field khác
    "FREE",               # không có goal cụ thể (LLM tự xử theo persona)
]


@dataclass
class Goal:
    """Mô tả mục tiêu turn này — Conductor chọn, Replier thực thi."""
    kind: GoalKind
    target_field: str | None = None       # field cần hỏi (cho ASK_FIELD)
    v7_turn_id: str | None = None         # turn id v7 (cho V7_TURN) — vd "2.3"
    skipped_field: str | None = None      # field vừa bị refuse (cho HANDLE_REFUSAL)
    next_field: str | None = None         # field tiếp theo (cho HANDLE_REFUSAL/ENGAGE_TAM_SU)
    forbidden_opener_group: str | None = None  # nhóm A/B/C/D bị cấm
    extra_hint: str | None = None         # tự do — thêm context cho turn đặc biệt


# Mapping field → mô tả thân thiện cho LLM (giống extractor cũ, để consistent)
_FIELD_DESC = {
    "dealer_name": "tên cửa hàng/đại lý",
    "owner_name": "tên người chủ/người đang chat",
    "phone_or_zalo": "số Zalo hoặc SĐT khách hay liên hệ",
    "province": "tỉnh/thành phố",
    "district": "quận/huyện",
    "main_category": "ngành chính (cửa cuốn / nhôm kính / cửa thép / tủ bếp / solar / bảo trì / VLXD tổng hợp)",
    "dealer_type": "loại hình kinh doanh (đại lý / chủ xưởng / thợ đội / nhà thầu nhỏ / dịch vụ)",
    "customer_base_estimate": "ước lượng số khách cũ trong 2-3 năm gần đây",
    "pain_points": "khó khăn lớn nhất hiện tại (khách cũ ít quay lại / marketing yếu / ế ẩm / thợ không ổn / dịch bệnh...)",
    "dl0_priority": "ưu tiên hỗ trợ trước (bộ mặt số / QR khách cũ / bài đăng / trợ lý tư vấn)",
}


_GROUP_NAMES = {
    "A": "A (acknowledge: Dạ em ghi nhận / Em note / Oke / Dạ vâng)",
    "B": "B (cảm xúc: Wow / Uầy / Hay quá / Em phục)",
    "C": "C (đồng cảm: Em hiểu mà / Em nghe mà thương / Vất vả thật)",
    "D": "D (chuyển ý: Tiện đây em hỏi / À mà anh ơi / Em tò mò)",
}


class Replier:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def reply(
        self,
        messages: list[ChatMessage],
        goal: Goal,
        profile: DealerProfileRaw,
        address: str = "anh",
    ) -> str:
        """Sinh reply text cho dealer dựa vào goal + profile state.

        Returns: text reply (string, không markdown bullet).
        """
        history = self._build_history(messages)
        instruction = self._build_instruction(goal, profile, address)

        # Inject instruction CUỐI message user (không phải system) — để giữ
        # prompt caching trên system prompt cố định, save 70% input cost.
        if history and history[-1]["role"] == "user":
            history[-1]["content"] = history[-1]["content"] + "\n\n" + instruction
        else:
            history.append({"role": "user", "content": instruction})

        return self.llm.chat(
            system_prompt=prompts.REPLIER_SYSTEM_PROMPT,
            messages=history,
            max_tokens=384,
        )

    @staticmethod
    def _build_history(messages: list[ChatMessage]) -> list[dict]:
        """Convert ChatMessage → format Anthropic API (xen kẽ user/assistant)."""
        clean = [m for m in messages if (m.content or "").strip()]
        recent = clean[-HISTORY_WINDOW:]

        merged: list[dict] = []
        for m in recent:
            role = "user" if m.role == ChatRole.DEALER else "assistant"
            content = m.content.strip()
            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n" + content
            else:
                merged.append({"role": role, "content": content})

        # Anthropic yêu cầu bắt đầu user
        if not merged or merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "(bắt đầu hội thoại)"})

        # Đảm bảo kết thúc user (để LLM phản hồi)
        if merged[-1]["role"] != "user":
            merged.append({"role": "user", "content": "(em nói tiếp đi)"})

        return merged

    @staticmethod
    def _build_instruction(goal: Goal, profile: DealerProfileRaw, address: str) -> str:
        """Sinh instruction block inject cuối user message.

        Bao gồm: PROFILE SO FAR (v6+v7 fields) + ADDRESS_FORM + GOAL cụ thể.
        """
        parts = []

        # 1. PROFILE SNAPSHOT — anchor để LLM không bịa
        prof_lines = []
        # Scalar fields — v6 + v7
        scalar_fields = (
            # v6 core
            "dealer_name", "owner_name", "phone_or_zalo",
            "province", "district", "main_category",
            "customer_base_estimate",
            # v7 identity
            "address", "province_specialty",
            # v7 business
            "main_product", "business_model_signal",
            "est_team_size", "team_stability_signal",
            "customer_segment_signal",
            # v7 channels
            "zalo", "facebook", "primary_contact_channel",
            "fb_marketing_status",
            # v7 mỏ vàng
            "customer_old_percentage", "customer_storage_method",
            "customer_pain", "usp_signal", "payment_terms_signal",
            # v7 brandkit
            "brandkit_consent", "color_accent", "feng_shui_signal",
        )
        for field in scalar_fields:
            val = getattr(profile, field, None)
            if val not in (None, "", []):
                prof_lines.append(f"  - {field}: {val}")
        # List fields
        if profile.pain_points:
            prof_lines.append(f"  - pain_points: {', '.join(profile.pain_points)}")
        if profile.dl0_priority:
            prof_lines.append(f"  - dl0_priority: {', '.join(profile.dl0_priority)}")
        if profile.category_stack:
            prof_lines.append(f"  - category_stack: {', '.join(profile.category_stack)}")
        if profile.supplier_brands:
            prof_lines.append(f"  - supplier_brands: {', '.join(profile.supplier_brands)}")
        if prof_lines:
            parts.append("PROFILE SO FAR (chỉ nhắc số/tên có trong list này, KHÔNG bịa):\n"
                         + "\n".join(prof_lines))
        else:
            parts.append("PROFILE SO FAR: (chưa có data nào)")

        # 2. ADDRESS FORM
        parts.append(f"ADDRESS_FORM: gọi dealer là \"{address}\", em xưng \"em\".")

        # 3. GOAL TURN NÀY
        goal_text = Replier._format_goal(goal)
        parts.append(f"GOAL TURN NÀY:\n{goal_text}")

        # 4. FORBIDDEN OPENER (nếu có)
        if goal.forbidden_opener_group and goal.forbidden_opener_group in _GROUP_NAMES:
            parts.append(
                f"⛔ TURN NÀY CẤM mở đầu bằng nhóm "
                f"{_GROUP_NAMES[goal.forbidden_opener_group]}. "
                f"Chọn 1 trong 3 nhóm còn lại."
            )

        return "\n\n".join(parts)

    @staticmethod
    def _format_goal(goal: Goal) -> str:
        """Convert Goal struct → instruction text rõ ràng cho LLM."""
        if goal.kind == "V7_TURN":
            # Import muộn để tránh circular (v7_turns → ... → replier)
            from app.core.v7_turns import get_turn
            t = get_turn(goal.v7_turn_id or "")
            if not t:
                return (
                    "Tự do trả lời theo persona chuyên gia MKT. "
                    "Hỏi tiếp theo flow nếu hợp lý."
                )
            base = (
                f"=== TURN {t.turn_id} ({t.theme}) — {t.description} ===\n\n"
                f"{t.instruction}\n\n"
                f"🚨 BẮT BUỘC STRICT — KHÔNG ĐƯỢC DRIFT:\n"
                f"1. CHỈ hỏi đúng câu hỏi của TURN {t.turn_id} ở trên — KHÔNG\n"
                f"   tự đoán flow + hỏi câu khác (vd: turn này hỏi địa chỉ\n"
                f"   thì TUYỆT ĐỐI KHÔNG hỏi sđt; turn 4.0 hỏi consent thì\n"
                f"   KHÔNG hỏi pain/tool; turn 4.2 hỏi màu+phong thủy thì\n"
                f"   KHÔNG xin consent lại).\n"
                f"2. KHÔNG gộp nhiều turn vào 1 reply — mỗi reply CHÍ 1 ý hỏi.\n"
                f"3. Cấu trúc reply: ACK data dealer vừa cho (1 câu) → LÝ DO\n"
                f"   hỏi tiếp (nếu có) → CHÍNH XÁC câu hỏi của turn này.\n"
                f"4. Độ dài: 2-5 câu, 40-120 từ. Tone CHUYÊN GIA KHIÊM TỐN.\n"
                f"5. KHÔNG bịa data ngoài PROFILE SO FAR. KHÔNG mở đầu mệnh lệnh."
            )
            if goal.extra_hint:
                base += f"\n\n📎 Lưu ý thêm: {goal.extra_hint}"
            return base

        if goal.kind == "ASK_FIELD":
            field = goal.target_field or ""
            desc = _FIELD_DESC.get(field, field)
            base = (
                f"Hỏi dealer về: **{desc}**.\n"
                f"  Cấu trúc reply tự nhiên (50-80 từ):\n"
                f"  - KHEN/REACT về data dealer vừa cho (1 câu cụ thể, có\n"
                f"    cảm xúc — vd 'Tên hay ghê!', 'Ngành đó tiềm năng quá!').\n"
                f"  - NÊU LÝ DO hỏi tiếp — dealer được lợi gì (vd 'để em ghi\n"
                f"    hồ sơ chuẩn', 'để khách tìm anh dễ hơn', 'để em gửi\n"
                f"    đúng tài liệu khu vực mình').\n"
                f"  - Hỏi field. 1 câu hỏi chính.\n"
                f"  Mẫu: 'Wow Hà Nội thị trường to nhỉ! Để em chọn đúng\n"
                f"  nhóm cộng đồng cho mình — anh hay làm mạnh nhất mảng\n"
                f"  nào ạ?'"
            )
            if goal.extra_hint:
                base += f"\n  - Lưu ý: {goal.extra_hint}"
            return base

        if goal.kind == "ANSWER_DEFENSIVE":
            base = (
                "Dealer đang HỎI NGƯỢC / NGHI NGỜ. BẮT BUỘC:\n"
                "  Câu 1-2: TRẢ LỜI THẲNG câu hỏi của dealer (cô đọng, value-focused).\n"
                "    - Nếu hỏi 'được lợi gì?' → liệt kê 4 công cụ MIỄN PHÍ:\n"
                "      bộ mặt số, QR khách cũ, bài đăng, trợ lý tư vấn.\n"
                "    - Nếu hỏi 'lừa đảo à?' → khẳng định KHÔNG, là Cộng Đồng Thợ 4.0\n"
                "      thật, anh có thể tra cứu để xác minh.\n"
                "    - Nếu hỏi 'lấy data làm gì?' → CHỈ team support, không bán/spam,\n"
                "      có quyền yêu cầu xoá bất kỳ lúc nào.\n"
                "    - Nếu hỏi 'có phí không?' → khẳng định MIỄN PHÍ giai đoạn pilot.\n"
                "  Câu 3: SAU khi đã giải đáp, NHẸ NHÀNG dẫn về xin info.\n"
                "TUYỆT ĐỐI KHÔNG bỏ qua câu hỏi của dealer rồi hỏi field thẳng."
            )
            if goal.target_field:
                desc = _FIELD_DESC.get(goal.target_field, goal.target_field)
                base += f"\n\nField cần hỏi sau khi giải đáp: {desc}."
            return base

        if goal.kind == "ENGAGE_TAM_SU":
            base = (
                "Dealer đang KỂ CHUYỆN ĐỜI THƯỜNG (không phải data cửa hàng).\n"
                "BẮT BUỘC:\n"
                "  Câu 1: ENGAGE THẬT về điều dealer vừa kể (chia sẻ/đồng cảm/pha\n"
                "         trò như bạn bè — vd: 'Wow anh chơi golf à, vui ghê',\n"
                "         'Em đồng cảm lắm', 'Hihi anh trêu em rồi'). KHÔNG bỏ\n"
                "         qua chi tiết, KHÔNG đưa lời khuyên y tế/pháp luật.\n"
                "  Câu 2-3: Sau khi engage, NHẸ NHÀNG dẫn về câu hỏi field.\n"
                "TUYỆT ĐỐI KHÔNG mở đầu bằng câu hỏi field thẳng."
            )
            if goal.next_field:
                desc = _FIELD_DESC.get(goal.next_field, goal.next_field)
                base += f"\n\nField cần dẫn về sau engage: {desc}."
            return base

        if goal.kind == "HANDLE_REFUSAL":
            skipped = _FIELD_DESC.get(goal.skipped_field or "", goal.skipped_field or "phần đó")
            next_desc = (
                _FIELD_DESC.get(goal.next_field, goal.next_field)
                if goal.next_field else None
            )
            base = (
                f"Dealer vừa TỪ CHỐI cung cấp {skipped}. BẮT BUỘC:\n"
                f"  Câu 1: Acknowledge tôn trọng quyết định của dealer (vd:\n"
                f"         'Dạ em tôn trọng anh ạ, không sao').\n"
                f"  Câu 2: Bỏ qua field đó, KHÔNG ép.\n"
            )
            if next_desc:
                base += (
                    f"  Câu 3: Chuyển sang hỏi field khác: {next_desc}.\n"
                    f"  Cụm bắc cầu — CHỌN ĐA DẠNG, KHÔNG lặp 'tiện đây':\n"
                    f"    'À mà anh ơi' / 'Còn 1 ý em hỏi anh' / 'Em tò mò xíu' /\n"
                    f"    'Nhân tiện em hỏi luôn' / 'Quay lại chuyện cửa hàng' /\n"
                    f"    hoặc vào thẳng câu hỏi không cần bridge."
                )
            else:
                base += "  Câu 3: Hỏi nhẹ liệu mình có thể hỗ trợ gì khác không."
            return base

        # FREE
        return "Tự do trả lời theo persona. Đọc intent dealer, ack/engage rồi tiếp tục flow tự nhiên."