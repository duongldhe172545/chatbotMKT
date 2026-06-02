from __future__ import annotations

from unittest.mock import MagicMock

from app.core._conv_confirming import _handle_edit, handle_confirming, handle_done
from app.core.session import create_session
from app.models.enums import Stage
from app.models.schema import DealerProfileRaw


def test_confirming_rejects_invalid_phone_from_llm_edit_parser():
    session = create_session()
    profile = DealerProfileRaw(phone_or_zalo="0912345678")
    client = MagicMock()
    client.chat_fast.return_value = (
        '{"field":"phone_or_zalo","value":"0134271132123"}'
    )

    reply = _handle_edit(
        session,
        profile,
        "số điện thoại là 0134271132123 cơ",
        client,
    )

    assert profile.phone_or_zalo == "0912345678"
    assert "chưa đúng định dạng" in reply


def test_confirming_smalltalk_does_not_render_card_or_close_session():
    session = create_session()
    session.stage = Stage.CONFIRMING
    client = MagicMock()
    client.chat_quality.return_value = "Em hiểu chuyện gia đình làm anh mệt. Khi tiện anh duyệt hồ sơ giúp em nhé."

    reply = handle_confirming(
        session,
        DealerProfileRaw(owner_name="Dương"),
        "vợ anh chán anh quá làm sao em",
        client,
    )

    assert session.stage == Stage.CONFIRMING
    assert "📋" not in reply
    assert "gia đình" in reply


def test_done_smalltalk_stays_natural_without_repeating_profile():
    session = create_session()
    session.stage = Stage.DONE
    client = MagicMock()
    client.chat_quality.return_value = "Em nghe anh chia sẻ rồi. Chuyện này chắc làm anh buồn nhiều."

    reply = handle_done(
        session=session,
        profile=DealerProfileRaw(owner_name="Dương"),
        message="vợ anh chán anh quá làm sao em",
        client=client,
    )

    assert "hồ sơ" not in reply.lower()
    assert "Zalo" not in reply
    assert "buồn" in reply
