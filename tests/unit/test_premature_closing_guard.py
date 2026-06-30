"""Test guard chống đóng sớm — fix bug "xong logo là ngừng hỏi" 2026-06-10.

2 lớp phòng thủ:
1. Prompt: collection status block + rule cấm chốt trong task hint.
2. Post-turn: detect marker chốt sớm → retry → fallback stub.
"""
from __future__ import annotations

from pathlib import Path

from app.parlant.context_builder import ContextBuilder, _build_collection_status, _task_from_objective
from app.parlant.turn_processor import _has_premature_closing
from app.services.serializers import empty_profile_snapshot

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ============================================================
# Marker detection — happy + adversarial
# ============================================================


class TestPrematureClosingMarkers:
    def test_zalo_link_detected(self):
        assert _has_premature_closing("Anh bấm vào link Zalo này nhé: [Link Zalo]")

    def test_zalo_me_url_detected(self):
        assert _has_premature_closing("Kết nối tại https://zalo.me/g/abc123 nhé anh")

    def test_collected_enough_detected(self):
        assert _has_premature_closing("Em đã thu thập đủ thông tin cần thiết rồi ạ.")

    def test_gom_du_detected(self):
        assert _has_premature_closing("Dạ em đã gom đủ thông tin chính rồi ạ.")

    def test_nam_day_du_detected(self):
        assert _has_premature_closing("Mọi thông tin em đã nắm đầy đủ rồi ạ.")

    # ----- Adversarial: câu bridge bình thường KHÔNG được trigger -----

    def test_normal_ask_not_flagged(self):
        assert not _has_premature_closing(
            "Dạ, Zalo đúng là kênh tiện nhất ạ! Anh cho em hỏi thêm về đội thợ nhé?"
        )

    def test_mentioning_zalo_channel_not_flagged(self):
        """Nhắc 'Zalo' như kênh liên hệ (không phải link) → không flag."""
        assert not _has_premature_closing(
            "Anh thường chốt đơn với khách qua Zalo hay gọi điện ạ?"
        )

    def test_bridge_promise_not_flagged(self):
        assert not _has_premature_closing(
            "Để em sớm hoàn thiện hồ sơ và gửi tặng bộ thương hiệu, anh chia sẻ giúp em nhé?"
        )

    def test_empty_reply_not_flagged(self):
        assert not _has_premature_closing("")

    # ----- 7.6: câu gửi-mẫu/giới-thiệu tử tế KHÔNG được bắt nhầm (bug "xem mẫu") -----

    def test_send_sample_via_zalo_not_flagged(self):
        assert not _has_premature_closing(
            "Dạ để em gửi mẫu logo qua Zalo cho anh xem sau khi mình trao đổi xong "
            "nhé, giờ anh cho em xin tên ạ?"
        )

    def test_design_team_mention_not_flagged(self):
        assert not _has_premature_closing(
            "Dạ đội ngũ thiết kế bên em sẽ làm mẫu riêng cho anh, anh cho em xin tên "
            "cửa hàng nhé?"
        )

    def test_connect_via_zalo_to_send_sample_not_flagged(self):
        assert not _has_premature_closing(
            "Dạ em sẽ kết nối qua Zalo để gửi mẫu cho anh xem, trước tiên anh cho em "
            "xin tên nhé?"
        )


# ============================================================
# Collection status block — LLM phải thấy field pending
# ============================================================


