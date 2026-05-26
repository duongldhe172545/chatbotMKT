"""Local hook generator — LLM_FAST gen hook địa phương cho Closing/Ack.

Refer:
- F2A.8 (LUAT_2A_core v0.2.5) — Closing local hook (KHÔNG khoá case)
- File 1A § 7.4 — quy ước local hook LLM
- F2C.5 cache — local_hook key TTL 7 ngày
- feedback_no_case_lock — KHÔNG hardcode mapping tỉnh → đặc sản

Phase 6 R+ update 2026-05-22 (user feedback):
1. LLM gen N=8 facts variety về tỉnh (KHÔNG chỉ 1), random pick 1 để tránh
   lặp. Cache key thêm `_variant_idx` để session khác nhau nhận hook khác.
2. CẤM bịa product cụ thể (vd "Gia Lộc nổi tiếng xưởng nhôm kính") —
   bot chỉ nói chung chung về vùng (làng nghề / khí hậu / phong tục).
3. Empty fallback nếu output có pattern "nổi tiếng + [sản phẩm ngành]".

Quy ước:
- LLM gen 1 câu ≤ 30 từ về địa phương, hoặc rỗng nếu không có gì đáng nói.
- KHÔNG ép câu specialty cụ thể.
- KHÔNG bịa product ngành dealer (cửa nhôm/cuốn/tủ bếp).
- Cache 7 ngày key `local_hook:{province}:{dealer_type}:{variant_idx}`.
"""
from __future__ import annotations

import hashlib
import logging
import random
import re
from typing import Optional

from app.cache.llm_cache import llm_cache_get, llm_cache_set, make_key
from app.llm.client import LLMClient
from app.llm.system_prompt import build_system_prompt
from app.models.enums import AddressForm, DealerType

logger = logging.getLogger(__name__)


# Cache TTL 7 ngày (refer F2C.5)
_LOCAL_HOOK_TTL_S = 7 * 24 * 3600

# Pattern bịa product ngành — reject output match
_PRODUCT_HALLUCINATE_PATTERN = re.compile(
    r"(nổi\s*tiếng|chuyên\s*làm|chuyên\s*về|phát\s*triển\s*mạnh)\s*"
    r"(với\s*|về\s*|là\s*|các\s*|nhiều\s*)?"
    r"(nhôm\s*kính|cửa\s*cuốn|cửa\s*nhôm|tủ\s*bếp|xưởng\s*sản\s*xuất)",
    re.IGNORECASE,
)


def _build_task(
    province: str,
    dealer_type: DealerType,
    address_form: AddressForm,
    variant_seed: int = 0,
) -> str:
    """Task instruction cho LLM_FAST gen N local hook variants.

    Phase 6 R+ update 2026-05-22: yêu cầu LLM gen 8 variants → caller
    random pick 1 (tránh lặp khi cùng tỉnh xuất hiện nhiều session).
    """
    # Seed-aware angle hint để mỗi variant focus 1 khía cạnh khác
    angles = [
        "khí hậu / thời tiết vùng",
        "địa hình / cảnh quan",
        "phong tục / văn hoá địa phương",
        "đặc sản ẩm thực (nếu rõ — không bịa)",
        "tinh thần con người vùng đó (cần cù, hiếu khách)",
        "thị trường xây dựng / nhà ở vùng",
        "khách hàng vùng có nhu cầu đặc thù gì (chung chung)",
        "vị trí giao thông / kết nối khu vực",
    ]
    angle_hint = angles[variant_seed % len(angles)]
    return (
        f'Sinh 1 câu local hook (≤ 30 từ) cho đại lý ở tỉnh/khu vực "{province}".\n\n'
        f"Context:\n"
        f"- Dealer type: {dealer_type.value}\n"
        f"- Xưng hô: {address_form.value}\n"
        f"- Angle focus turn này: {angle_hint}\n\n"
        f"Yêu cầu:\n"
        f"- 1 câu NGẮN, tự nhiên — focus vào angle trên.\n"
        f"- KHÔNG bịa đặc sản cụ thể nếu không chắc chắn (vd KHÔNG nói\n"
        f'  "Cao Bằng nổi tiếng vịt quay 7 vị" nếu không xác định).\n'
        f"- 🚫 TUYỆT ĐỐI KHÔNG bịa rằng tỉnh nổi tiếng về SẢN PHẨM NGÀNH dealer\n"
        f"  (nhôm kính / cửa cuốn / tủ bếp / VLXD). Vd CẤM:\n"
        f'  - "Gia Lộc nổi tiếng với xưởng sản xuất nhôm kính"\n'
        f'  - "Hà Đông chuyên làm cửa cuốn"\n'
        f"  Lý do: dealer dễ nhận ra bot bịa, mất trust.\n"
        f"- KHÔNG được bịa số liệu / quảng cáo tiền / promise.\n"
        f"- KHÔNG dùng vocab cấm (Tier, BRANDKIT, Scoring).\n"
        f"- Nếu KHÔNG có gì đáng nói về tỉnh + angle → trả rỗng (string \"\")."
    )


