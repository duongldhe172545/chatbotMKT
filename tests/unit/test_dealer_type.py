"""Test dealer_type detection — F2A.6.

Refer:
- LUAT_2A_core § F2A.6 — detect tại turn 3/8/13, 4 dimension
- KICH_BAN_1B_tone § 2 — 4 nhóm dealer
"""
from __future__ import annotations

from app.core.dealer_type import (
    DETECT_AT_TURNS,
    HIGH_THRESH_SWITCH,
    MIN_CONFIDENCE_SCORE,
    detect_dealer_type,
    get_score_breakdown,
    should_detect_now,
)
from app.core.session import create_session
from app.models.enums import DealerType


# ============================================================
# Score breakdown — kiểm regex pattern cho từng tone
# ============================================================


class TestScoreLuaLo:
    def test_profanity_scored(self):
        scores = get_score_breakdown(["đm em hỏi nhiều thế"])
        assert scores["lua_lo"] >= 2.0

    def test_caps_lock_scored(self):
        scores = get_score_breakdown(["TÊN HÙNG BẮC NINH"])
        assert scores["lua_lo"] >= 1.0

    def test_normal_message_zero(self):
        scores = get_score_breakdown(["Dạ anh tên Tùng"])
        assert scores["lua_lo"] == 0

    def test_combo_caps_chui_high(self):
        """Caps + chửi + cụt câu = signal mạnh."""
        scores = get_score_breakdown([
            "ANH TÊN HÙNG ĐM EM HỎI NHIỀU THẾ",
            "BẮC NINH RỒI",
            "ĐÉO BIẾT ZALO",
        ])
        assert scores["lua_lo"] >= HIGH_THRESH_SWITCH


class TestScoreKhoe:
    def test_boast_phrase_scored(self):
        scores = get_score_breakdown(["anh đứng đầu Bắc Ninh ngành nhôm hệ"])
        assert scores["khoe"] >= 1.0

    def test_numeric_with_boast_scored(self):
        scores = get_score_breakdown([
            "đội anh có 12 thợ gắn bó 5 năm"
        ])
        assert scores["khoe"] >= 2.0

    def test_numeric_without_boast_low(self):
        """Số liệu trả lời slot 3.1 không phải khoe."""
        scores = get_score_breakdown(["60-70%"])
        # KHÔNG có boast phrase → score thấp
        assert scores["khoe"] < 2.0

    def test_long_message_with_emoji(self):
        msg = (
            "Anh là Hùng, cửa hàng Nhôm Kính Thanh Tùng đứng đầu Bắc Ninh "
            "suốt 8 năm rồi em ạ 💪✨🎉"
        )
        scores = get_score_breakdown([msg])
        assert scores["khoe"] >= 3.0


class TestScoreLo:
    def test_defensive_marker_scored_high(self):
        scores = get_score_breakdown(["em là ai? bot à?"])
        assert scores["lo"] >= 3.0

    def test_phi_scared_scored(self):
        scores = get_score_breakdown(["có phí ẩn không em"])
        assert scores["lo"] >= 3.0

    def test_an_toan_scored(self):
        scores = get_score_breakdown(["có an toàn không"])
        assert scores["lo"] >= 3.0

    def test_normal_message_zero(self):
        scores = get_score_breakdown(["Dạ anh tên Tùng"])
        assert scores["lo"] == 0


class TestScoreBan:
    def test_short_messages_scored(self):
        scores = get_score_breakdown(["Tùng", "Cao Bằng", "0912345678"])
        # 3 message ngắn ≤5 từ → ≥ 3.0 + bonus
        assert scores["ban"] >= 3.0

    def test_long_messages_not_ban(self):
        scores = get_score_breakdown([
            "Anh tên Tùng cửa hàng Nhôm Kính Thanh Tùng tại quận 1 TP.HCM"
        ])
        assert scores["ban"] == 0


# ============================================================
# detect_dealer_type — main function
# ============================================================


