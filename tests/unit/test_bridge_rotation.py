"""Test bridge phrase rotation — 1A § 2.2.

Refer:
- File 1A § 2.2 — pool 11 + no-bridge ~1/12
- feedback_test_form — test multi-turn để verify rotation, không chỉ 1 turn
"""
from __future__ import annotations

import random

import pytest

from app.core.bridge_rotation import (
    BRIDGE_POOL,
    MAX_RECENT_BRIDGES,
    NO_BRIDGE_PROBABILITY,
    detect_bridge_in_reply,
    get_avoid_hint,
    pick_unused_bridge,
    record_bridge,
    reset_bridges,
)
from app.models.schema import SessionState


def _make_session() -> SessionState:
    """Minimal session cho test."""
    return SessionState(session_id="test-bridge-001")


class TestDetectBridgeInReply:
    @pytest.mark.parametrize("reply,expected", [
        ("Dạ em note. À cho em hỏi địa chỉ ạ?", "À cho em hỏi"),
        ("Em hỏi thêm xíu — bên mình có xưởng không?", "Em hỏi thêm xíu"),
        ("Tiện đây em hỏi luôn nhé?", "Tiện đây em hỏi"),
        ("Em tò mò xíu, anh kinh doanh lâu chưa?", "Em tò mò xíu"),
        ("À mà anh ơi, cho em xin Zalo nha?", "À mà anh ơi"),
    ])
    def test_match_each_bridge(self, reply, expected):
        assert detect_bridge_in_reply(reply) == expected

    def test_no_bridge_returns_none(self):
        """Reply không có bridge → None."""
        assert detect_bridge_in_reply("Dạ em note rồi ạ.") is None
        assert detect_bridge_in_reply("Anh ơi, cho em xin số nhé?") is None

    def test_empty_returns_none(self):
        assert detect_bridge_in_reply("") is None
        assert detect_bridge_in_reply(None) is None

    def test_case_insensitive_match(self):
        """ADVERSARIAL: bridge lowercase trong reply vẫn match."""
        assert detect_bridge_in_reply("dạ à cho em hỏi nhé?") is not None

    def test_longest_match_first(self):
        """ADVERSARIAL: 'Em hỏi thêm cái này' và 'Em hỏi thêm xíu' overlap prefix
        'Em hỏi thêm' → longest match first → 'Em hỏi thêm cái này'.
        """
        result = detect_bridge_in_reply("Em hỏi thêm cái này anh ạ?")
        assert result == "Em hỏi thêm cái này"


class TestRecordBridge:
    def test_record_first_bridge(self):
        s = _make_session()
        assert s.recent_bridges == []
        bridge = record_bridge(s, "À cho em hỏi địa chỉ?")
        assert bridge == "À cho em hỏi"
        assert s.recent_bridges == ["À cho em hỏi"]

    def test_record_lru_max_3(self):
        """ADVERSARIAL: > 3 bridge → giữ 3 mới nhất."""
        s = _make_session()
        record_bridge(s, "À cho em hỏi địa chỉ?")
        record_bridge(s, "Em hỏi thêm xíu nha?")
        record_bridge(s, "Tiện đây em hỏi nhé?")
        record_bridge(s, "À mà anh ơi cho em hỏi?")
        assert len(s.recent_bridges) == MAX_RECENT_BRIDGES
        # Newest first
        assert s.recent_bridges[0] == "À mà anh ơi"

    def test_record_duplicate_moves_to_head(self):
        """ADVERSARIAL: dùng lại bridge cũ → move to head, không duplicate."""
        s = _make_session()
        record_bridge(s, "À cho em hỏi A?")
        record_bridge(s, "Em hỏi thêm xíu B?")
        record_bridge(s, "À cho em hỏi C?")  # re-use
        assert len(s.recent_bridges) == 2
        assert s.recent_bridges[0] == "À cho em hỏi"

    def test_no_bridge_in_reply_returns_none(self):
        s = _make_session()
        bridge = record_bridge(s, "Dạ em note ạ.")
        assert bridge is None
        assert s.recent_bridges == []


class TestGetAvoidHint:
    def test_empty_when_no_recent(self):
        s = _make_session()
        assert get_avoid_hint(s) == ""

    def test_lists_recent_bridges(self):
        s = _make_session()
        record_bridge(s, "À cho em hỏi A?")
        record_bridge(s, "Em hỏi thêm xíu B?")
        hint = get_avoid_hint(s)
        assert "À cho em hỏi" in hint
        assert "Em hỏi thêm xíu" in hint
        assert "TRÁNH" in hint or "tránh" in hint.lower()


class TestPickUnusedBridge:
    def test_avoid_recent(self):
        """ADVERSARIAL: recent 3 bridge → pick từ 8 còn lại."""
        s = _make_session()
        s.recent_bridges = ["À cho em hỏi", "Em hỏi thêm xíu", "Tiện đây em hỏi"]
        # Seed để skip no-bridge branch
        rng = random.Random(42)
        # Loop pick nhiều lần — tất cả phải ≠ recent
        for _ in range(20):
            bridge = pick_unused_bridge(s, rng=rng)
            if bridge is not None:
                assert bridge not in s.recent_bridges

    def test_pool_exhausted_returns_none(self):
        """ADVERSARIAL: recent chứa tất cả 11 bridge → fallback no-bridge."""
        s = _make_session()
        s.recent_bridges = list(BRIDGE_POOL)  # spec ko allow nhưng test guard
        rng = random.Random(1)
        bridge = pick_unused_bridge(s, rng=rng)
        assert bridge is None

    def test_no_bridge_probability(self):
        """ADVERSARIAL: rng.random() < NO_BRIDGE_PROBABILITY → None."""
        s = _make_session()
        # Force no-bridge branch
        class _FakeRng:
            def random(self):
                return 0.01  # < 1/12

            def choice(self, seq):  # pragma: no cover
                return seq[0]

        bridge = pick_unused_bridge(s, rng=_FakeRng())
        assert bridge is None


class TestResetBridges:
    def test_clears_recent(self):
        s = _make_session()
        s.recent_bridges = ["a", "b", "c"]
        reset_bridges(s)
        assert s.recent_bridges == []


class TestMultiTurnRotation:
    """Test luồng multi-turn — bridge không lặp trong 3 turn liên tiếp."""

    def test_3_turn_no_repeat(self):
        """ADVERSARIAL: 3 turn liên tiếp → 3 bridge khác nhau."""
        s = _make_session()
        rng = random.Random(0)
        picked: list[str] = []
        for _ in range(3):
            b = pick_unused_bridge(s, rng=rng)
            if b is None:
                # Skip no-bridge turn (đôi khi gặp do random)
                continue
            picked.append(b)
            # Simulate engine dùng bridge → record
            record_bridge(s, f"{b} ...?")
        # 3 bridge picked phải đôi một khác nhau
        if len(picked) >= 2:
            assert len(set(picked)) == len(picked)

    def test_recent_bridges_persists_across_turns(self):
        """Bridge tracked qua nhiều turn — old bridge fall off khi đủ 3 new."""
        s = _make_session()
        # 5 turn: 5 bridge khác nhau → recent giữ 3 mới nhất
        for bridge in BRIDGE_POOL[:5]:
            record_bridge(s, f"{bridge} ...?")
        assert len(s.recent_bridges) == 3
        # 3 bridge mới nhất theo thứ tự reverse
        assert s.recent_bridges == [BRIDGE_POOL[4], BRIDGE_POOL[3], BRIDGE_POOL[2]]
