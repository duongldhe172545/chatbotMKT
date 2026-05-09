"""Conversation state machine.

Logic Python thuần — KHÔNG để LLM tự quyết bot nói gì,
LLM chỉ làm extractor. Đây là kỷ luật trong tài liệu MVP
(mục 7: "Schema để hệ thống hiểu đúng").
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from app.core import red_flags, spam_guard
from app.core.address_form import detect_address_form
from app.core.card_renderer import render_card
from app.core.chat_replier import ChatReplier
from app.core.edit_parser import parse_edit_command
from app.core.extractor import Extractor
from app.core.intent_detect import (
    is_defensive_message,
    is_refusal_message,
    is_tam_su_message,
)
from app.core.opener_enforcer import (
    classify_opener_group,
    enforce_opener_variety,
)
from app.core.prompts import FIELD_LABEL, GREETING, QUESTIONS, REQUIRED_FIELDS
from app.core.replier import Goal, Replier
from app.core.reply_guards import (
    enforce_defensive_answer,
    enforce_min_length,
)
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

# Trivial detect đã chuyển sang spam_guard.is_trivial_message (Layer 4 cải tiến —
# bắt thêm "okkkk", "vânggg", "ok ạ", "uhmmm"...). Alias để giữ backward compat.
_is_trivial_message = spam_guard.is_trivial_message


# Note: helpers detect_address_form, is_*_message, classify_opener_group,
# enforce_opener_variety, enforce_min_length, enforce_defensive_answer đã
# move sang các module riêng (intent_detect / address_form / opener_enforcer
# / reply_guards) — giảm conversation.py từ ~1350 xuống ~700 dòng.


class ConversationService:
    def __init__(
        self,
        extractor: Extractor,
        storage: StorageAdapter,
        chat_replier: ChatReplier,
        replier: Replier | None = None,
    ):
        self.extractor = extractor
        self.storage = storage
        self.chat_replier = chat_replier
        # Replier mới (Bước 1 refactor). None = giữ flow cũ (Extractor sinh
        # cả field + reply). Set qua USE_REPLIER=true trong .env.
        self.replier = replier

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

        address = session.address_form or "anh"

        # === SPAM GUARD PRECHECK (Layer 1.1, 1.2, 3.B, soft_ended) ===
        # Chạy TRƯỚC khi append message + flow chính → tiết kiệm LLM call.
        proceed, blocked_reply = spam_guard.precheck(session, msg_clean, address)
        if not proceed:
            session.messages.append(self._dealer(msg_clean))
            # Nếu là injection lần đầu, ghi flag để turn sau biết là lần 2
            if spam_guard.detect_injection(msg_clean):
                session.flag_history.append(red_flags.PROMPT_INJECTION)
            session.messages.append(self._bot(blocked_reply))
            self.storage.save_session(session)
            return session, blocked_reply

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

        # === LAYER 5 — Update mode từ flags + xử template_only ===
        spam_guard.update_mode_after_flags(session, new_flags)
        if session.mode == "template_only":
            reason = (
                "abuse" if red_flags.ABUSIVE_LANGUAGE in new_flags
                else "garbage" if red_flags.GARBAGE_INPUT in new_flags
                else "neutral"
            )
            bot_msg = spam_guard.template_only_mode_reply(address, reason)
            session.messages.append(self._bot(bot_msg))
            self.storage.save_session(session)
            return session, bot_msg

        # === LAYER 1.4 — Hard cap quota ===
        if session.llm_call_count >= spam_guard.LLM_CALL_HARD_CAP:
            session.mode = "soft_ended"
            bot_msg = spam_guard.template_quota_exceeded(address)
            session.messages.append(self._bot(bot_msg))
            self.storage.save_session(session)
            return session, bot_msg

        # === LAYER 1.3 — Cảnh báo + đẩy CONFIRMING tại ngưỡng warn ===
        if (
            session.llm_call_count >= spam_guard.LLM_CALL_WARN_THRESHOLD
            and session.stage == Stage.ASKING
            and not session.quota_warned
        ):
            session.quota_warned = True
            warn_text = spam_guard.template_quota_warn(address)
            card = self._go_to_confirming(session)
            bot_msg = warn_text + "\n\n" + card
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

        # === LAYER 3.C — Output guard: drop reply có leak system/code ===
        if spam_guard.detect_output_leak(bot_msg):
            bot_msg = spam_guard.template_output_leak_blocked(address)

        # B3: Post-process safety net — nếu Haiku vẫn lặp nhóm bị cấm dù
        # đã có directive trong prompt, code strip prefix + thay opener khác.
        # Chỉ apply cho ASKING (CONFIRMING+DONE đa phần dùng template hardcoded).
        if session.stage == Stage.ASKING:
            bot_msg, opener_group = enforce_opener_variety(
                bot_msg, session.last_opener_group
            )
        else:
            opener_group = classify_opener_group(bot_msg)

        # Layer 2 — Defensive answer guarantee: nếu dealer hỏi ngược mà bot
        # không trả lời thẳng, code prepend đáp trực tiếp.
        if session.stage in (Stage.ASKING, Stage.CONFIRMING):
            address = session.address_form or "anh"
            latest_dealer_msg = next(
                (m.content for m in reversed(session.messages) if m.role == ChatRole.DEALER),
                "",
            )
            bot_msg = enforce_defensive_answer(bot_msg, latest_dealer_msg, address)

        # Layer 1 — Pre-send validation: chống câu cộc lốc / quá ngắn.
        # Áp dụng cho ASKING + CONFIRMING (không áp dụng greeting/done).
        if session.stage in (Stage.ASKING, Stage.CONFIRMING):
            extracted_this_turn = getattr(self, "_last_extracted_this_turn", None) or {}
            bot_msg = enforce_min_length(
                bot_msg,
                extracted_data=extracted_this_turn,
                address=session.address_form or "anh",
                min_words=25,
            )

        # Track nhóm opener turn này → cấm nhóm này ở turn sau.
        if opener_group != "X":
            session.last_opener_group = opener_group

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
        weak_before_list = self._weak_required_fields(session)
        weak_before = set(weak_before_list)

        # Snapshot profile TRƯỚC merge để diff field MỚI turn này (Q1 fix:
        # tránh enforce_min_length prepend compliment lạc quẻ về tên/shop
        # đã có từ turn trước).
        profile_before_dump = session.profile_raw.model_dump()

        # C3: Skip LLM extractor khi dealer message tầm thường ("ok"/"yes"/"k"...)
        # → tiết kiệm 1 LLM call cho ~10-15% turn. Dùng fallback question.
        latest_dealer = next(
            (m.content for m in reversed(session.messages) if m.role == ChatRole.DEALER),
            "",
        )
        # Phân loại intent — dùng cho cả Extractor (cũ) và Replier (mới).
        defensive = is_defensive_message(latest_dealer) if latest_dealer else False
        tam_su = (
            is_tam_su_message(latest_dealer) and not defensive
            if latest_dealer else False
        )

        if _is_trivial_message(latest_dealer):
            result = ExtractResult()
        else:
            # KHÔNG inject target_field hint khi defensive/tâm sự — để LLM tự do
            # trả lời câu hỏi / engage theo persona, không bị ép hỏi field.
            target_for_extract = (
                weak_before_list[0]
                if weak_before_list and not (defensive or tam_su)
                else None
            )
            # Khi USE_REPLIER bật: Extractor chỉ trích field (confirm_questions
            # sẽ bị ignore phía dưới). Vẫn truyền is_tam_su/is_defensive cho
            # Extractor vì nó dùng cùng prompt — sẽ refactor ở Bước sau.
            session.llm_call_count += 1
            result = self.extractor.extract(
                session.messages,
                forbidden_opener_group=session.last_opener_group,
                target_field=target_for_extract,
                is_tam_su=tam_su,
                is_defensive=defensive,
            )
        # Merge trước, sau đó diff với profile_before_dump để lấy field
        # THỰC SỰ MỚI turn này (Q1 fix). Khác với cũ — chỉ snapshot
        # extracted_fields, không phân biệt field cũ vs mới.
        self._merge_extraction(session, result)
        profile_after_dump = session.profile_raw.model_dump()
        self._last_extracted_this_turn = self._diff_new_fields(
            profile_before_dump, profile_after_dump
        )
        # Detect xưng hô — sau khi đã có owner_name potentially mới
        detected = detect_address_form(latest_dealer, session.profile_raw.owner_name)
        if detected == "chị" and session.address_form != "chị":
            session.address_form = "chị"

        # Cross-session memory: nếu vừa cho phone và phone match dealer cũ,
        # auto-fill các field còn thiếu từ profile cũ.
        if not session.profile_raw.confirmation_status == "CONFIRMED":
            self._maybe_load_returning_dealer(session)

        weak_after = self._weak_required_fields(session)
        progress_made = len(weak_after) < len(weak_before)

        # REFUSAL handling — user nói "đéo cho" / "không cho" cho field hiện tại.
        # Acknowledge respect + skip field, không spam lại câu hỏi cũ.
        if (
            weak_after
            and is_refusal_message(latest_dealer)
            and not progress_made
        ):
            target_refused = weak_after[0]
            address = session.address_form or "anh"
            # Skip field này — ghi nhận count để re-ask logic biết khi nào
            # dealer đã hợp tác trở lại (sau ≥2 field mới fill).
            if target_refused not in session.skipped_fields:
                session.skipped_fields.append(target_refused)
                session.skipped_at_filled_count[target_refused] = (
                    self._count_filled_required(session)
                )
            weak_after = self._weak_required_fields(session)

            # Hết field weak → confirming ngay (vẫn cần ack ngắn trước card)
            if not weak_after:
                ack = (
                    f"Dạ em tôn trọng quyết định của {address} ạ — phần đó "
                    f"em tạm bỏ qua, không ép {address}. "
                )
                return ack + self._go_to_confirming(session)

            next_target = weak_after[0]

            # ===== PATH MỚI — Replier xử HANDLE_REFUSAL =====
            # Route qua Replier để tránh triple-prefix mess (template ack +
            # bridge + fallback question với prefix riêng).
            if self.replier is not None:
                goal = Goal(
                    kind="HANDLE_REFUSAL",
                    skipped_field=target_refused,
                    next_field=next_target,
                    forbidden_opener_group=session.last_opener_group,
                )
                try:
                    session.llm_call_count += 1
                    return self.replier.reply(
                        messages=session.messages,
                        goal=goal,
                        profile=session.profile_raw,
                        address=address,
                    )
                except Exception:
                    # Replier fail → fallback path cũ
                    pass

            # ===== PATH CŨ — template hardcoded =====
            ack = (
                f"Dạ em tôn trọng quyết định của {address} ạ — phần đó "
                f"em tạm bỏ qua, không ép {address}. "
            )
            return ack + "À tiện đây em hỏi xíu nhé — " + self._fallback_question_for(next_target)

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
                    session.skipped_at_filled_count[target] = (
                        self._count_filled_required(session)
                    )
                weak_after = self._weak_required_fields(session)
                if not weak_after:
                    return self._go_to_confirming(session)
                target = weak_after[0]

            # Re-ask logic: nếu target là field đã từng skip mà nay đủ điều
            # kiện hỏi lại → mark retried (chỉ retry 1 lần) + thêm hint cho
            # Replier để tone nhẹ ("nếu vẫn không tiện thì bỏ qua").
            is_reask = (
                target in session.skipped_fields
                and target not in session.skipped_retried
            )
            if is_reask:
                session.skipped_retried.append(target)

            # ===== PATH MỚI (Bước 1 refactor) — Replier sinh reply =====
            if self.replier is not None:
                # Re-ask hint chỉ áp dụng cho ASK_FIELD — defensive/tâm sự
                # ưu tiên trả lời/engage trước, re-ask vibe sẽ confuse.
                reask_hint = (
                    "Đây là lần hỏi lại nhẹ field dealer trước đó đã từ chối. "
                    "Tone NHẸ NHÀNG, KHÔNG ép. Chèn câu 'nếu anh vẫn không "
                    "tiện thì mình bỏ qua cũng được ạ'. Không hỏi lại lần "
                    "thứ hai nếu dealer tiếp tục từ chối."
                ) if is_reask else None

                if defensive:
                    goal = Goal(
                        kind="ANSWER_DEFENSIVE",
                        target_field=target,
                        forbidden_opener_group=session.last_opener_group,
                    )
                elif tam_su:
                    goal = Goal(
                        kind="ENGAGE_TAM_SU",
                        next_field=target,
                        forbidden_opener_group=session.last_opener_group,
                    )
                else:
                    goal = Goal(
                        kind="ASK_FIELD",
                        target_field=target,
                        forbidden_opener_group=session.last_opener_group,
                        extra_hint=reask_hint,
                    )
                try:
                    session.llm_call_count += 1
                    return self.replier.reply(
                        messages=session.messages,
                        goal=goal,
                        profile=session.profile_raw,
                        address=session.address_form or "anh",
                    )
                except Exception:
                    # Replier fail → fallback path cũ (template + chém gió)
                    pass

            # ===== PATH CŨ — dùng confirm_questions[0] từ Extractor =====
            # Field order guard — kiểm tra LLM có hỏi đúng target không.
            # LLM Sonnet đôi khi skip phone để hỏi ngành (vì ngành "thân thiện"
            # hơn). Force respect order priority.
            if result.confirm_questions:
                llm_q = result.confirm_questions[0]
                if self._llm_question_matches_target(llm_q, target):
                    return llm_q
                # LLM hỏi sai field → bỏ, dùng template + chém gió tâm sự nếu có
            tam_su_engage = self._tam_su_engagement(latest_dealer)
            base_question = self._fallback_question_for(target)
            if tam_su_engage:
                return f"{tam_su_engage} {base_question}"
            return base_question

        return self._go_to_confirming(session)

    @staticmethod
    def _llm_question_matches_target(question: str, target: str) -> bool:
        """Check LLM's confirm_question có thực sự hỏi về target field không.

        Match keyword cụ thể của field để tránh LLM skip target.
        """
        if not question or not target:
            return True  # no validation possible
        q = question.lower()
        # Map target field → keywords PHẢI có trong câu hỏi
        target_keywords = {
            "dealer_name": ("tên cửa hàng", "tên shop", "đặt tên"),
            "owner_name": ("tên anh", "tên chị", "tên gọi", "xưng hô", "anh tên", "chị tên"),
            "phone_or_zalo": ("zalo", "sđt", "số điện thoại", "điện thoại", "số liên hệ", "số khách"),
            "province": ("tỉnh", "thành phố"),
            "district": ("quận", "huyện"),
            "main_category": ("mảng", "ngành", "cửa cuốn", "nhôm kính", "tủ bếp", "solar", "vlxd"),
            "dealer_type": ("đại lý", "xưởng", "thợ", "bán lẻ", "phân phối", "lắp đặt"),
            "customer_base_estimate": ("khách cũ", "bao nhiêu khách", "tầm bao nhiêu", "khoảng bao nhiêu"),
            "pain_points": ("vướng", "đau", "khó khăn", "vấn đề"),
            "dl0_priority": ("ưu tiên", "muốn em làm", "bộ mặt số", "qr khách", "bài đăng", "trợ lý"),
        }
        keywords = target_keywords.get(target, ())
        if not keywords:
            return True
        return any(kw in q for kw in keywords)

    def _go_to_confirming(self, session: Session) -> str:
        session.stage = Stage.CONFIRMING
        prefix = ""
        if session.is_returning_dealer:
            prefix = (
                "Dạ em nhớ anh đã đăng ký bên em hôm trước rồi ạ 🌷. Em xin "
                "xác nhận lại thông tin để chắc chắn không có gì thay đổi nhé:\n\n"
            )
        elif session.skipped_fields:
            prefix = (
                "Em hiểu là có vài thông tin mình chưa tiện chia sẻ ngay, không sao ạ. "
                "Em xin tóm tắt phần đã có để mình xác nhận trước nhé:\n\n"
            )
        return prefix + render_card(session.profile_raw)

    def _merge_extraction(self, session: Session, result: ExtractResult) -> None:
        fields = result.extracted_fields or {}
        confidence = result.confidence or {}
        profile = session.profile_raw
        accepted_confidence: dict[str, str] = {}
        for key, val in fields.items():
            if val in (None, "", []):
                continue
            # INTENT fields (pain/priority): accept HIGH+MEDIUM — reject LOW.
            if key in INTENT_FIELDS and confidence.get(key) == "LOW":
                continue
            # Anti-overwrite: nếu field đã có value với confidence HIGH, KHÔNG cho
            # turn sau ghi đè bằng value khác trừ khi cũng HIGH. Tránh case LLM
            # extract sai (vd: dealer_name "Cuốn Phong" bị overwrite thành "Phong").
            if hasattr(profile, key):
                old_val = getattr(profile, key)
                old_conf = session.confidence.get(key)
                new_conf = confidence.get(key)
                if (
                    old_val not in (None, "", [])
                    and old_val != val
                    and old_conf == "HIGH"
                    and new_conf != "HIGH"
                ):
                    continue  # giữ value cũ HIGH, không đè bằng MEDIUM/LOW
                setattr(profile, key, val)
                if new_conf:
                    accepted_confidence[key] = new_conf
        # CHỈ merge confidence cho field thực sự được fill turn này. KHÔNG đè
        # confidence cũ HIGH với LOW của field không liên quan — fix bug
        # truncate history (C2) khiến extractor không thấy data cũ → trả LOW
        # cho field đã có HIGH → bot hỏi lại.
        session.confidence = {**session.confidence, **accepted_confidence}
        session.missing_fields = result.missing_fields or []
        # Rule-based regex bắt pain/priority từ message dealer cuối — bù khi LLM
        # đánh MEDIUM/LOW cho keyword rõ ràng.
        self._merge_rule_based_intent(session)

    def _maybe_load_returning_dealer(self, session: Session) -> None:
        """Cross-session memory v2 — SAFE LOAD.

        KHÔNG auto-fill profile từ dealer cũ (gây ô nhiễm data nếu trùng phone
        nhưng khác người). Chỉ:
        1. Mark `is_returning_dealer=True` (để bot greet đặc biệt)
        2. Verify owner_name nếu có — chỉ load nếu owner_name match

        Fix bug: phone trùng nhưng different dealer → KHÔNG load data sai.
        """
        if session.is_returning_dealer:
            return
        phone = (session.profile_raw.phone_or_zalo or "").strip()
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            return

        old_profile = self.storage.find_profile_by_phone(phone)
        if old_profile is None:
            return

        # SAFETY CHECK: nếu session HIỆN TẠI đã có owner_name, mà KHÁC owner_name
        # cũ → coi như là dealer khác dùng cùng số (hiếm), KHÔNG mark returning.
        current_owner = (session.profile_raw.owner_name or "").strip().lower()
        old_owner = (old_profile.owner_name or "").strip().lower()
        if current_owner and old_owner and current_owner != old_owner:
            # Tên khác hẳn → chắc chắn không phải cùng người. Bỏ qua.
            return

        # Phone match + tên ko mâu thuẫn → đánh dấu returning.
        # KHÔNG auto-fill profile data — để dealer tự xác nhận lại.
        # (Trước đây bug: auto-fill khiến confirm card hiển thị data người cũ.)
        session.is_returning_dealer = True

    def _merge_rule_based_intent(self, session: Session) -> None:
        """Regex bắt keyword phone/pain/priority từ message DEALER cuối cùng.

        Bot reply không tính. Chỉ áp khi field còn empty (không đè data LLM tốt).
        """
        latest_raw = ""
        for m in reversed(session.messages):
            if m.role == ChatRole.DEALER and (m.content or "").strip():
                latest_raw = m.content
                break
        if not latest_raw:
            return
        latest = latest_raw.lower()

        # PHONE regex: bắt số 9-11 chữ số bắt đầu bằng 0, có thể có dấu cách/dấu chấm/gạch
        if not session.profile_raw.phone_or_zalo:
            phone_match = re.search(r"(?<!\d)(0\d[\d\s.\-]{7,13}\d)(?!\d)", latest_raw)
            if phone_match:
                digits = re.sub(r"\D", "", phone_match.group(1))
                if 9 <= len(digits) <= 11:
                    session.profile_raw.phone_or_zalo = digits
                    session.confidence["phone_or_zalo"] = "HIGH"

        # PAIN keywords
        pain_keywords = [
            ("Khách cũ ít quay lại", ("khách cũ ít", "khach cu it", "khách cũ không quay",
                                       "khach cu khong quay")),
            ("Marketing yếu", ("marketing yếu", "marketing yeu", "quảng bá yếu",
                                "quang ba yeu", "không biết quảng bá", "khong biet quang ba")),
            ("Khó tìm khách", ("khó tìm khách", "kho tim khach", "thiếu khách",
                                "thieu khach", "ế ẩm", "e am", "vắng khách", "vang khach",
                                "ít khách", "it khach")),
            ("Đội thợ không ổn định", ("đội thợ", "doi tho", "thợ không ổn", "tho khong on",
                                         "thợ nghỉ", "tho nghi")),
            ("Thiếu vốn", ("thiếu tiền", "thieu tien", "hết tiền", "het tien",
                            "thiếu vốn", "thieu von", "không có vốn", "khong co von",
                            "kẹt tiền", "ket tien")),
            ("Dịch bệnh ảnh hưởng kinh doanh", ("dịch bệnh", "dich benh", "covid",
                                                  "dịch covid", "do dịch", "do dich")),
        ]
        # Bắt MULTIPLE pain trong 1 turn (max 3 mới mỗi turn để tránh nhiễu)
        # Dedupe: skip nếu existing pain đã cover keyword tương tự.
        new_pains_added = 0
        for label, kws in pain_keywords:
            if new_pains_added >= 3:
                break
            if any(kw in latest for kw in kws):
                pains = list(session.profile_raw.pain_points or [])
                # Check duplicate: existing pain text đã chứa keyword trong label?
                existing_text = " ".join(pains).lower()
                already_covered = any(kw in existing_text for kw in kws)
                if not already_covered and label not in pains:
                    pains.append(label)
                    new_pains_added += 1
                    session.profile_raw.pain_points = pains
                    session.confidence["pain_points"] = "HIGH"

        # PRIORITY keywords
        if any(neg in latest for neg in ("cái nào cũng được", "cai nao cung duoc",
                                          "gì cũng được", "gi cung duoc")):
            return  # mơ hồ → không suy ra priority
        priority_keywords = [
            ("qr_khach_cu", ("qr khách cũ", "qr khach cu", "qr gửi khách",
                              "qr gui khach", "qr khách", "qr khach")),
            ("bo_mat_so", ("bộ mặt số", "bo mat so", "mặt số", "mat so")),
            ("bai_dang", ("bài đăng", "bai dang", "đăng bài", "dang bai", "post bài")),
            ("tro_ly_tu_van", ("trợ lý tư vấn", "tro ly tu van", "trợ lý ai",
                                 "tro ly ai")),
        ]
        for value, kws in priority_keywords:
            if any(kw in latest for kw in kws):
                priorities = list(session.profile_raw.dl0_priority or [])
                if value not in priorities:
                    priorities.append(value)
                session.profile_raw.dl0_priority = priorities
                session.confidence["dl0_priority"] = "HIGH"
                break

    @staticmethod
    def _diff_new_fields(before: dict, after: dict) -> dict:
        """Trả dict các field THỰC SỰ MỚI fill ở turn này (Q1 fix).

        Quy tắc:
        - Scalar field: trống → có giá trị → coi là MỚI.
        - Scalar field: giá trị thay đổi (vd dealer correct) → coi là MỚI.
        - List field (pain_points/dl0_priority): list dài hơn → MỚI (item bổ sung).
        - Field giữ nguyên → KHÔNG MỚI, không vào dict.

        Mục đích: chống enforce_min_length prepend compliment khen field cũ
        (vd dealer vừa cho phone, bot đột ngột "Tên Dương đẹp quá!").
        """
        new_fields: dict = {}
        for field, after_val in after.items():
            before_val = before.get(field)
            # List field: chỉ coi là mới khi có item bổ sung
            if isinstance(after_val, list):
                before_list = before_val if isinstance(before_val, list) else []
                if len(after_val) > len(before_list):
                    new_fields[field] = after_val
                continue
            # Scalar: empty → filled, hoặc value thay đổi
            after_empty = after_val in (None, "", [])
            before_empty = before_val in (None, "", [])
            if after_empty:
                continue
            if before_empty or before_val != after_val:
                new_fields[field] = after_val
        return new_fields

    @staticmethod
    def _count_filled_required(session: Session) -> int:
        """Đếm số REQUIRED_FIELDS đã có giá trị thật (HIGH/MEDIUM, không LOW).

        Dùng làm thước đo "dealer đang hợp tác mức nào" cho re-ask logic.
        """
        profile_dict = session.profile_raw.model_dump()
        count = 0
        for field in REQUIRED_FIELDS:
            value = profile_dict.get(field)
            if value in (None, "", []):
                continue
            conf = session.confidence.get(field)
            if conf == "LOW":
                continue
            count += 1
        return count

    # Sau khi dealer fill thêm ≥ N field NEW so với lúc skip → field skip
    # được retry 1 lần. N=2 = "dealer trả lời 2 câu hỏi sau đó coi như cooperation".
    REASK_COOPERATION_THRESHOLD = 2

    def _weak_required_fields(self, session: Session) -> list[str]:
        """Field bắt buộc còn null hoặc confidence chưa đủ tin cậy.

        Logic skip:
        - Field trong skipped_fields → KHÔNG vào weak NẾU chưa đủ điều kiện re-ask.
        - Field đủ điều kiện re-ask (dealer đã fill thêm ≥2 field, chưa retry) →
          đẩy xuống CUỐI list (low priority — chỉ hỏi sau khi field ưu tiên hết).

        INTENT field accept MEDIUM nhờ rule-based regex bù.
        """
        weak: list[str] = []
        reaskable: list[str] = []  # field skip nhưng đủ điều kiện hỏi lại
        profile_dict = session.profile_raw.model_dump()
        filled_now = self._count_filled_required(session)

        for field in REQUIRED_FIELDS:
            if field in session.skipped_fields:
                # Đã retry rồi → bỏ luôn, không hỏi nữa
                if field in session.skipped_retried:
                    continue
                # Đủ điều kiện cooperation → đưa vào reaskable
                skipped_at = session.skipped_at_filled_count.get(field, filled_now)
                if filled_now - skipped_at >= self.REASK_COOPERATION_THRESHOLD:
                    reaskable.append(field)
                continue

            value = profile_dict.get(field)
            empty = value in (None, "", [])
            conf = session.confidence.get(field)
            if empty or conf == "LOW":
                weak.append(field)

        # Re-askable đẩy xuống cuối — ưu tiên field chưa từng hỏi trước
        return weak + reaskable

    @staticmethod
    def _tam_su_engagement(text: str) -> str:
        """Sinh 1 câu engagement đơn giản dựa trên keyword trong tâm sự message.

        Dùng khi LLM không sinh được confirm_questions cho turn tâm sự — bot
        không bị bơ hoàn toàn. Nếu không match keyword nào → trả "" (không prepend).
        """
        if not text:
            return ""
        low = text.lower()
        if any(k in low for k in ("vợ", "chồng", "cãi", "ny", "gấu", "gia đình")):
            return "Dạ chuyện vợ chồng cãi cọ thường thôi anh ơi 😊, em không tiện vào đâu. Cộng Đồng Thợ 4.0 bên em có nhiều anh em hay tụ cafe xả stress, anh thử join cho khuây khoả nhé."
        if any(k in low for k in ("nhậu", "say", "đau đầu rượu")):
            return "Hihi anh nhậu căng quá rồi 😂. Anh uống nước ép giải rượu cho khoẻ nhé."
        if any(k in low for k in ("bóng", "đá bóng", "tennis", "gym", "tập", "golf")):
            return "Wow anh khoẻ ghê, vận động xong nhìn vui lắm anh ạ 😊."
        if any(k in low for k in ("ốm", "bệnh", "viện", "đau ", "mệt")):
            return "Dạ em mong anh mau khoẻ lại ạ 🌷. Anh nhớ nghỉ ngơi nhé."
        if any(k in low for k in ("buồn", "chán", "stress", "căng thẳng", "khổ")):
            return "Dạ em hiểu mà anh, ai cũng có lúc thế thôi ạ 😔."
        if any(k in low for k in ("dịch bệnh", "ế ẩm", "khó khăn")):
            return "Dạ em đồng cảm với anh ạ, đợt này nhiều anh em làm nghề cũng kêu khó."
        if any(k in low for k in ("công trình", "lắp đặt", "đi khách")):
            return "Dạ anh đang trên công trình bận rộn em không làm phiền lâu đâu ạ 🌷."
        return ""

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
        session.llm_call_count += 1
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
            session.llm_call_count += 1
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
        session.llm_call_count += 1
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