class TestDetectDealerType:
    def test_detect_at_turn_3_only(self):
        """Chỉ detect tại turn 3/8/13."""
        session = create_session()
        session.turn_count = 2
        result = detect_dealer_type(session, user_messages=["abc"])
        # turn ≠ 3/8/13 → giữ nguyên (UNKNOWN)
        assert result == DealerType.UNKNOWN
        assert len(session.dealer_type_history) == 0

    def test_detect_at_turn_3_short_messages_ban(self):
        """3 message ngắn → BẬN."""
        session = create_session()
        session.turn_count = 3
        result = detect_dealer_type(
            session,
            user_messages=["Tùng", "Cao Bằng", "0912345678"],
        )
        assert result == DealerType.BAN
        assert len(session.dealer_type_history) == 1
        assert session.dealer_type_history[0].turn == 3
        assert session.dealer_type_history[0].type == DealerType.BAN

    def test_detect_lua_lo_caps_chui(self):
        session = create_session()
        session.turn_count = 3
        result = detect_dealer_type(
            session,
            user_messages=[
                "ANH TÊN HÙNG ĐM EM HỎI NHIỀU THẾ",
                "BẮC NINH RỒI",
                "ĐÉO BIẾT ZALO",
            ],
        )
        assert result == DealerType.LUA_LO

    def test_detect_khoe_boast_numeric(self):
        session = create_session()
        session.turn_count = 3
        result = detect_dealer_type(
            session,
            user_messages=[
                "Anh là Hùng, cửa hàng Nhôm Kính Thanh Tùng đứng đầu Bắc Ninh suốt 8 năm rồi em ạ 💪",
                "Đội anh có 12 thợ gắn bó hơn 5 năm, anh đào tạo từng đứa",
            ],
        )
        assert result == DealerType.KHOE

    def test_detect_lo_defensive(self):
        session = create_session()
        session.turn_count = 3
        result = detect_dealer_type(
            session,
            user_messages=[
                "Em là ai? Bot à?",
                "Có an toàn không em",
                "Có phí ẩn không",
            ],
        )
        assert result == DealerType.LO

    def test_detect_low_confidence_defaults_ban(self):
        """Score thấp → BAN (default conservative)."""
        session = create_session()
        session.turn_count = 3
        # Empty messages
        result = detect_dealer_type(session, user_messages=["", "ok"])
        # Empty + 1 short → score thấp
        assert result == DealerType.BAN

    def test_re_detect_keeps_type_if_low_confidence(self):
        """Turn 8: nếu confidence thấp, giữ type cũ."""
        session = create_session()
        session.detected_dealer_type = DealerType.KHOE
        session.turn_count = 8
        # Messages mới — tone bình thường, không Lua_Lo nổi bật
        result = detect_dealer_type(
            session,
            user_messages=["Tùng", "Cao Bằng"],
        )
        # Score thấp → giữ KHOE
        assert result == DealerType.KHOE

    def test_re_detect_switches_if_high_confidence(self):
        """Turn 8: nếu confidence cao, dời sang type mới."""
        session = create_session()
        session.detected_dealer_type = DealerType.BAN
        session.turn_count = 8
        # Strong lua_lo signals
        result = detect_dealer_type(
            session,
            user_messages=[
                "ĐM EM HỎI LẮM CMM",
                "ĐÉO BIẾT ĐÉO HIỂU",
                "TAO BẬN ĐM",
            ],
        )
        assert result == DealerType.LUA_LO

    def test_history_appends_per_detect(self):
        """Mỗi lần detect chạy → append 1 entry."""
        session = create_session()
        session.turn_count = 3
        detect_dealer_type(session, user_messages=["Tùng"])
        session.turn_count = 8
        detect_dealer_type(session, user_messages=["Tùng", "Cao Bằng"])
        assert len(session.dealer_type_history) == 2
        assert session.dealer_type_history[0].turn == 3
        assert session.dealer_type_history[1].turn == 8


# ============================================================
# Helpers
# ============================================================


class TestShouldDetectNow:
    def test_detect_turns(self):
        for t in DETECT_AT_TURNS:
            assert should_detect_now(t) is True

    def test_non_detect_turns(self):
        for t in [1, 2, 4, 5, 6, 7, 9, 10, 14, 15, 100]:
            assert should_detect_now(t) is False
