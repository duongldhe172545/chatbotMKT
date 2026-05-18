"""Seed 1 CONFIRMED session vào main DB cho admin UI có data demo."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.core.session import create_session
from app.models.enums import ConfirmationStatus, DealerType, ReviewStatus, Stage
from app.models.schema import DealerProfileRaw, HistoryMessage
from app.storage.sqlite_store import SQLiteStore

settings = get_settings()
print(f"DB: {settings.SQLITE_PATH}")
store = SQLiteStore(settings.SQLITE_PATH)

# ===== Session 1: CONFIRMED + đầy đủ =====
session = create_session(channel="web", ip_address="192.168.1.100")
session.stage = Stage.DONE
session.confirmation_status = ConfirmationStatus.CONFIRMED
session.review_status = ReviewStatus.RAW
session.detected_dealer_type = DealerType.KHOE
session.turn_count = 14
now = datetime.now(timezone.utc)
session.closed_at = now
session.updated_at = now
session.created_at = now - timedelta(minutes=12)

# Mini history
session.history = [
    HistoryMessage(role="bot", content="Dạ em chào anh! Em là Linh...",
                   ts=session.created_at),
    HistoryMessage(role="dealer", content="OK em làm đi",
                   ts=session.created_at + timedelta(seconds=30)),
    HistoryMessage(role="bot", content="Đầu tiên cho em xin tên anh và tên cửa hàng ạ.",
                   ts=session.created_at + timedelta(seconds=32)),
    HistoryMessage(role="dealer", content="Anh tên Tùng, Nhôm Kính Thanh Tùng",
                   ts=session.created_at + timedelta(minutes=1)),
    HistoryMessage(role="bot", content="Dạ em note anh Tùng. Địa chỉ cửa hàng anh ở đâu ạ?",
                   ts=session.created_at + timedelta(minutes=1, seconds=3)),
    HistoryMessage(role="dealer", content="123 Lê Lợi quận 1 TP.HCM",
                   ts=session.created_at + timedelta(minutes=2)),
    HistoryMessage(
        role="bot",
        content="Em xác nhận: anh Tùng — Nhôm Kính Thanh Tùng — 123 Lê Lợi Q.1 TP.HCM — đúng không ạ?",
        ts=session.created_at + timedelta(minutes=11),
    ),
    HistoryMessage(role="dealer", content="đúng rồi em chốt",
                   ts=session.created_at + timedelta(minutes=11, seconds=30)),
]

profile = DealerProfileRaw(
    owner_name="Tùng",
    dealer_name="Nhôm Kính Thanh Tùng",
    address="123 Lê Lợi, Quận 1, TP.HCM",
    phone_or_zalo="0912345678",
    main_product="cửa nhôm kính",
    business_model_signal="bán + thi công",
    customer_radius_km=5,
    est_team_size=3,
    supplier_brands=["Xingfa", "PMA"],
    province="TP.HCM",
    category_stack=["cua_nhom_kinh"],
    brandkit_consent="yes",
    slogan_options=[
        "Cửa nhôm kính Thanh Tùng — bền đẹp Sài Gòn",
        "Thanh Tùng — kính bền, nhôm chuẩn, khách bền lâu",
        "Cửa đẹp khởi đầu từ Thanh Tùng",
    ],
)

store.save_session(session)
store.save_profile(session.session_id, profile)
print(f"Session 1 (CONFIRMED): {session.session_id}")

# ===== Session 2: ASKING + dealer type Lửa Lò =====
s2 = create_session(channel="zalo", ip_address="10.0.0.5")
s2.stage = Stage.ASKING
s2.current_slot = "1.2"
s2.detected_dealer_type = DealerType.LUA_LO
s2.turn_count = 3
s2.created_at = now - timedelta(minutes=5)
s2.updated_at = now - timedelta(minutes=1)
s2.history = [
    HistoryMessage(role="bot", content="Dạ em chào anh...",
                   ts=s2.created_at),
    HistoryMessage(role="dealer", content="ờ", ts=s2.created_at + timedelta(seconds=20)),
    HistoryMessage(role="bot", content="Em xin tên anh + cửa hàng ạ?",
                   ts=s2.created_at + timedelta(seconds=22)),
    HistoryMessage(role="dealer", content="đm hỏi nhanh đi",
                   ts=s2.created_at + timedelta(minutes=1)),
]
p2 = DealerProfileRaw(owner_name="Hùng", dealer_name="Nhôm Kính Hùng Gia")
store.save_session(s2)
store.save_profile(s2.session_id, p2)
print(f"Session 2 (ASKING, lua_lo): {s2.session_id}")

# ===== Session 3: CONFIRMED Lo type =====
s3 = create_session(channel="web", ip_address="192.168.1.200")
s3.stage = Stage.DONE
s3.confirmation_status = ConfirmationStatus.CONFIRMED
s3.review_status = ReviewStatus.RAW
s3.detected_dealer_type = DealerType.LO
s3.turn_count = 18
s3.created_at = now - timedelta(hours=2)
s3.updated_at = now - timedelta(hours=1, minutes=45)
s3.closed_at = s3.updated_at
s3.history = [
    HistoryMessage(role="bot", content="Em là Linh ạ...", ts=s3.created_at),
    HistoryMessage(role="dealer", content="Em là ai? Có lừa đảo không?",
                   ts=s3.created_at + timedelta(seconds=10)),
    HistoryMessage(role="bot", content="Dạ không ạ, em chỉ giúp anh dựng hồ sơ thôi.",
                   ts=s3.created_at + timedelta(seconds=12)),
]
p3 = DealerProfileRaw(
    owner_name="Lan",
    dealer_name="Cửa Cuốn Lan Anh",
    address="56 Trần Hưng Đạo, Quận 5, TP.HCM",
    phone_or_zalo="0987654321",
    main_product="cửa cuốn",
    business_model_signal="thi công công trình",
    customer_radius_km=10,
    est_team_size=8,
    province="TP.HCM",
    category_stack=["cua_cuon"],
    brandkit_consent="no",
)
store.save_session(s3)
store.save_profile(s3.session_id, p3)
print(f"Session 3 (CONFIRMED, lo, no consent): {s3.session_id}")

print()
print("Seeded 3 sessions vào main DB. Admin nên thấy:")
print("  - Sessions tab: 4 session (3 seed + 1 HTTP)")
print("  - Đã chốt tab: 2 session CONFIRMED")
