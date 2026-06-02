from __future__ import annotations

from app.core.intake_coverage import compute_intake_coverage, field_to_slot
from app.core.session import create_session
from app.models.schema import DealerProfileRaw


def test_coverage_reports_required_missing_without_slot_script():
    coverage = compute_intake_coverage(DealerProfileRaw(owner_name="Hùng"))

    assert coverage.required_missing[0] == "dealer_name"
    assert coverage.recommended_focus == "dealer_name"
    assert coverage.recommended_slot == "1.1"
    assert not coverage.can_summarize


def test_required_fields_do_not_skip_linh_optional_survey():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công và thương mại",
        brandkit_consent="yes",
        logo_initials="auto",
        slogan_preference="auto",
        logo_style="auto",
    )

    coverage = compute_intake_coverage(profile)

    assert coverage.required_missing == []
    assert not coverage.can_summarize
    assert coverage.open_optional_slots[0] == "2.3"
    assert coverage.recommended_slot == "2.3"


def test_consent_is_requested_after_pre_consent_survey():
    session = create_session()
    session.skipped_slots.extend([
        "2.3", "2.4", "2.5", "2.6",
        "3.1", "3.2", "3.3", "3.4", "3.5",
    ])
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công và thương mại",
    )

    coverage = compute_intake_coverage(profile, session=session)

    assert coverage.recommended_focus == "brandkit_consent"
    assert coverage.recommended_slot == "4.0"
    assert not coverage.can_summarize


def test_coverage_can_summarize_after_optional_topics_are_answered_or_skipped():
    session = create_session()
    session.skipped_slots.extend([
        "2.3", "2.4", "2.5", "2.6",
        "3.1", "3.2", "3.3", "3.4", "3.5", "4.2",
    ])
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công và thương mại",
        brandkit_consent="yes",
        logo_initials="auto",
        slogan_preference="auto",
        logo_style="auto",
    )

    coverage = compute_intake_coverage(profile, session=session)

    assert coverage.required_missing == []
    assert coverage.open_optional_slots == []
    assert coverage.can_summarize
    assert coverage.recommended_focus is None


def test_field_to_slot_is_debug_pointer_only():
    assert field_to_slot("phone_or_zalo") == "1.3"
    assert field_to_slot("zalo") == "2.5"
    assert field_to_slot("unknown") is None


def test_branding_questions_follow_color_before_summary():
    session = create_session()
    session.skipped_slots.extend([
        "2.3", "2.4", "2.5", "2.6",
        "3.1", "3.2", "3.3", "3.4", "3.5", "4.2",
    ])
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công",
        brandkit_consent="yes",
    )

    coverage = compute_intake_coverage(profile, session=session)

    assert coverage.open_branding_fields == [
        "logo_initials",
        "slogan_preference",
        "logo_style",
    ]
    assert coverage.recommended_slot == "4.3"
    assert not coverage.can_summarize


def test_supplier_slot_stays_open_until_segment_and_backup_are_collected():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công",
        est_team_size=5,
        team_stability_signal="đội cơ hữu",
        supplier_brands=["Xingfa"],
    )

    coverage = compute_intake_coverage(profile)

    assert coverage.recommended_slot == "2.4"
    assert coverage.recommended_focus == "customer_segment_signal"
    assert "2.4" in coverage.open_optional_slots


def test_facebook_slot_stays_open_until_marketing_and_network_are_collected():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công",
        est_team_size=5,
        team_stability_signal="đội cơ hữu",
        supplier_brands=["Xingfa"],
        customer_segment_signal="nhà dân",
        supplier_negotiation_signal="có nguồn backup",
        primary_contact_channel="Zalo",
        facebook="có fanpage",
    )

    coverage = compute_intake_coverage(profile)

    assert coverage.recommended_slot == "2.6"
    assert coverage.recommended_focus == "fb_marketing_status"
    assert "2.6" in coverage.open_optional_slots


def test_customer_pain_resolves_slot_without_forcing_mining_fields():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Solar Hùng Phát",
        address="Gia Lâm",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm Xingfa",
        business_model_signal="thi công",
        est_team_size=5,
        team_stability_signal="đội cơ hữu",
        supplier_brands=["Xingfa"],
        customer_segment_signal="nhà dân",
        supplier_negotiation_signal="có nguồn backup",
        primary_contact_channel="Zalo",
        facebook="có fanpage",
        fb_marketing_status="post tự nhiên",
        community_network_signal="có thợ quen giới thiệu",
        customer_old_percentage="50%",
        customer_storage_method="Zalo",
        customer_pain="khó chăm khách cũ",
    )

    coverage = compute_intake_coverage(profile)

    assert "3.3" not in coverage.open_optional_slots
    assert coverage.recommended_slot == "3.4"
