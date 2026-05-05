"""Conversation state machine.

Logic Python thuần — KHÔNG để LLM tự quyết bot nói gì,
LLM chỉ làm extractor. Đây là kỷ luật trong tài liệu MVP
(mục 7: "Schema để hệ thống hiểu đúng").
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from app.core import red_flags
from app.core.card_renderer import render_card
from app.core.chat_replier import ChatReplier
from app.core.edit_parser import parse_edit_command
from app.core.extractor import Extractor
from app.core.prompts import FIELD_LABEL, GREETING, QUESTIONS, REQUIRED_FIELDS
from app.models.schema import (
    ChatMessage,
    ChatRole,
    DealerProfileRaw,
    ExtractResult,
    Session,
    Stage,
)
from app.storage.base import StorageAdapter

# Số lần tối đa hỏi 1 field KHÔNG TIẾN TRIỂN. Sau đó skip để không loop vô tận.
# Chỉ count khi turn KHÔNG fill được field nào mới (xem _handle_asking).
MAX_FIELD_ATTEMPTS = 3

# Field "intent" — bắt buộc dealer trả lời TRỰC TIẾP câu hỏi của bot.
# LLM hay suy diễn từ context mơ hồ (vd: dealer nói "đưa kịch bản đây" →
# LLM đoán pain_point="khách cũ khó gọi"), nên ép HIGH confidence mới accept.
# MEDIUM/LOW → coi như chưa có, hỏi lại.
INTENT_FIELDS = {"pain_points", "dl0_priority"}


class ConversationService:
    def __init__(
        self,
        extractor: Extractor,
        storage: StorageAdapter,
        chat_replier: ChatReplier,
    ):
        self.extractor = extractor
        self.storage = storage
        self.chat_replier = chat_replier

    def handle_message(
        self, session_id: str | None, dealer_message: str
    ) -> tuple[Session, str]:
        session = self._load_or_create(session_id)
        msg_clean = dealer_message.strip()

        # Lần đầu kết nối (frontend gửi message rỗng) → trả greeting
        if session.stage == Stage.GREETING and not msg_clean:
            session.stage = Stage.ASKING
            bot_msg = GREETING
            session.messages.append(self._bot(bot_msg))
            self.storage.save_session(session)
            return session, bot_msg

        # Ping rỗng trên session đã có — chỉ trả lại state, KHÔNG append.
        # Dùng cho frontend khôi phục history khi reload trang.
        if not msg_clean:
            last_bot = next(
                (m.content for m in reversed(session.messages) if m.role == ChatRole.BOT),
                "Em đang ở đây ạ, anh nhắn em nhé!",
            )
            return session, last_bot

        # Ghi message của dealer
        session.messages.append(self._dealer(msg_clean))

        # Quét red flags trên message này, gộp vào lịch sử
        new_flags = red_flags.detect_message_flags(msg_clean)
        if new_flags:
            session.flag_history.extend(new_flags)
            session.flag_history = red_flags.upgrade_persistent_flags(
                session.flag_history
            )

        # Escalation request → defer to human, sang Confirmation Card với info hiện có
        if red_flags.ESCALATION_REQUESTED in new_flags:
            bot_msg = self._handle_escalation(session)
            session.messages.append(self._bot(bot_msg))
            self.storage.save_session(session)
            return session, bot_msg

        if session.stage == Stage.GREETING:
            session.stage = Stage.ASKING

        if session.stage == Stage.ASKING:
            bot_msg = self._handle_asking(session)
        elif session.stage == Stage.CONFIRMING:
            bot_msg = self._handle_confirming(session, msg_clean)
        elif session.stage == Stage.DONE:
            bot_msg = self._handle_done(session)
        else:
            bot_msg = "Em xin lỗi, em chưa nghe rõ ý anh, anh nói lại giúp em với ạ?"

        session.messages.append(self._bot(bot_msg))
        self.storage.save_session(session)
        return session, bot_msg

    def _handle_escalation(self, session: Session) -> str:
        """Dealer xin gặp người thật — chuyển thẳng sang CONFIRMING với info hiện có."""
        if session.profile_raw.phone_or_zalo:
            session.stage = Stage.CONFIRMING
            return (
                "Dạ em hiểu rồi anh ạ. Em ghi nhận luôn để team người thật bên em "
                "liên hệ anh trong 24h nhé 🌷. Em xin tóm tắt info hiện có để xác "
                "nhận với anh trước nha:\n\n" + render_card(session.profile_raw)
            )
        # Chưa có SĐT → vẫn cần xin để team gọi lại
        return (
            "Dạ em hiểu rồi anh ạ. Em sẽ chuyển team người thật liên hệ anh nhé. "
            "Anh cho em xin số Zalo / SĐT cuối cùng để team gọi đúng số nha?"
        )

    # ---------- ASKING ----------
    def _handle_asking(self, session: Session) -> str:
        # Đếm số field đã fill TRƯỚC khi extract turn này (để biết có tiến triển không)
        weak_before = set(self._weak_required_fields(session))

        result = self.extractor.extract(session.messages)
        self._merge_extraction(session, result)

        weak_after = self._weak_required_fields(session)
        progress_made = len(weak_after) < len(weak_before)

        if weak_after:
            target = weak_after[0]

            # CHỈ tăng attempts khi turn này KHÔNG có tiến triển (no field newly filled).
            # Tránh bug: dealer defensive ("tao được gì") không trả lời nhưng attempts vẫn tăng
            # → field bị skip oan dù bot chưa thực sự hỏi nhiều lần.
            if not progress_made:
                session.field_attempts[target] = session.field_attempts.get(target, 0) + 1

            # Đã hỏi quá MAX_FIELD_ATTEMPTS không tiến triển → skip
            if session.field_attempts.get(target, 0) > MAX_FIELD_ATTEMPTS:
                if target not in session.skipped_fields:
                    session.skipped_fields.append(target)
                weak_after = self._weak_required_fields(session)
                if not weak_after:
                    return self._go_to_confirming(session)
                target = weak_after[0]

            if result.confirm_questions:
                return result.confirm_questions[0]
            return self._fallback_question_for(target)

        return self._go_to_confirming(session)

    def _go_to_confirming(self, session: Session) -> str:
        session.stage = Stage.CONFIRMING
        prefix = ""
        if session.skipped_fields:
            prefix = (
                "Em hiểu là có vài thông tin mình chưa tiện chia sẻ ngay, không sao ạ. "
                "Em xin tóm tắt phần đã có để mình xác nhận trước nhé:\n\n"
            )
        return prefix + render_card(session.profile_raw)

    def _merge_extraction(self, session: Session, result: ExtractResult) -> None:
        fields = result.extracted_fields or {}
        confidence = result.confidence or {}
        profile = session.profile_raw
        for key, val in fields.items():
            if val in (None, "", []):
                continue
            # Intent fields: chỉ merge khi HIGH confidence — chống LLM suy diễn
            if key in INTENT_FIELDS and confidence.get(key) != "HIGH":
                continue
            if hasattr(profile, key):
                setattr(profile, key, val)
        session.confidence = {**session.confidence, **confidence}
        session.missing_fields = result.missing_fields or []

    def _weak_required_fields(self, session: Session) -> list[str]:
        """Field bắt buộc còn null hoặc confidence chưa đủ tin cậy (đã loại field bị skip).

        - Field thường: empty hoặc LOW → weak
        - INTENT field: empty hoặc !=HIGH → weak (đòi dealer trả lời rõ)
        """
        weak = []
        profile_dict = session.profile_raw.model_dump()
        for field in REQUIRED_FIELDS:
            if field in session.skipped_fields:
                continue
            value = profile_dict.get(field)
            empty = value in (None, "", [])
            conf = session.confidence.get(field)
            if field in INTENT_FIELDS:
                # Intent: phải HIGH mới accept
                not_high = conf != "HIGH"
                if empty or not_high:
                    weak.append(field)
            else:
                # Field thường: empty hoặc LOW
                if empty or conf == "LOW":
                    weak.append(field)
        return weak

    @staticmethod
    def _fallback_question_for(field: str) -> str:
        # Fallback chỉ chạy khi LLM không sinh được confirm_questions —
        # vẫn cố gắng giữ tone acknowledge + ask, nhưng generic vì không có context.
        mapping = {
            "dealer_name": "Dạ em xin lỗi anh, em chưa rõ tên cửa hàng mình. Anh cho em biết bên mình đặt tên cửa hàng là gì với ạ?",
            "owner_name": "Dạ tiện đây để em biết xưng hô cho đúng, anh cho em xin tên gọi của anh với ạ?",
            "phone_or_zalo": "Dạ vâng em hiểu rồi ạ. Anh ơi cho em xin số Zalo hoặc số điện thoại khách hay liên hệ với cửa hàng mình luôn nhé?",
            "province": "Dạ em ghi nhận rồi ạ. Cho em hỏi cửa hàng mình hiện đang ở tỉnh/thành nào vậy anh?",
            "main_category": "Dạ em hiểu rồi ạ. Bên mình hiện làm mạnh nhất mảng gì nhỉ anh — cửa cuốn, cửa nhôm kính, tủ bếp, solar, bảo trì, hay VLXD tổng hợp ạ?",
            "customer_base_estimate": "Dạ vâng ạ. Anh ơi 2-3 năm gần đây bên mình tầm bao nhiêu khách cũ còn liên hệ lại được nhỉ? Anh ước chừng cho em cũng được ạ.",
            "pain_points": "Dạ em hiểu rồi anh. Em hỏi thật lòng nhé, hiện bên mình đang vướng nhất ở chỗ nào hả anh — khách cũ không quay lại, marketing yếu, hay khó quản lý đội thợ ạ? Anh có nhiều vướng cùng lúc cũng cứ kể em nghe nhé.",
            "dl0_priority": "Dạ vâng em ghi nhận hết rồi ạ. Vậy giữa các thứ em có thể hỗ trợ — bộ mặt số, QR gửi khách cũ, bài đăng, hay trợ lý tư vấn — anh muốn em ưu tiên cái nào trước hả anh?",
        }
        return mapping.get(field, QUESTIONS[0])

    # ---------- CONFIRMING ----------
    def _handle_confirming(self, session: Session, dealer_message: str) -> str:
        msg = dealer_message.strip().lower()

        if self._is_affirmative(msg):
            session.profile_raw.confirmation_status = "CONFIRMED"
            session.profile_raw.review_status = "RAW"
            session.profile_raw.flags = self._final_flags(session)
            self.storage.save_profile_raw(session.session_id, session.profile_raw)
            session.stage = Stage.DONE
            return (
                "Dạ em cảm ơn anh nhiều ạ! Em đã ghi nhận hồ sơ rồi nhé.\n"
                "Team bên em sẽ xem qua và liên hệ lại với anh trong 24h ạ. "
                "Có gì cần hỗ trợ thêm anh cứ nhắn em nhé! 🌷\n\n"
                "(MVP: phần Mini App + cộng đồng em sẽ làm tiếp ở giai đoạn sau ạ)"
            )

        # P1-7: thử parse "sửa X thành Y" bằng regex trước → tiết kiệm 1 LLM call
        regex_patch = parse_edit_command(dealer_message)
        if regex_patch:
            field, new_value = regex_patch
            setattr(session.profile_raw, field, new_value)
            session.profile_raw.confirmation_status = "EDITED"
            return (
                f"Dạ em đã cập nhật {FIELD_LABEL.get(field, field)} thành "
                f"{new_value} rồi ạ, anh xem lại giúp em nhé:\n\n"
                + render_card(session.profile_raw)
            )

        # Fallback: dealer nói tự do (không match regex) → gọi LLM extractor
        result = self.extractor.extract(session.messages)
        self._merge_extraction(session, result)
        session.profile_raw.confirmation_status = "EDITED"
        return "Dạ em đã cập nhật rồi ạ, anh xem lại giúp em nhé:\n\n" + render_card(session.profile_raw)

    # ---------- DONE — chat tiếp + cho phép sửa ----------
    EDIT_KEYWORDS = (
        "sửa", "sua", "đổi", "doi", "thay", "cập nhật", "cap nhat",
        "không phải", "khong phai", "nhầm", "nham", "lại", "đính chính",
        "dinh chinh", "update",
    )

    def _handle_done(self, session: Session) -> str:
        """Sau DONE: dealer chat thoải mái. Chỉ chạy edit detection khi
        dealer DÙNG keyword sửa/đổi — tránh LLM paraphrase nhẹ bị nhầm là edit."""
        latest_msg = ""
        for m in reversed(session.messages):
            if m.role == ChatRole.DEALER and (m.content or "").strip():
                latest_msg = m.content.lower()
                break

        wants_edit = any(kw in latest_msg for kw in self.EDIT_KEYWORDS)

        if wants_edit:
            result = self.extractor.extract(session.messages)
            changes = self._detect_field_changes(session.profile_raw, result)
            if changes:
                self._merge_extraction(session, result)
                session.profile_raw.confirmation_status = "EDITED"
                session.profile_raw.flags = self._final_flags(session)
                self.storage.save_profile_raw(
                    session.session_id, session.profile_raw
                )
                change_lines = "\n".join(
                    f"• {FIELD_LABEL.get(f, f)}: {self._fmt_value(v)}"
                    for f, v in changes
                )
                return (
                    f"Dạ em đã cập nhật hồ sơ rồi ạ:\n\n{change_lines}\n\n"
                    "Còn gì cần em chỉnh nữa không anh?"
                )
            # Có ý sửa nhưng chưa rõ field nào → để LLM hỏi rõ
            return (
                "Dạ anh nói rõ giúp em thông tin nào cần sửa và giá trị mới "
                "là gì với ạ? Ví dụ: \"sửa SĐT thành 0901234567\"."
            )

        # Không có ý sửa → casual chat
        return self.chat_replier.reply(session.messages)

    @staticmethod
    def _final_flags(session: Session) -> list[str]:
        """Gộp flag từ message history + flag suy ra từ profile data."""
        msg_flags = list(dict.fromkeys(session.flag_history))
        profile_flags = red_flags.detect_profile_flags(
            session.profile_raw.model_dump()
        )
        merged = list(dict.fromkeys(msg_flags + profile_flags))
        return red_flags.upgrade_persistent_flags(merged)

    @staticmethod
    def _detect_field_changes(
        current: DealerProfileRaw, result: ExtractResult
    ) -> list[tuple[str, object]]:
        """So sánh profile hiện tại với extracted_fields, trả list (field, new_value)."""
        changes = []
        current_dict = current.model_dump()
        for field, new_val in (result.extracted_fields or {}).items():
            if new_val in (None, "", []):
                continue
            old_val = current_dict.get(field)
            if old_val != new_val:
                changes.append((field, new_val))
        return changes

    @staticmethod
    def _fmt_value(v: object) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v) if v else "(trống)"
        return str(v) if v not in (None, "") else "(trống)"

    @staticmethod
    def _is_affirmative(msg: str) -> bool:
        if not msg:
            return False
        patterns = [
            r"^đúng\b", r"^dung\b", r"^ok\b", r"^okay\b",
            r"^chốt\b", r"^chot\b", r"^xác nhận\b", r"^xac nhan\b",
            r"^đồng ý\b", r"^dong y\b", r"^yes\b", r"^y\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    # ---------- helpers ----------
    def _load_or_create(self, session_id: str | None) -> Session:
        if session_id:
            existing = self.storage.load_session(session_id)
            if existing:
                return existing
        return Session(session_id=session_id or str(uuid.uuid4()))

    @staticmethod
    def _bot(content: str) -> ChatMessage:
        return ChatMessage(role=ChatRole.BOT, content=content, ts=datetime.utcnow())

    @staticmethod
    def _dealer(content: str) -> ChatMessage:
        return ChatMessage(role=ChatRole.DEALER, content=content, ts=datetime.utcnow())
