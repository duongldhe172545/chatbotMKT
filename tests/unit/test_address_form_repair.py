from __future__ import annotations

from app.core.address_form import repair_named_address_form


def test_repairs_bare_owner_vocative():
    assert repair_named_address_form(
        "Dương ơi, em gửi mẫu nhé.",
        owner_name="Lê Dương",
        address_form="anh",
    ) == "Anh Dương ơi, em gửi mẫu nhé."


def test_normalizes_duplicate_honorific():
    assert repair_named_address_form(
        "Em chuyên hỗ trợ các anh anh làm cửa.",
        address_form="anh",
    ) == "Em chuyên hỗ trợ các anh làm cửa."


def test_repairs_bare_owner_sentence_opener():
    assert repair_named_address_form(
        "Cường vui tính quá! Anh cho em xin số Zalo nhé.",
        owner_name="Cường",
        address_form="anh",
    ) == "Anh Cường vui tính quá! Anh cho em xin số Zalo nhé."


def test_does_not_prefix_owner_substring_inside_shop_name():
    assert repair_named_address_form(
        "Cường Vinh có đội thợ riêng không anh?",
        owner_name="Cường",
        address_form="anh",
    ) == "Cường Vinh có đội thợ riêng không anh?"