class TestCollectionStatus:
    def test_empty_profile_lists_required_pending(self):
        snap = empty_profile_snapshot()
        status = _build_collection_status(snap)
        assert "Còn phải hỏi" in status
        assert "BẮT BUỘC" in status
        # Phase 6: nhắc nhẹ (info) thay cho lệnh "CHƯA ĐƯỢC PHÉP" — chống chốt sớm
        # giờ dựa principle reply + guard post-turn.
        assert "tiếp tục hỏi" in status

    def test_pending_includes_optional_fields(self):
        """Bug gốc: 3.2/3.4/3.5 chưa thu nhưng bot chốt — block phải liệt kê."""
        snap = empty_profile_snapshot()
        snap["all_fields"] = {
            "owner_name": "Huyền",
            "dealer_name": "Huyền Nhôm",
            "address": "Lê Văn Thiêm HN",
            "phone_or_zalo": "0867098021",
            "main_product": "nhôm tủ bếp",
            "business_model_signal": "bán lẻ",
        }
        snap["missing_required_fields"] = []
        snap["skipped_fields"] = []
        status = _build_collection_status(snap)
        assert "Còn phải hỏi" in status
        # các optional chưa thu phải xuất hiện (label mới sau Fix 1)
        assert "lưu thông tin khách" in status
        assert "ký gửi" in status  # C2 label = "tự chủ vốn (ký gửi / mua đứt)"
        assert "bảo hành" in status

    def test_all_collected_allows_closing(self):
        snap = empty_profile_snapshot()
        all_fields = {
            "owner_name": "A", "dealer_name": "B", "address": "C",
            "phone_or_zalo": "0912345678", "main_product": "nhôm",
            "business_model_signal": "xưởng", "est_team_size": 4,
            "supplier_brands": ["Xingfa"], "primary_contact_channel": "zalo",
            "facebook": "fb.com/x", "customer_old_percentage": "70%",
            "local_dominance_signal": "ông trùm khu",
            "customer_storage_method": "sổ", "customer_pain": "giá",
            "payment_terms_signal": "cọc 50%",
            "warranty_responsibility_signal": "5 năm",
            "brandkit_consent": "yes", "color_accent": "xanh",
            "logo_style": "auto", "slogan_preference": "auto",  # P4.4 brandkit đủ
            "brandkit_preview_shown": "yes",  # 9.4b: đã show mẫu → hết bước thu thập
        }
        snap["all_fields"] = all_fields
        snap["missing_required_fields"] = []
        snap["skipped_fields"] = []
        status = _build_collection_status(snap)
        assert "Đã thu xong toàn bộ" in status
        assert "Còn phải hỏi" not in status

    def test_unclarified_logo_intent_in_pending(self):
        snap = empty_profile_snapshot()
        snap["all_fields"] = {"brandkit_consent": "yes", "logo_existing_intent": "unclarified"}
        snap["missing_required_fields"] = []
        snap["skipped_fields"] = []
        status = _build_collection_status(snap)
        assert "nhu cầu với logo hiện có" in status

    def test_skipped_fields_not_pending(self):
        snap = empty_profile_snapshot()
        snap["all_fields"] = {}
        snap["skipped_fields"] = ["facebook", "est_team_size"]
        status = _build_collection_status(snap)
        assert "Facebook" not in status.split("Còn phải hỏi")[-1].split("\n")[0]

    def test_context_builder_includes_status(self):
        cb = ContextBuilder()
        ctx = cb.build(
            profile_snapshot=empty_profile_snapshot(),
            suggested_objective={"type": "collect_required_field", "target_field": "owner_name"},
            observations={},
            matched_guidelines=[],
            recent_messages=[],
        )
        assert "collection_status" in ctx
        assert "Còn phải hỏi" in ctx["collection_status"]


# ============================================================
# Task hint — Phase 6: task chỉ hỏi field; chống chốt sớm đã chuyển
# sang principle reply (rules.yaml) + guard post-turn (KHÔNG nhồi vào task).
# ============================================================


class TestTaskContent:
    def test_collect_required_asks_field_not_closing(self):
        task = _task_from_objective(
            {"type": "collect_required_field", "target_field": "owner_name", "prompt_hint": "tên"},
            "anh",
        )
        assert "tên" in task
        # task gọn, KHÔNG còn rule cấm-chốt verbose lặp lại mỗi lượt
        assert "TUYỆT ĐỐI KHÔNG kết thúc" not in task
        assert "[Link Zalo]" not in task

    def test_collect_optional_asks_field_not_closing(self):
        task = _task_from_objective(
            {"type": "collect_optional_field", "target_field": "customer_storage_method",
             "prompt_hint": "cách lưu khách"},
            "anh",
        )
        assert "cách lưu khách" in task
        assert "TUYỆT ĐỐI KHÔNG kết thúc" not in task

    def test_zalo_handoff_includes_link_guidance(self):
        """zalo_handoff là objective DUY NHẤT hướng dẫn gửi link."""
        task = _task_from_objective({"type": "zalo_handoff"}, "anh")
        assert "Zalo" in task or "zalo" in task


