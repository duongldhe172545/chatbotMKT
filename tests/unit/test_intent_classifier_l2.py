"""Test Layer 2 intent classifier + PII leak guard — Phase 4 R3."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.session import create_session
from app.llm.intent_classifier import (
    check_pii_leak,
    classify_intent_layer2,
)
from app.models.enums import Intent
from app.models.schema import DealerProfileRaw
from app.storage.sqlite_store import SQLiteStore


def _mock_client(intent_str: str | None = None, confidence: str = "HIGH"):
    """Mock LLMClient.extract_fast."""
    client = MagicMock()
    if intent_str is None:
        client.extract_fast.return_value = {}
    else:
        client.extract_fast.return_value = {
            "intent": intent_str,
            "confidence": confidence,
        }
    return client


# ============================================================
# classify_intent_layer2
# ============================================================


class TestClassifyIntentLayer2:
    def test_returns_intent_for_valid_label(self):
        client = _mock_client("defensive", "HIGH")
        intent, conf = classify_intent_layer2("em là ai vậy", client)
        assert intent == Intent.DEFENSIVE
        assert conf == "HIGH"

    def test_invalid_enum_returns_none(self):
        """ADVERSARIAL: LLM trả enum lạ → caller giữ NORMAL."""
        client = _mock_client("invalid_enum")
        intent, conf = classify_intent_layer2("hi", client)
        assert intent is None
        assert conf == "LOW"

    def test_llm_fail_returns_none(self):
        client = MagicMock()
        client.extract_fast.side_effect = Exception("API timeout")
        intent, conf = classify_intent_layer2("hi", client)
        assert intent is None
        assert conf == "LOW"

    def test_empty_message(self):
        client = _mock_client()
        intent, conf = classify_intent_layer2("", client)
        assert intent is None

    def test_non_dict_response(self):
        client = MagicMock()
        client.extract_fast.return_value = "not a dict"
        intent, conf = classify_intent_layer2("hi", client)
        assert intent is None

    def test_invalid_confidence_normalized_to_low(self):
        client = _mock_client("normal", "WEIRD_VALUE")
        intent, conf = classify_intent_layer2("hi", client)
        assert intent == Intent.NORMAL
        assert conf == "LOW"  # normalized

    def test_all_7_intents_mapped(self):
        for label, expected in [
            ("affirmative", Intent.AFFIRMATIVE),
            ("refusal", Intent.REFUSAL),
            ("khong_biet", Intent.KHONG_BIET),
            ("defensive", Intent.DEFENSIVE),
            ("tam_su", Intent.TAM_SU),
            ("edit", Intent.EDIT),
            ("normal", Intent.NORMAL),
        ]:
            client = _mock_client(label, "MED")
            # use_cache=False để mỗi label test riêng (cùng "test" message)
            intent, _ = classify_intent_layer2("test", client, use_cache=False)
            assert intent == expected, f"{label} → {expected}"


# ============================================================
# PII leak guard
# ============================================================


@pytest.fixture
def store_with_other_session(tmp_path):
    """Seed 1 session khác để test cross-session leak."""
    db = tmp_path / "test_pii.db"
    store = SQLiteStore(str(db))

    # Session khác — Bob
    other = create_session()
    store.save_session(other)
    profile_other = DealerProfileRaw(
        owner_name="Bob",
        dealer_name="Bob Nhôm Kính",
        phone_or_zalo="0987654321",
        address="999 Nguyễn Huệ Q.1 TP.HCM",
    )
    store.save_profile(other.session_id, profile_other)
    return store, other.session_id


class TestPiiLeak:
    def test_clean_response_no_leak(self, store_with_other_session):
        store, other_sid = store_with_other_session
        # Current session Alice — reply không chứa PII Bob
        leaked = check_pii_leak(
            "Dạ anh tên Alice, em note rồi ạ.",
            current_session_id="alice-session",
            store=store,
        )
        assert leaked == []

    def test_phone_leak_detected(self, store_with_other_session):
        store, other_sid = store_with_other_session
        leaked = check_pii_leak(
            "Dạ số 0987654321 — em note rồi.",
            current_session_id="alice-session",
            store=store,
        )
        assert other_sid in leaked

    def test_dealer_name_leak_detected(self, store_with_other_session):
        store, other_sid = store_with_other_session
        leaked = check_pii_leak(
            "Em thấy Bob Nhôm Kính cũng làm nghề này.",
            current_session_id="alice-session",
            store=store,
        )
        assert other_sid in leaked

    def test_skip_current_session(self, store_with_other_session):
        """ADVERSARIAL: reply chứa PII current session → KHÔNG flag (đó là dealer)."""
        store, other_sid = store_with_other_session
        # Pass current_session_id = other_sid → skip
        leaked = check_pii_leak(
            "Dạ Bob, em note SĐT 0987654321.",
            current_session_id=other_sid,  # KEY: current session = Bob
            store=store,
        )
        assert leaked == []

    def test_short_value_no_false_positive(self, store_with_other_session):
        """ADVERSARIAL: nếu owner_name ngắn (vd "An" 2 char) → skip
        (filter ≥ 4 char tránh false positive 'An' trong "Anh ơi")."""
        store, _ = store_with_other_session
        # Bob owner = "Bob" 3 char → skip check (< 4)
        leaked = check_pii_leak(
            "Bộ thương hiệu cho anh ạ!",
            current_session_id="alice-session",
            store=store,
        )
        # "Bộ" trong reply không match "Bob" (case-sensitive substring) →
        # nhưng nếu match thì sẽ false positive → guard với ≥ 4 char filter
        # đảm bảo Bob (3 char) bị skip
        assert leaked == []

    def test_empty_reply_no_leak(self, store_with_other_session):
        store, _ = store_with_other_session
        assert check_pii_leak("", "alice-session", store) == []

    def test_no_other_sessions_no_leak(self, tmp_path):
        """ADVERSARIAL: DB rỗng → return empty."""
        db = tmp_path / "empty.db"
        store = SQLiteStore(str(db))
        leaked = check_pii_leak("any reply 0987654321", "alice", store)
        assert leaked == []