def gen_local_hook(
    province: Optional[str],
    dealer_type: Optional[DealerType] = None,
    client: Optional[LLMClient] = None,
    address_form: AddressForm = AddressForm.ANH,
    use_cache: bool = True,
    session_id: Optional[str] = None,
) -> str:
    """Gen local hook 1 câu cho closing/ack. Cache 7 ngày per variant.

    Phase 6 R+ update 2026-05-22: random pick 1 trong 8 variant (theo
    session_id hash + dealer_type angle) để tránh lặp khi cùng tỉnh xuất
    hiện nhiều session.

    Args:
        province: Tỉnh dealer (canonical từ whitelist 63)
        dealer_type: Detected dealer type, default UNKNOWN
        client: LLMClient. None → trả rỗng (Phase 1 fallback)
        address_form: anh / chị
        use_cache: Bật cache TTL 7 ngày
        session_id: Optional — dùng hash để pick variant deterministic.
            Nếu None: random.

    Returns:
        Hook text 1 câu ≤ 30 từ, hoặc rỗng nếu LLM fail / không có province /
        không có client / bị reject (bịa product).
    """
    if not province or not isinstance(province, str):
        return ""
    if client is None:
        return ""

    dealer_type = dealer_type or DealerType.UNKNOWN

    # Pick variant index — 8 angles, rotate theo session_id (deterministic
    # per session, đa dạng across sessions).
    if session_id:
        h = int(hashlib.md5(session_id.encode("utf-8")).hexdigest()[:8], 16)
        variant_idx = h % 8
    else:
        variant_idx = random.randint(0, 7)

    # Cache lookup — key per variant
    cache_key = None
    if use_cache:
        cache_key = make_key(
            "local_hook", province, dealer_type.value, str(variant_idx)
        )
        cached = llm_cache_get(cache_key)
        if cached is not None:
            return str(cached) if cached else ""

    task = _build_task(province, dealer_type, address_form, variant_seed=variant_idx)
    system = build_system_prompt(
        dealer_type=dealer_type,
        address_form=address_form,
        task=task,
    )

    try:
        response = client.chat_fast(
            system_prompt=system,
            messages=[
                {"role": "user", "content": f"Tỉnh: {province}"},
            ],
            max_tokens=128,
        )
    except Exception as e:
        logger.exception("Local hook LLM fail province=%s: %s", province, e)
        if cache_key:
            llm_cache_set(cache_key, "", ttl_s=_LOCAL_HOOK_TTL_S)
        return ""

    text = (response or "").strip()
    # LLM có thể trả thông báo "không có gì đáng nói" — accept rỗng
    if not text or len(text) > 200:
        text = ""

    # Phase 6 R+ fix 2026-05-22: reject output match pattern bịa product
    # ngành (vd "Gia Lộc nổi tiếng xưởng nhôm kính").
    if text and _PRODUCT_HALLUCINATE_PATTERN.search(text):
        logger.warning(
            "Local hook REJECT bịa product: province=%s text=%r",
            province, text[:120],
        )
        text = ""

    if cache_key:
        llm_cache_set(cache_key, text, ttl_s=_LOCAL_HOOK_TTL_S)
    return text