# ============================================================
# Guard flow in TurnProcessor — retry rồi fallback
# ============================================================


class _FakeAgent:
    """Agent giả trả reply đóng-sớm; đếm số lần generate."""

    def __init__(self, replies):
        self.runtime = "gemini"  # tránh canned match (trừ greet)
        self.replies = list(replies)
        self.calls = 0

    def generate(self, context):
        from app.parlant.agent import AgentResult
        self.calls += 1
        text = self.replies.pop(0) if self.replies else "Dạ anh cho em xin tên ạ?"
        return AgentResult(text=text, model_id="fake")


def _build_processor(agent):
    from app.parlant.canned_responses import CannedResponseRegistry
    from app.parlant.context_builder import ContextBuilder
    from app.parlant.guideline_registry import GuidelineRegistry
    from app.parlant.turn_processor import TurnProcessor
    from app.parlant.workflow_engine import WorkflowEngine

    guideline_reg = GuidelineRegistry(config_path=CONFIG_DIR / "guidelines.yaml")
    guideline_reg.load()
    canned_reg = CannedResponseRegistry(config_path=CONFIG_DIR / "canned_responses.yaml")
    canned_reg.load()
    return TurnProcessor(
        guideline_registry=guideline_reg,
        canned_registry=canned_reg,
        workflow_engine=WorkflowEngine(),
        context_builder=ContextBuilder(),
        agent=agent,
    )


class TestGuardFlow:
    def test_premature_reply_triggers_retry(self):
        """Reply 1 chốt sớm, reply 2 sạch → dùng reply 2, flag regenerated."""
        agent = _FakeAgent([
            "Em đã thu thập đủ thông tin rồi, anh bấm link Zalo này nhé: [Link Zalo]",
            "Dạ em cảm ơn anh. Anh cho em hỏi mình lưu danh sách khách thế nào ạ?",
        ])
        tp = _build_processor(agent)
        result = tp.process(
            message="ok",
            profile_snapshot=empty_profile_snapshot(),
            recent_messages=[],
            address_form="anh",
            turn_count=3,
        )
        assert agent.calls == 2
        assert "Link Zalo" not in result.reply_text
        assert "premature_closing_regenerated" in result.trace.post_guard_flags

    def test_double_violation_falls_back_to_stub(self):
        """Cả 2 lần đều chốt sớm → fallback stub deterministic, flag fallback."""
        agent = _FakeAgent([
            "Em đã gom đủ thông tin rồi ạ! [Link Zalo]",
            "Mọi thông tin em đã nắm đầy đủ, anh vào link zalo nhé!",
        ])
        tp = _build_processor(agent)
        result = tp.process(
            message="ok",
            profile_snapshot=empty_profile_snapshot(),
            recent_messages=[],
            address_form="anh",
            turn_count=3,
        )
        assert agent.calls == 2
        assert "premature_closing_fallback" in result.trace.post_guard_flags
        assert not _has_premature_closing(result.reply_text)

    def test_clean_reply_no_retry(self):
        """Reply sạch → không retry, không flag."""
        agent = _FakeAgent([
            "Dạ em cảm ơn anh. Anh cho em xin tên cửa hàng mình nhé?",
        ])
        tp = _build_processor(agent)
        result = tp.process(
            message="chào em",
            profile_snapshot=empty_profile_snapshot(),
            recent_messages=[],
            address_form="anh",
            turn_count=1,
        )
        assert agent.calls == 1
        assert "premature_closing_regenerated" not in result.trace.post_guard_flags
        assert "premature_closing_fallback" not in result.trace.post_guard_flags
