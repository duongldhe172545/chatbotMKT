"""Test stage transitions — forward-only. Refer F2A.1 + D2 STRATEGY."""
from __future__ import annotations

from app.core.stages import (
    STAGE_TRANSITIONS,
    get_allowed_transitions,
    is_valid_transition,
)
from app.models.enums import Stage


class TestForwardTransitions:
    """4 forward transition hợp lệ."""

    def test_greeting_to_asking(self):
        """Happy path: dealer ack greeting → ASKING."""
        assert is_valid_transition(Stage.GREETING, Stage.ASKING)

    def test_greeting_to_done(self):
        """Edge case: dealer từ chối ngay greeting → DONE soft-close."""
        assert is_valid_transition(Stage.GREETING, Stage.DONE)

    def test_asking_to_confirming(self):
        """Happy path: thu đủ slot → CONFIRMING."""
        assert is_valid_transition(Stage.ASKING, Stage.CONFIRMING)

    def test_asking_to_done(self):
        """Edge case: timeout / escalation L3 → DONE từ ASKING."""
        assert is_valid_transition(Stage.ASKING, Stage.DONE)

    def test_confirming_to_done(self):
        """Happy path: dealer confirm/edit → DONE."""
        assert is_valid_transition(Stage.CONFIRMING, Stage.DONE)


class TestBackwardTransitionRejected:
    """Forward-only: không cho back. Refer D2 STRATEGY."""

    def test_no_asking_to_greeting(self):
        assert not is_valid_transition(Stage.ASKING, Stage.GREETING)

    def test_no_confirming_to_asking(self):
        """Sửa data sai ở CONFIRMING không quay về ASKING — dùng edit_parser."""
        assert not is_valid_transition(Stage.CONFIRMING, Stage.ASKING)

    def test_no_confirming_to_greeting(self):
        assert not is_valid_transition(Stage.CONFIRMING, Stage.GREETING)

    def test_no_done_to_anything(self):
        """DONE = terminal."""
        for to_stage in Stage:
            if to_stage != Stage.DONE:
                assert not is_valid_transition(Stage.DONE, to_stage)


class TestSelfTransitionRejected:
    """Stage → cùng stage không phải transition thật."""

    def test_no_self_transition_any_stage(self):
        for stage in Stage:
            assert not is_valid_transition(stage, stage), \
                f"Self-transition {stage} → {stage} không hợp lệ"


class TestGetAllowedTransitions:
    def test_from_greeting(self):
        allowed = get_allowed_transitions(Stage.GREETING)
        assert allowed == {Stage.ASKING, Stage.DONE}

    def test_from_asking(self):
        allowed = get_allowed_transitions(Stage.ASKING)
        assert allowed == {Stage.CONFIRMING, Stage.DONE}

    def test_from_confirming(self):
        allowed = get_allowed_transitions(Stage.CONFIRMING)
        assert allowed == {Stage.DONE}

    def test_from_done_empty(self):
        """Terminal — không transition."""
        assert get_allowed_transitions(Stage.DONE) == set()


class TestTransitionTableIntegrity:
    """STAGE_TRANSITIONS có đủ 4 stage làm key."""

    def test_all_stages_in_table(self):
        for stage in Stage:
            assert stage in STAGE_TRANSITIONS

    def test_no_invalid_target_in_table(self):
        """Mọi target trong table phải là Stage hợp lệ."""
        for from_stage, targets in STAGE_TRANSITIONS.items():
            for to in targets:
                assert isinstance(to, Stage)
