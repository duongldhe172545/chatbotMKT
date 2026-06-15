"""Fix 2026-06-11 — đồng bộ workflow ↔ LLM (gói A-E từ bug test thật).

Bug gốc: workflow KẸT vì objective chỉ check field chính, trong khi câu trả lời
rơi vào field signal anh em (motivation_signal thay customer_pain) → không tới
được review/handoff → card không hiện + handoff bịa.
"""
from __future__ import annotations

from app.core.config_v2 import reset_settings
from app.db.connection import Database
from app.db.store import Store
from app.parlant.context_builder import _task_from_objective
from app.parlant.turn_processor import _has_premature_closing
from app.parlant.workflow_engine import (
    OPTIONAL_FIELDS_PRIORITY,
    WorkflowEngine,
    optional_satisfied,
)
from app.services.chat_service import ChatService

try:
    from app.core.config_v2 import Settings
except Exception:  # pragma: no cover
    Settings = None


# ============================================================
# A — optional_satisfied: field signal anh em thoả mãn slot
# ============================================================


class TestOptionalSatisfied:
    def test_sibling_signal_satisfies(self):
        assert optional_satisfied("customer_pain", {"motivation_signal": "thêm khách"}, [])
        assert optional_satisfied("facebook", {"community_network_signal": "nhóm thợ"}, [])
        assert optional_satisfied("supplier_brands", {"supplier_negotiation_signal": "2 nguồn"}, [])

    def test_c6_is_standalone_not_sibling_of_c1(self):
        # C6 giờ hỏi riêng → local_dominance KHÔNG còn thoả mãn slot C1
        assert not optional_satisfied("customer_old_percentage", {"local_dominance_signal": "x"}, [])
        # và C6 tự nó là 1 optional probe
        assert any(f == "local_dominance_signal" for f, _l, _h in OPTIONAL_FIELDS_PRIORITY)

    def test_primary_or_skip_satisfies(self):
        assert optional_satisfied("customer_pain", {"customer_pain": "x"}, [])
        assert optional_satisfied("customer_pain", {}, ["customer_pain"])

    def test_unsatisfied_when_empty(self):
        assert not optional_satisfied("customer_pain", {}, [])
        assert not optional_satisfied("customer_old_percentage", {}, [])


def _snapshot(**all_fields):
    return {
        "all_fields": dict(all_fields),
        "missing_required_fields": [],
        "skipped_fields": [],
        "blocking_flags": [],
        "review_status": "DRAFT",
        "logo_issued_status": "NONE",
    }


def _required_done():
    return {
        "owner_name": "A", "dealer_name": "B", "address": "HN",
        "phone_or_zalo": "0912345678", "main_product": "nhôm",
        "business_model_signal": "xưởng",
    }


class TestNoStuckOnPain:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def _all_optional_via_signal(self):
        af = _required_done()
        # mọi optional có giá trị, RIÊNG customer_pain rỗng nhưng motivation_signal có
        for f, _l, _h in OPTIONAL_FIELDS_PRIORITY:
            if f != "customer_pain":
                af[f] = "x"
        af["motivation_signal"] = "thêm khách"  # thoả mãn slot 3.3 thay customer_pain
        return af

    def test_advances_past_pain_to_consent(self):
        snap = _snapshot(**self._all_optional_via_signal())
        obj = self.engine.compute_objective(profile_snapshot=snap, observations={}, turn_count=30)
        assert obj.get("target_field") != "customer_pain", "VẪN kẹt ở customer_pain!"
        assert obj.get("target_field") == "brandkit_consent"

    def test_workflow_ready_despite_empty_pain(self):
        af = self._all_optional_via_signal()
        af.update({"brandkit_consent": "yes", "color_accent": "auto",
                   "logo_style": "auto", "slogan_preference": "auto"})
        snap = _snapshot(**af)
        assert self.engine.compute_workflow_state(snap) == "READY_FOR_REVIEW"


# ============================================================
# C — guard chốt-sớm bắt handoff bịa
# ============================================================


