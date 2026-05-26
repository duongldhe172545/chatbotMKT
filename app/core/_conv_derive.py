"""Auto-derive Scope 2 wiring sau extract — Phase 6 R2 refactor.

Refer:
- F2A.3 Scope 2 — 12 derive fields
- F2B.7 (LUAT_2B_llm) — auto-derive brand_short / initials / slogan / main_category
- F2A.8 — province/district auto-derive
- D8 STRATEGY — LLM_FAST cho derive, LLM_QUALITY cho slogan
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.address_parser import parse_address
from app.llm.auto_derive import (
    derive_brand_short,
    derive_main_category,
    gen_initial_single,
    gen_initials_full,
    gen_slogans,
)
from app.llm.client import LLMClient
from app.models.schema import DealerProfileRaw

logger = logging.getLogger(__name__)


def merge_extracted(
    profile: DealerProfileRaw,
    extracted: dict,
    client: Optional[LLMClient] = None,
) -> None:
    """Merge extracted dict vào profile (chỉ field non-None) + auto-derive Scope 2.

    Auto-derive sau khi merge:
    - address → province + district (Layer 1 regex + Layer 2 LLM fuzzy)
    - main_product → main_category (LLM_FAST)
    - dealer_name → brand_short + initials_full + initial_single
    - owner_name → contact_name (default copy)
    - phone_or_zalo → hotline (default copy)
    - dealer_name + main_product → slogan_options (LLM_QUALITY 5 phương án)
    """
    for field, value in extracted.items():
        if value is None:
            continue
        if not hasattr(profile, field):
            logger.warning("Extracted field %s không có trong DealerProfileRaw", field)
            continue
        setattr(profile, field, value)

    # Province + district sau khi address fill
    if "address" in extracted and extracted.get("address") and not profile.province:
        province, district = parse_address(profile.address, client=client)
        if province:
            profile.province = province
        if district:
            profile.district = district

    # main_category sau khi main_product fill
    if (
        client is not None
        and "main_product" in extracted
        and extracted.get("main_product")
        and not profile.main_category
    ):
        context = ""
        if profile.category_stack:
            context = f"category_stack: {', '.join(profile.category_stack)}"
        derived = derive_main_category(profile.main_product, client, context)
        if derived:
            profile.main_category = derived
            logger.info(
                "Auto-derive main_category: %r → %s",
                profile.main_product, derived,
            )
        else:
            logger.warning(
                "Auto-derive main_category fail/null cho main_product=%r",
                profile.main_product,
            )

    # brand_short + initials sau khi dealer_name fill
    if (
        client is not None
        and "dealer_name" in extracted
        and extracted.get("dealer_name")
    ):
        if not profile.brand_name_short:
            short = derive_brand_short(profile.dealer_name, client)
            if short:
                profile.brand_name_short = short
                logger.info("Auto-derive brand_short: %r → %r", profile.dealer_name, short)
        if not profile.initials_full:
            initials = gen_initials_full(profile.dealer_name)
            if initials:
                profile.initials_full = initials
                if not profile.initial_single:
                    profile.initial_single = gen_initial_single(initials)

    # contact_name = owner_name (default copy)
    if (
        "owner_name" in extracted
        and extracted.get("owner_name")
        and not profile.contact_name
    ):
        profile.contact_name = profile.owner_name

    # hotline = phone_or_zalo (default copy)
    if (
        "phone_or_zalo" in extracted
        and extracted.get("phone_or_zalo")
        and not profile.hotline
    ):
        profile.hotline = profile.phone_or_zalo

    # Slogan options — sau khi đủ dealer_name + main_product
    if (
        client is not None
        and "main_product" in extracted
        and extracted.get("main_product")
        and profile.dealer_name
        and not profile.slogan_options
    ):
        slogans = gen_slogans(
            dealer_name=profile.dealer_name,
            main_product=profile.main_product,
            client=client,
            province=profile.province,
            use_quality=True,
        )
        if slogans:
            profile.slogan_options = slogans
            logger.info(
                "Auto-derive slogans: dealer=%r → %d options",
                profile.dealer_name, len(slogans),
            )
