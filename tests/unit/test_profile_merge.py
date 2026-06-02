from __future__ import annotations

from app.core.profile_merge import merge_planner_result
from app.models.planner import PlannedFact, PlannerResult
from app.models.schema import DealerProfileRaw


def _result(*facts: PlannedFact, corrections: list[PlannedFact] | None = None):
    return PlannerResult(
        move="continue_intake",
        facts=list(facts),
        corrections=corrections or [],
        assistant_reply="Dạ em ghi nhận rồi ạ.",
    )


def test_merge_fills_empty_scalar_fields():
    profile = DealerProfileRaw()
    summary = merge_planner_result(
        profile,
        _result(
            PlannedFact(field="owner_name", value="Hùng", evidence="Anh tên Hùng", confidence="high"),
            PlannedFact(field="dealer_name", value="Hùng Phát", evidence="cửa hàng Hùng Phát", confidence="high"),
        ),
    )

    assert profile.owner_name == "Hùng"
    assert profile.dealer_name == "Hùng Phát"
    assert summary.applied["owner_name"] == "Hùng"


def test_merge_does_not_overwrite_existing_scalar_without_correction():
    profile = DealerProfileRaw(owner_name="Hùng")
    summary = merge_planner_result(
        profile,
        _result(PlannedFact(field="owner_name", value="Dũng", evidence="Dũng", confidence="high")),
    )

    assert profile.owner_name == "Hùng"
    assert summary.skipped["owner_name"] == "already_filled"


def test_high_confidence_correction_overwrites_scalar():
    profile = DealerProfileRaw(address="Cầu Giấy")
    summary = merge_planner_result(
        profile,
        _result(
            corrections=[
                PlannedFact(
                    field="address",
                    value="Nam Từ Liêm",
                    evidence="không phải Cầu Giấy, là Nam Từ Liêm",
                    confidence="high",
                )
            ]
        ),
    )

    assert profile.address == "Nam Từ Liêm"
    assert summary.applied["address"] == "Nam Từ Liêm"


def test_address_fact_is_not_case_locked_before_derive():
    profile = DealerProfileRaw()
    summary = merge_planner_result(
        profile,
        _result(PlannedFact(field="address", value="Gia Lam", evidence="Gia Lam", confidence="high")),
    )

    assert profile.address == "Gia Lam"
    assert profile.province is None
    assert profile.district is None
    assert summary.applied["address"] == "Gia Lam"


def test_invalid_phone_is_rejected():
    profile = DealerProfileRaw()
    summary = merge_planner_result(
        profile,
        _result(PlannedFact(field="phone_or_zalo", value="abc123", evidence="abc123", confidence="high")),
    )

    assert profile.phone_or_zalo is None
    assert summary.skipped["phone_or_zalo"] == "invalid_value"


def test_list_fields_merge_unique_values():
    profile = DealerProfileRaw(supplier_brands=["Xingfa"])
    summary = merge_planner_result(
        profile,
        _result(
            PlannedFact(
                field="supplier_brands",
                value=["Xingfa", "Austdoor"],
                evidence="Xingfa với Austdoor",
                confidence="high",
            )
        ),
    )

    assert profile.supplier_brands == ["Xingfa", "Austdoor"]
    assert summary.applied["supplier_brands"] == ["Xingfa", "Austdoor"]