class TestPrematureGuard:
    # 7.6 (2026-06-12): guard THU GỌN còn lõi link/đã-đủ. 6 marker hành vi đã BỎ
    # vì bắt nhầm câu tử tế → các câu dưới giờ KHÔNG còn bị gắn cờ.

    def test_design_team_no_longer_flagged(self):
        # "đội ngũ thiết kế" / "bắt tay vào làm" đã bỏ — câu giới thiệu tử tế không bị bắt
        assert not _has_premature_closing("đội ngũ thiết kế sẽ làm mẫu riêng cho anh nhé")

    def test_connect_via_zalo_no_longer_flagged(self):
        # "kết bạn qua zalo / zalo theo số" đã bỏ — câu hẹn gửi mẫu không bị bắt
        assert not _has_premature_closing("Em sẽ kết nối qua Zalo để gửi mẫu cho anh xem nhé")

    def test_catches_real_link_and_done_markers(self):
        # Lõi giữ lại VẪN bắt: link Zalo thật + tuyên bố "đã đủ thông tin"
        assert _has_premature_closing("em gửi link Zalo cho anh")
        assert _has_premature_closing("anh vào zalo.me/g/abc nhé")
        assert _has_premature_closing("em đã thu thập đủ thông tin rồi")
        assert _has_premature_closing("Dạ em đã đủ thông tin cần thiết rồi ạ")

    def test_normal_question_not_flagged(self):
        assert not _has_premature_closing("Dạ em hiểu rồi, anh cho em hỏi đội thợ mình mấy người ạ?")
        assert not _has_premature_closing("Màu xanh rất hợp ngành mình, anh thích phong cách nào ạ?")


# ============================================================
# D — zalo handoff: không bịa số / không dùng SĐT khách
# ============================================================


class TestZaloHandoff:
    def test_no_url_forbids_inventing_number(self, monkeypatch):
        monkeypatch.delenv("ZALO_GROUP_URL", raising=False)
        reset_settings()
        try:
            task = _task_from_objective({"type": "zalo_handoff"}, "anh")
            assert "KHÔNG bịa" in task
            assert "số điện thoại của khách" in task
        finally:
            reset_settings()

    def test_with_url_uses_link_and_forbids_phone(self, monkeypatch):
        monkeypatch.setenv("ZALO_GROUP_URL", "https://zalo.me/g/abc123")
        reset_settings()
        try:
            task = _task_from_objective({"type": "zalo_handoff"}, "anh")
            assert "https://zalo.me/g/abc123" in task
            assert "KHÔNG dùng số điện thoại của khách" in task
        finally:
            reset_settings()


# ============================================================
# B — auto-skip optional khi kẹt >= 3 lượt
# ============================================================


def test_auto_skip_after_stuck(tmp_path):
    db = Database(str(tmp_path / "b.sqlite3"))
    db.initialize()
    store = Store(db)
    settings = Settings(database_url="sqlite:///x", conversation_runtime="stub", gemini_api_key="")
    svc = ChatService(store=store, settings=settings)
    _ = svc.turn_processor  # warm

    with db.transaction() as conn:
        sid = store.create_session(
            conn, channel="web", token_hash="t", ip_hash=None,
            user_agent_hash=None, metadata={},
        )["id"]
        pid = store.get_or_create_profile(conn, sid)["id"]
        for fn, val in [
            ("owner_name", "A"), ("dealer_name", "B"), ("address", "HN"),
            ("phone_or_zalo", "0912345678"), ("main_product", "nhôm"),
            ("business_model_signal", "xưởng"), ("est_team_size", "4"),
            ("supplier_brands", "Xingfa"), ("primary_contact_channel", "zalo"),
            ("facebook", "không"),
        ]:
            store.upsert_profile_field(
                conn, profile_id=pid, field_name=fn, raw_value=val,
                normalized_value=val, status="PROVIDED", source_type="extraction",
                confidence=1.0, evidence_message_ids=[],
            )
        # 3 lượt trước đều nhắm customer_old_percentage mà chưa thu
        for i in range(3):
            um = store.insert_message(
                conn, session_id=sid, source="user", message_type="text", text=f"x{i}"
            )
            store.create_turn(
                conn, session_id=sid, user_message_id=um["id"], profile_id=pid,
                active_rules_version="v2", backend_turn_trace={}, profile_snapshot={},
                suggested_objective={"type": "collect_optional_field", "target_field": "customer_old_percentage"},
                observations=[], matched_guideline_ids=[], field_status_summary={},
                model_id="stub", backend_latency_ms=1, turn_aggregation_latency_ms=1,
                final_reply_hash="x",
            )

    # Lượt 4 vẫn lạc đề → customer_old_percentage phải bị auto-skip
    svc.send_text_message(session_id=sid, text="trời mưa quá", client_message_id="m4")

    with db.transaction() as conn:
        row = conn.execute(
            "SELECT status, raw_value FROM profile_fields WHERE profile_id=? AND field_name='customer_old_percentage'",
            (pid,),
        ).fetchone()
    assert row is not None and row["status"] == "SKIPPED", "auto-skip không kích hoạt sau 3 lượt kẹt"
    # #3: câu khách nói lúc skip được lưu để admin xem
    assert row["raw_value"] == "trời mưa quá"


# ============================================================
# #1 — validator chặn placeholder rác (C5 "none")
# ============================================================


