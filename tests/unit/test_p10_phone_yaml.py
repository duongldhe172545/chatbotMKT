"""Phase 10 — SĐT sai không kẹt luồng (10.1) + rules.yaml không duplicate key (10.6) + luật hãng (10.3)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.db.connection import Database
from app.db.store import Store
from app.core.config_v2 import Settings
from app.services.profile_service import ProfileService

CONFIG = Path(__file__).resolve().parents[2] / "config"


# ============================================================
# 10.6 — rules.yaml KHÔNG có duplicate key (slot 2.4/2.6 từng lặp 'rules:')
# ============================================================


def test_rules_yaml_no_duplicate_keys():
    class _DupLoader(yaml.SafeLoader):
        pass

    def _no_dup(loader, node, deep=False):
        mapping = {}
        for k_node, v_node in node.value:
            k = loader.construct_object(k_node, deep=deep)
            if k in mapping:
                raise AssertionError(f"Duplicate key '{k}' trong 1 mapping rules.yaml")
            mapping[k] = loader.construct_object(v_node, deep=deep)
        return mapping

    _DupLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup
    )
    text = (CONFIG / "rules.yaml").read_text(encoding="utf-8")
    yaml.load(text, Loader=_DupLoader)  # raise nếu có key trùng


def test_supplier_slot_keeps_one_question_and_brand_rule():
    from app.core.rules import get_slot_rules
    rules = " ".join(get_slot_rules("2.4"))
    assert "Chỉ hỏi 1 câu" in rules            # luật P4.10 KHÔNG còn bị nuốt
    assert "Austdoor" in rules                  # luật chuẩn hoá tên hãng (10.3)


def test_facebook_slot_keeps_one_question_rule():
    from app.core.rules import get_slot_rules
    assert "Chỉ hỏi 1 câu" in " ".join(get_slot_rules("2.6"))


# ============================================================
# 10.1 — SĐT sai: WARNING (không BLOCKING) + van an toàn
# ============================================================


@pytest.fixture
def svc():
    db = Database(":memory:")
    db.initialize()
    store = Store(db)
    ps = ProfileService(store, Settings(app_env="test", database_url="sqlite:///:memory:"))
    return db, store, ps


def _new_session(db, store):
    with db.transaction() as conn:
        s = store.create_session(conn, channel="web", token_hash="h", ip_hash="i",
                                 user_agent_hash="u", metadata={})
        sid = s["id"]
        pid = store.get_or_create_profile(conn, sid)["id"]
        msg = store.insert_message(conn, session_id=sid, source="user",
                                   message_type="text", text="023941212")
    return sid, pid, msg["id"]


def test_invalid_phone_is_warning_not_blocking(svc):
    db, store, ps = svc
    sid, pid, mid = _new_session(db, store)
    with db.transaction() as conn:
        snap = ps.save_extracted_fields(
            conn, session_id=sid,
            extracted_fields={"phone_or_zalo": "023941212"},  # 9 số → invalid
            evidence_message_id=mid,
        )
        # phone chưa PROVIDED → vẫn missing (workflow sẽ hỏi lại qua collect_required)
        assert "phone_or_zalo" in snap["missing_required_fields"]
        # KHÔNG còn cờ BLOCKING → không cướp luồng sang resolve_blocking_flag
        assert "phone_invalid_after_retry" not in snap["blocking_flags"]
        pf = [f for f in store.get_active_flags(conn, profile_id=pid)
              if f["flag_name"] == "phone_invalid_after_retry"]
        assert pf and pf[0]["severity"] == "WARNING"


def test_phone_van_accepts_after_retries(svc):
    db, store, ps = svc
    sid, pid, mid = _new_session(db, store)
    with db.transaction() as conn:
        snap = ps.save_extracted_fields(
            conn, session_id=sid,
            extracted_fields={"phone_or_zalo": "023941212"},
            evidence_message_id=mid,
            accept_phone_unverified=True,   # chat_service báo đã hỏi đủ N lần
        )
        # nhận TẠM → phone PROVIDED → KHÔNG còn missing → luồng đi tiếp được
        assert "phone_or_zalo" not in snap["missing_required_fields"]
        flags = store.get_active_flags(conn, profile_id=pid)
        assert any(f["flag_name"] == "phone_unverified" for f in flags)
        assert "phone_invalid_after_retry" not in snap["blocking_flags"]


def test_phone_invalid_task_reasks_not_acknowledge():
    from app.parlant.context_builder import _task_from_objective
    obj = {"type": "collect_required_field", "target_field": "phone_or_zalo", "prompt_hint": "SĐT/Zalo"}
    t = _task_from_objective(obj, "anh", phone_invalid=True)
    assert "chưa hợp lệ" in t.lower()
    assert "KHÔNG nói 'đã ghi nhận" in t  # cấm bot nói đã ghi nhận số sai
    # khi không invalid → task thường
    t2 = _task_from_objective(obj, "anh", phone_invalid=False)
    assert "chưa hợp lệ" not in t2.lower()


def test_valid_phone_still_works(svc):
    db, store, ps = svc
    sid, pid, mid = _new_session(db, store)
    with db.transaction() as conn:
        snap = ps.save_extracted_fields(
            conn, session_id=sid,
            extracted_fields={"phone_or_zalo": "0912345678"},
            evidence_message_id=mid,
        )
        assert "phone_or_zalo" not in snap["missing_required_fields"]
