"""Greeting handler — LLM-driven responses for Stage.GREETING.

Handles benefit questions, pings, and casual greetings dynamically
using the Em Linh persona to provide a premium, natural user experience.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.llm.client import LLMClient
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


def _build_greeting_task(
    dealer_message: str,
    intent_type: str,  # "benefit", "ping", or "casual"
    address_form: str,
) -> str:
    """Build the task instruction for the greeting LLM response."""
    af = address_form
    if intent_type == "benefit":
        return (
            f"Dealer vừa hỏi về quyền lợi / lợi ích khi tham gia: \"{dealer_message}\"\n\n"
            f"Nhiệm vụ:\n"
            f"1. Trả lời trực tiếp và rõ ràng: Sau cuộc trò chuyện ngắn khoảng 4-5 phút này, "
            f"Cộng Đồng Thợ 4.0 sẽ tặng {af} một bộ thương hiệu hoàn toàn miễn phí "
            f"(gồm logo riêng, danh thiếp cá nhân hóa và video giới thiệu thương hiệu) gửi qua Zalo.\n"
            f"2. Hỏi xem {af} đã sẵn sàng bắt đầu cuộc trò chuyện chưa một cách tự nhiên và ấm áp.\n\n"
            f"Yêu cầu:\n"
            f"- Chiều dài: 35-65 từ (2-3 câu ngắn gọn).\n"
            f"- Xưng hô: Em xưng \"em\", gọi dealer là \"{af}\" và tôn trọng.\n"
            f"- Không hứa hẹn tiền bạc, không dùng từ ngữ tiếng Anh."
        )
    elif intent_type == "ping":
        return (
            f"Dealer vừa ping / chào hỏi kiểm tra: \"{dealer_message}\"\n\n"
            f"Nhiệm vụ:\n"
            f"1. Phản hồi lại lời ping một cách vui vẻ và ấm áp: Xác nhận em là Linh đang ở đây "
            f"để hỗ trợ {af} làm bộ thương hiệu miễn phí cho cửa hàng.\n"
            f"2. Hỏi xem nếu {af} tiện thì mình bắt đầu cuộc trò chuyện nhé.\n\n"
            f"Yêu cầu:\n"
            f"- Chiều dài: 30-55 từ.\n"
            f"- Xưng hô: Em xưng \"em\", gọi dealer là \"{af}\".\n"
            f"- Giọng điệu nhiệt tình, hiếu khách, sử dụng tối đa 1 emoji thích hợp."
        )
    else:  # casual or greeting-ack with data/casual commentary
        return (
            f"Dealer gửi một câu trả lời casual hoặc bắt đầu cuộc trò chuyện: \"{dealer_message}\"\n\n"
            f"Nhiệm vụ:\n"
            f"1. Phản hồi ghi nhận (ack) thân thiện câu nói của {af} một cách tự nhiên.\n"
            f"2. Giải thích lý do chuyển ý ngắn gọn: Để thiết kế bộ quà tặng thương hiệu chính xác, em cần xin một số thông tin.\n"
            f"3. Hỏi câu hỏi đầu tiên (slot 1.1): Mời {af} cho em xin tên cá nhân và tên cửa hàng của mình.\n\n"
            f"Yêu cầu:\n"
            f"- Chiều dài: 40-70 từ (liền mạch, ấm áp).\n"
            f"- Xưng hô: Em xưng \"em\", gọi dealer là \"{af}\".\n"
            f"- Lồng ghép câu hỏi xin tên xưởng và tên {af} cực kỳ mềm mại ở cuối."
        )


def handle_greeting_llm(
    dealer_message: str,
    intent_type: str,  # "benefit", "ping", or "casual"
    address_form: AddressForm,
    client: LLMClient,
    history_summary: str = "(chưa có)",
) -> Optional[str]:
    """Generate dynamic greeting response using LLM_FAST."""
    if not dealer_message:
        return None

    task = _build_greeting_task(
        dealer_message=dealer_message,
        intent_type=intent_type,
        address_form=address_form.value,
    )

    system_prompt = build_system_prompt(
        dealer_type=DealerType.UNKNOWN,
        address_form=address_form,
        current_slot="GREETING",
        history_summary=history_summary,
        task=task,
    )

    try:
        response = client.chat_fast(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": dealer_message}],
            max_tokens=256,
        )
        text = (response or "").strip()
        if text:
            return text
    except Exception as e:
        logger.exception("Failed to generate dynamic greeting response: %s", e)

    return None
