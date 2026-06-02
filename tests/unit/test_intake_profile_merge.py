from __future__ import annotations

from app.core.intake_profile_merge import merge_intake_facts
from app.llm.intake_fact_extractor import IntakeFact, IntakeFacts
from app.models.schema import DealerProfileRaw


def _facts(*facts: IntakeFact) -> IntakeFacts:
    return IntakeFacts(facts=list(facts))


def test_merge_fills_scalars_and_basic_derives():
    profile = DealerProfileRaw()
    summary = merge_intake_facts(
        profile,
        _facts(
            IntakeFact(field="owner_name", value="Hùng", evidence="anh tên Hùng", confidence="high"),
            IntakeFact(field="phone_or_zalo", value="0912 345 678", evidence="0912 345 678", confidence="high"),
        ),
    )

    assert profile.owner_name == "Hùng"
    assert profile.contact_name == "Hùng"
    assert profile.phone_or_zalo == "0912345678"
    assert profile.hotline == "0912345678"
    assert summary.applied["phone_or_zalo"] == "0912345678"


def test_merge_requires_province_before_persisting_address():
    profile = DealerProfileRaw()
    summary = merge_intake_facts(
        profile,
        _facts(IntakeFact(field="address", value="Gia Lam", evidence="o Gia Lam", confidence="high")),
    )

    assert profile.address is None
    assert profile.province is None
    assert profile.district is None
    assert summary.skipped["address"] == "address_needs_province_confirmation"


def test_merge_accepts_address_with_clear_province():
    profile = DealerProfileRaw()
    summary = merge_intake_facts(
        profile,
        _facts(IntakeFact(field="address", value="Gia Lâm, Hà Nội", evidence="Gia Lâm, Hà Nội", confidence="high")),
    )

    assert profile.address == "Gia Lâm, Hà Nội"
    assert profile.province == "Hà Nội"
    assert summary.applied["address"] == "Gia Lâm, Hà Nội"


def test_merge_list_unique_and_reject_invalid_phone():
    profile = DealerProfileRaw(supplier_brands=["Xingfa"])
    summary = merge_intake_facts(
        profile,
        _facts(
            IntakeFact(field="supplier_brands", value="Xingfa, Austdoor", evidence="Xingfa với Austdoor", confidence="high"),
            IntakeFact(field="phone_or_zalo", value="abc123", evidence="abc123", confidence="high"),
        ),
    )

    assert profile.supplier_brands == ["Xingfa", "Austdoor"]
    assert profile.phone_or_zalo is None
    assert summary.skipped["phone_or_zalo"] == "invalid_value"


def test_high_confidence_correction_overwrites_existing_value():
    profile = DealerProfileRaw(dealer_name="Hùng Phát")
    merge_intake_facts(
        profile,
        _facts(
            IntakeFact(
                field="dealer_name",
                value="Solar Hùng Phát",
                evidence="không, là Solar Hùng Phát",
                confidence="high",
                is_correction=True,
            )
        ),
    )

    assert profile.dealer_name == "Solar Hùng Phát"


def test_merge_reuses_legacy_business_type_derive():
    profile = DealerProfileRaw()
    merge_intake_facts(
        profile,
        _facts(
            IntakeFact(
                field="business_model_signal",
                value="phân phối thi công",
                evidence="anh phân phối thi công",
                confidence="high",
            )
        ),
    )

    assert profile.business_model_signal == "phân phối thi công"
    assert profile.dealer_type == "nha_thau_nho"


def test_merge_rejects_unresolved_supplier_reference_placeholder():
    profile = DealerProfileRaw()
    summary = merge_intake_facts(
        profile,
        _facts(
            IntakeFact(
                field="supplier_brands",
                value="2 hãng vật tư đó",
                evidence="anh xài 2 hãng đấy là chính",
                confidence="high",
            )
        ),
    )

    assert profile.supplier_brands == []
    assert summary.skipped["supplier_brands"] == "invalid_value"


def test_merge_normalizes_approximate_team_size_range_to_integer():
    profile = DealerProfileRaw()
    summary = merge_intake_facts(
        profile,
        _facts(
            IntakeFact(
                field="est_team_size",
                value="6-7",
                evidence="anh có 6 7 ông thôi, cao điểm thì thuê thêm",
                confidence="high",
            )
        ),
    )

    assert profile.est_team_size == 6
    assert summary.applied["est_team_size"] == 6
