"""Test phone invalid 3 lần → flag PHONE_INVALID_AFTER_RETRY + queue MED.

Scenario: dealer cho phone sai 3 lần, slot 1.3 SKIP sau retry exhausted.
"""
from __future__ import annotations

import base64
import json
import urllib.request


BASE = "http://127.0.0.1:8000"
ADMIN_AUTH = "Basic " + base64.b64encode(b"admin:duongdeptrai123").decode()


def post(body):
    req = urllib.request.Request(
        f"{BASE}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def admin_get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": ADMIN_AUTH})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


# Init
r0 = post({"message": ""})
sid = r0["session_id"]
print(f"Session: {sid}\n")

# Set up: tới slot 1.3
post({"session_id": sid, "message": "ok em làm đi"})
post({"session_id": sid, "message": "anh tên Tùng, cửa hàng Nhôm Kính Thanh Tùng"})
post({"session_id": sid, "message": "123 Lê Lợi Hoàn Kiếm Hà Nội"})

print("=== Đã setup tới slot 1.3 ===\n")

# 3 lần phone invalid
invalid_phones = [
    "abc xyz không có số",          # 1: empty digits
    "012345",                        # 2: quá ngắn (6 digit)
    "111111111111",                  # 3: 12 digit + repeat
]
for i, msg in enumerate(invalid_phones, start=1):
    r = post({"session_id": sid, "message": msg})
    print(f"─── Phone attempt #{i}: '{msg}' ───")
    print(f"[BOT]: {r['reply'][:250]}")
    print(f"  Slot={r['current_slot']}\n")

# Status
status = json.loads(
    urllib.request.urlopen(f"{BASE}/api/chat/{sid}/status").read()
)
print(f"Flags: {status['flags']}")
print(f"Slot: {status['current_slot']}")

# Admin queue
queue = admin_get("/api/admin/queue?status=PENDING")
print(f"\nAdmin queue PENDING entries for this session:")
for q in queue:
    if q["session_id"] == sid:
        print(f"  - trigger={q['trigger']} priority={q['priority']}")
