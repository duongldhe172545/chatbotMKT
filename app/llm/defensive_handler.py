"""Defensive handler — LLM_QUALITY gen response 3-component khi dealer hỏi defensive.

Refer:
- F2B.4b (LUAT_2B_llm) — defensive handler spec
- File 1C § 2 — defensive lặp 3 cấp
- File 1B § 2.3 — Lo tone 3-component pattern
- STRATEGY D8 — defensive dùng LLM_QUALITY

Pattern: 3 thành phần bắt buộc
1. Trấn an trực tiếp vào lo lắng dealer
2. Cam kết bảo mật CỤ THỂ (lưu nội bộ / không share / xoá lúc nào)
3. Quay slot nhẹ nhàng

Tier: LLM_QUALITY (cần empathy + judgement)
Fallback: caller dùng template L1/L2/L3 từ edge_cases nếu LLM fail.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.llm.client import LLMClient
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


DEFENSIVE_ESCALATE_AT = 3  # Lần thứ N defensive → kết offer dừng


def _build_defensive_task(
    dealer_message: str,
    defensive_count: int,
    turn_count: int,
    dealer_type: DealerType,
) -> str:
    """Build task instruction cho LLM_QUALITY defensive handler.

    Phase 6 R+ update 2026-05-22 (user feedback): bot phải TRẢ LỜI CỤ THỂ
    câu dealer hỏi, KHÔNG spam template chung chung "em chỉ hỗ trợ tư vấn
    chiến lược..." khi dealer hỏi câu cụ thể (vd "có lừa đảo không?",
    "tặng tiền không?", "phí gì?").
    """
    is_l3 = defensive_count >= DEFENSIVE_ESCALATE_AT
    base = (
        f'Đại lý vừa hỏi defensive / nghi ngờ: "{dealer_message}"\n\n'
        f"Context:\n"
        f"- Đã trò chuyện {turn_count} turn\n"
        f"- Defensive lần thứ {defensive_count} trong session\n"
        f"- Dealer type: {dealer_type.value}\n\n"
        f"Sinh 1 response 3 thành phần (refer File 1B § 2.3 Lo pattern):\n"
        f'1. **TRẢ LỜI TRỰC TIẾP câu hỏi dealer** — addresses cụ thể nội dung\n'
        f'   câu dealer vừa hỏi, KHÔNG né tránh, KHÔNG spam template chung:\n'
        f'   - Nếu dealer hỏi "lừa đảo không?" / "phí gì?" → nói thẳng:\n'
        f'     "Dạ KHÔNG lừa đảo, KHÔNG mất phí gì cả ạ. Bộ thương hiệu\n'
        f'     (logo + danh thiếp + video) hoàn toàn miễn phí."\n'
        f'   - Nếu dealer hỏi "tặng tiền không?" → nói thẳng:\n'
        f'     "Dạ KHÔNG, em không tặng tiền/ưu đãi gì ạ. Em chỉ tặng\n'
        f'     bộ thương hiệu miễn phí thôi."\n'
        f'   - Nếu dealer hỏi "ai làm?" / "công ty nào?" → nói thẳng:\n'
        f'     "Dạ team Cộng Đồng Thợ 4.0 làm ạ, em là trợ lý số phía trước."\n'
        f"2. Cam kết bảo mật CỤ THỂ (vd em lưu nội bộ, không share ra ngoài,\n"
        f"   anh có quyền yêu cầu xoá bất kỳ lúc nào) — 1 câu ngắn.\n"
        f'3. Quay slot nhẹ nhàng ("mình tiếp tục được không ạ?")\n\n'
        f"Yêu cầu:\n"
        f"- 30-60 từ tổng (3 phần phải đủ, KHÔNG quá dài, KHÔNG quá ngắn)\n"
        f'- KHÔNG mặc cả ("tin em đi")\n'
        f"- KHÔNG promise tiền / ưu đãi / job / pháp lý / thuế / y tế\n"
        f"- KHÔNG dùng vocab cấm (Tier, BRANDKIT, Scoring, ...)\n"
        f"- KHÔNG dùng cliche 'hệ thống hỗ trợ chiến lược' — bot không có hệ thống.\n"
        f"  Thay = 'em lưu vào hồ sơ' / 'em note' / 'em ghi nhận'.\n"
    )
    if is_l3:
        base += (
            f"\n⚠️ Defensive lần ≥ {DEFENSIVE_ESCALATE_AT} → THAY phần 3 "
            f"bằng câu OFFER DỪNG nhẹ nhàng: "
            f'"Anh không muốn tiếp em cũng OK ạ, em ghi nhận tới đây."'
        )
    return base


def handle_defensive(
    dealer_message: str,
    defensive_count: int,
    dealer_type: DealerType,
    address_form: AddressForm,
    client: LLMClient,
    turn_count: int = 0,
    history_summary: str = "(chưa có)",
    current_slot: Optional[str] = None,
    bridge_avoid_hint: str = "",
) -> Optional[str]:
    """Gen LLM_QUALITY response cho intent=DEFENSIVE.

    Args:
        dealer_message: Raw dealer message gây defensive
        defensive_count: Số lần defensive trong session (≥ 1)
        dealer_type: Detected dealer type (UNKNOWN nếu chưa detect)
        address_form: anh / chị
        client: LLMClient
        turn_count: Tổng số turn đến hiện tại
        history_summary: Tóm tắt 3 turn gần
        current_slot: Slot đang hỏi (cho system prompt context)

    Returns:
        Response text, hoặc None nếu LLM fail / empty (caller fallback template).
    """
    if not dealer_message or not isinstance(dealer_message, str):
        return None

    dealer_type = dealer_type or DealerType.UNKNOWN
    task = _build_defensive_task(
        dealer_message=dealer_message,
        defensive_count=max(1, defensive_count),
        turn_count=turn_count,
        dealer_type=dealer_type,
    )

    system_prompt = build_system_prompt(
        dealer_type=dealer_type,
        address_form=address_form,
        current_slot=current_slot,
        history_summary=history_summary,
        task=task,
        bridge_avoid_hint=bridge_avoid_hint,
    )

    try:
        response = client.chat_quality(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": dealer_message}],
            max_tokens=768,
        )
    except Exception as e:
        logger.exception(
            "Defensive handler LLM fail: count=%d msg=%r err=%s",
            defensive_count, dealer_message[:80], e,
        )
        return None

    text = (response or "").strip()
    if not text:
        logger.warning(
            "Defensive handler LLM returned empty: count=%d msg=%r",
            defensive_count, dealer_message[:80],
        )
        return None
    return text
