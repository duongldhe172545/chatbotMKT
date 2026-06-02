from __future__ import annotations

from app.core.missing_fields import compute_missing_fields, field_to_slot
from app.models.schema import DealerProfileRaw


def test_empty_profile_missing_required_in_priority_order():
    state = compute_missing_fields(DealerProfileRaw())

    assert state.required_missing[:4] == [
        "owner_name",
        "dealer_name",
        "address",
        "phone_or_zalo",
    ]
    assert state.next_focus_field == "owner_name"
    assert state.next_focus_slot == "1.1"
    assert state.can_confirm is False


def test_next_focus_skips_filled_required_fields():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Hùng Phát",
        address="Cầu Giấy",
        main_product="cửa nhôm Xingfa",
    )

    state = compute_missing_fields(profile)

    assert "owner_name" not in state.required_missing
    assert "dealer_name" not in state.required_missing
    assert "address" not in state.required_missing
    assert state.next_focus_field == "phone_or_zalo"
    assert state.next_focus_slot == "1.3"


def test_can_confirm_when_required_fields_are_filled():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Hùng Phát",
        address="Cầu Giấy",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm",
        business_model_signal="vừa bán vừa thi công",
        brandkit_consent="yes",
    )

    state = compute_missing_fields(profile)

    assert state.required_missing == []
    assert state.can_confirm is True


def test_derived_fields_are_not_planner_focus():
    profile = DealerProfileRaw(
        owner_name="Hùng",
        dealer_name="Hùng Phát",
        address="Cầu Giấy",
        phone_or_zalo="0912345678",
        main_product="cửa nhôm",
        business_model_signal="vừa bán vừa thi công",
        brandkit_consent="yes",
    )

    state = compute_missing_fields(profile)

    assert "province" not in state.optional_missing
    assert "dealer_type" not in state.optional_missing
    assert field_to_slot("phone_or_zalo") == "1.3"