class TestPlaceholderReject:
    def test_rejects_english_placeholder(self):
        from app.llm.extractors.validators import validate_free_text

        for junk in ("none", "None", "NULL", "n/a", "N/A", "undefined", "-", "nil"):
            ok, _ = validate_free_text(junk)
            assert not ok, f"{junk!r} phải bị loại"

    def test_accepts_vietnamese_negation(self):
        from app.llm.extractors.validators import validate_free_text

        ok, val = validate_free_text("không có khó khăn rõ rệt")
        assert ok and val == "không có khó khăn rõ rệt"
        ok2, _ = validate_free_text("không biết")  # tiếng Việt vẫn là dữ liệu hợp lệ
        assert ok2


# ============================================================
# Fix 1 — mỗi hint là 1 câu hỏi (bỏ vế "và Y")
# ============================================================


class TestSingleQuestionHints:
    def _h(self, field):
        for f, _l, h in OPTIONAL_FIELDS_PRIORITY:
            if f == field:
                return h
        raise AssertionError(field)

    def test_facebook_dropped_network_clause(self):
        assert "giới thiệu" not in self._h("facebook")

    def test_customer_old_dropped_ownership_clause(self):
        h = self._h("customer_old_percentage")
        assert "lưu" not in h and "tệp" not in h

    def test_supplier_dropped_negotiation_clause(self):
        h = self._h("supplier_brands")
        assert "đàm phán" not in h and "đổi hãng" not in h

    def test_no_hint_has_double_clause(self):
        for f, _l, h in OPTIONAL_FIELDS_PRIORITY:
            assert " — và " not in h, f"{f} vẫn còn 2 vế trong 1 câu"


# ============================================================
# Fix 2 — "tùy em" KHÔNG skip field brandkit (để bot đề xuất), nhưng VẪN skip field thường
# ============================================================


def _session_with_prev_objective(tmp_path, name, target_field):
    db = Database(str(tmp_path / name))
    db.initialize()
    store = Store(db)
    settings = Settings(database_url="sqlite:///x", conversation_runtime="stub", gemini_api_key="")
    svc = ChatService(store=store, settings=settings)
    _ = svc.turn_processor
    with db.transaction() as conn:
        sid = store.create_session(
            conn, channel="web", token_hash="t", ip_hash=None,
            user_agent_hash=None, metadata={},
        )["id"]
        pid = store.get_or_create_profile(conn, sid)["id"]
        um = store.insert_message(conn, session_id=sid, source="user", message_type="text", text="x")
        store.create_turn(
            conn, session_id=sid, user_message_id=um["id"], profile_id=pid,
            active_rules_version="v2", backend_turn_trace={}, profile_snapshot={},
            suggested_objective={"type": "collect_optional_field", "target_field": target_field},
            observations=[], matched_guideline_ids=[], field_status_summary={},
            model_id="stub", backend_latency_ms=1, turn_aggregation_latency_ms=1,
            final_reply_hash="x",
        )
    return svc, store, db, sid, pid


def _status(db, pid, field):
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT status FROM profile_fields WHERE profile_id=? AND field_name=?",
            (pid, field),
        ).fetchone()
    return row["status"] if row else None


def test_brandkit_choice_not_skipped_on_tuy_em(tmp_path):
    svc, store, db, sid, pid = _session_with_prev_objective(tmp_path, "bk.sqlite3", "color_accent")
    svc.send_text_message(session_id=sid, text="tùy em", client_message_id="m1")
    # màu KHÔNG bị skip → để bot đề xuất cho khách chọn
    assert _status(db, pid, "color_accent") != "SKIPPED"


def test_normal_field_still_skipped_on_tuy_em(tmp_path):
    # đối chứng: field thường "tùy em" (khong_biet) VẪN skip → chứng tỏ exclusion là riêng brandkit
    svc, store, db, sid, pid = _session_with_prev_objective(tmp_path, "nm.sqlite3", "customer_storage_method")
    svc.send_text_message(session_id=sid, text="tùy em không biết", client_message_id="m1")
    assert _status(db, pid, "customer_storage_method") == "SKIPPED"


def test_brandkit_invented_value_stripped_on_tuy_em(tmp_path):
    # Guard cứng: dù extractor TỰ BỊA màu khi khách "tùy em" → bị strip, không lưu PROVIDED
    svc, store, db, sid, pid = _session_with_prev_objective(tmp_path, "strip.sqlite3", "color_accent")
    real = svc.turn_processor

    class _Spy:
        def process(self, **kw):
            r = real.process(**kw)
            r.extracted_fields["color_accent"] = "xanh dương"  # giả lập LLM bịa
            return r

    svc._turn_processor = _Spy()
    svc.send_text_message(session_id=sid, text="tùy em", client_message_id="m1")
    assert _status(db, pid, "color_accent") != "PROVIDED", "giá trị bịa lúc 'tùy em' phải bị strip"
