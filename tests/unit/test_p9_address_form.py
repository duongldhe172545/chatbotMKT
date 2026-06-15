"""Phase 9.1 — xưng hô anh/chị tất định (2026-06-12).

detect_address_form: suy "anh"/"chi" từ cách khách tự xưng trong lịch sử.
guard hậu-lượt: address_form="chi" → sửa "anh" lạc thành "chị".
"""
from __future__ import annotations

from pathlib import Path

from app.parlant.observation_detector import detect_address_form

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _u(text):
    return {"source": "user", "text": text}


class TestDetectAddressForm:
    def test_chi_self_intro(self):
        assert detect_address_form([_u("chị tên Thư")]) == "chi"

    def test_chi_toi_la_chi(self):
        assert detect_address_form([_u("tôi là chị Hoa, làm nhôm kính")]) == "chi"

    def test_chi_goi_chi(self):
        assert detect_address_form([_u("em gọi chị nhé")]) == "chi"

    def test_anh_self_intro(self):
        assert detect_address_form([_u("anh tên Linh")]) == "anh"

    def test_default_anh_when_no_cue(self):
        assert detect_address_form([_u("Nội thất Linh Đan"), _u("36 Lê Văn Thiêm")]) == "anh"

    def test_chi_wins_over_later_neutral(self):
        # cue chị ở lượt đầu → giữ chị dù lượt sau trung tính
        msgs = [_u("chị tên Thư"), _u("bán tủ bếp"), _u("ở Hà Nội")]
        assert detect_address_form(msgs) == "chi"

    def test_only_scan_user_messages(self):
        # ADVERSARIAL: câu của BOT có "chị tên" KHÔNG được tính
        msgs = [{"source": "linh_mkt", "text": "dạ chị tên gì ạ?"}, _u("anh tên Hùng")]
        assert detect_address_form(msgs) == "anh"

    def test_empty_default(self):
        assert detect_address_form([]) == "anh"

    def test_no_false_positive_doanh_thanh(self):
        # "anh" trong "doanh thu", "thanh toán" KHÔNG được match (\b word boundary)
        assert detect_address_form([_u("doanh thu thanh toán ổn")]) == "anh"  # default, không crash


def _build_tp():
    from app.parlant.canned_responses import CannedResponseRegistry
    from app.parlant.context_builder import ContextBuilder
    from app.parlant.guideline_registry import GuidelineRegistry
    from app.parlant.turn_processor import TurnProcessor
    from app.parlant.workflow_engine import WorkflowEngine

    g = GuidelineRegistry(config_path=CONFIG_DIR / "guidelines.yaml"); g.load()
    c = CannedResponseRegistry(config_path=CONFIG_DIR / "canned_responses.yaml"); c.load()

    class _A:
        runtime = "gemini"
    return TurnProcessor(
        guideline_registry=g, canned_registry=c,
        workflow_engine=WorkflowEngine(), context_builder=ContextBuilder(), agent=_A(),
    )


class TestAddressGuard:
    def test_chi_repairs_stray_anh(self):
        tp = _build_tp()
        reply, flags = tp._post_turn_guards(
            "Dạ Anh cho em xin tên cửa hàng của anh nhé?", "msg", "chi"
        )
        assert "anh" not in reply.lower()
        assert "Chị" in reply and "chị" in reply  # giữ hoa đầu câu + thường giữa câu
        assert "address_form_repaired" in flags

    def test_anh_form_unchanged(self):
        tp = _build_tp()
        reply, flags = tp._post_turn_guards("Dạ anh cho em xin tên nhé?", "msg", "anh")
        assert "anh" in reply.lower()
        assert "address_form_repaired" not in flags

    def test_chi_no_anh_no_flag(self):
        tp = _build_tp()
        reply, flags = tp._post_turn_guards("Dạ chị cho em xin tên nhé?", "msg", "chi")
        assert "address_form_repaired" not in flags
