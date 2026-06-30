"""Test md_exporter — render profile + history ra Markdown."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.md_exporter import (
    render_full_md,
    render_profile_md,
    render_session_history_md,
    safe_filename,
)
import uuid
from app.models.enums import ConfirmationStatus, DealerType, Flag, Stage
from app.models.schema import DealerProfileRaw, HistoryMessage, SessionState

def create_session() -> SessionState:
    return SessionState(session_id=str(uuid.uuid4()))


class TestSafeFilename:
    def test_strip_forbidden_chars(self):
        # Phase 5 R4: diacritics stripped → ASCII-safe cho HTTP header
        assert safe_filename('Tên/cửa<hàng>') == "Ten_cua_hang"

    def test_strip_whitespace(self):
        assert safe_filename("  Tùng  ") == "Tung"

    def test_diacritics_stripped_for_http_safe(self):
        """Phase 5 R4 Gap 13: Việt → ASCII cho Content-Disposition."""
        assert safe_filename("Nhôm Kính Thanh Tùng") == "Nhom_Kinh_Thanh_Tung"
        assert safe_filename("Đà Nẵng") == "Da_Nang"
        assert safe_filename("Đồng Nai") == "Dong_Nai"

    def test_empty_returns_untitled(self):
        assert safe_filename("") == "untitled"
        assert safe_filename(None) == "untitled"

    def test_long_truncated(self):
        long = "a" * 200
        result = safe_filename(long, max_len=50)
        assert len(result) == 50


class TestRenderProfileMd:
    def test_minimal_profile(self):
        session = create_session()
        profile = DealerProfileRaw(owner_name="Tùng")
        md = render_profile_md(session, profile)
        assert "# Hồ sơ đại lý" in md
        assert "Tùng" in md
        assert "## 🏪 1. Thông tin cơ bản" in md
        assert "## 🛠 2. 9 Tiêu chí đánh giá" in md
        assert "## 🎁 3. Thông tin bổ sung làm Logo & Thương hiệu" in md
        assert "## ⏰ Hành động trong 3 ngày tới" in md

    def test_full_profile(self):
        session = create_session()
        session.stage = Stage.DONE
        session.confirmation_status = ConfirmationStatus.CONFIRMED
        profile = DealerProfileRaw(
            owner_name="Tùng",
            dealer_name="Nhôm Kính Thanh Tùng",
            address="123 Lê Lợi Q.1 TP.HCM",
            phone_or_zalo="0912345678",
            main_product="cửa nhôm kính",
            brandkit_consent="yes",
            main_category="cua_nhom_kinh",
            est_team_size=5,
            supplier_brands=["Xingfa"],
            province="TP.HCM",
        )
        md = render_profile_md(session, profile)
        assert "Nhôm Kính Thanh Tùng" in md
        assert "0912345678" in md
        assert "cua_nhom_kinh" in md
        assert "Xingfa" in md
        assert "5 người" in md
        assert "TP.HCM" in md


    def test_no_forbidden_vocab(self):
        """Refer GLOSSARY § 6: không có Tier/C-score/BRANDKIT."""
        session = create_session()
        profile = DealerProfileRaw(
            owner_name="Tùng",
            brandkit_consent="yes",
            slogan_options=["A", "B"],
        )
        md = render_profile_md(session, profile)
        for word in ["Tier", "C-score", "Scoring", "BRANDKIT", "Profile",
                     "Namecard", "evaluation", "ranking"]:
            assert word not in md, f"Vocab cấm '{word}' xuất hiện trong MD"

    def test_consent_no_path(self):
        session = create_session()
        profile = DealerProfileRaw(brandkit_consent="no")
        md = render_profile_md(session, profile)
        assert "Không ✗" in md
        # Section 5 vẫn có (giới thiệu nhóm)
        assert "Cộng Đồng Thợ 4.0" in md


class TestRenderHistoryMd:
    def test_render_history(self):
        session = create_session()
        ts = datetime.now(timezone.utc)
        session.history = [
            HistoryMessage(role="dealer", content="OK em", ts=ts),
            HistoryMessage(role="bot", content="Dạ em note.\nHỏi anh tiếp", ts=ts),
        ]
        md = render_session_history_md(session)
        assert "Dealer" in md
        assert "Bot" in md
        assert "OK em" in md
        assert "Dạ em note." in md
        # Multi-line indented as blockquote
        assert "> Hỏi anh tiếp" in md

    def test_empty_history(self):
        session = create_session()
        md = render_session_history_md(session)
        assert "chưa có" in md.lower()


class TestRenderFullMd:
    def test_combined_profile_and_history(self):
        session = create_session()
        session.history = [
            HistoryMessage(
                role="dealer", content="hi",
                ts=datetime.now(timezone.utc),
            ),
        ]
        profile = DealerProfileRaw(owner_name="Tùng")
        md = render_full_md(session, profile, include_history=True)
        assert "Hồ sơ đại lý" in md
        assert "Lịch sử trò chuyện" in md

    def test_skip_history(self):
        session = create_session()
        session.history = [
            HistoryMessage(role="dealer", content="hi",
                          ts=datetime.now(timezone.utc)),
        ]
        profile = DealerProfileRaw(owner_name="Tùng")
        md = render_full_md(session, profile, include_history=False)
        assert "Lịch sử trò chuyện" not in md
