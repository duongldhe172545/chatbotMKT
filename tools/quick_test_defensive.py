"""Test defensive escalation 3 cấp live qua HTTP.

Scenario: dealer nói defensive 3 turn → L1 → L2 → L3 (soft-end + queue HIGH).
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

# T1: ack greeting
post({"session_id": sid, "message": "ok em làm đi"})

# 3 lần defensive
defensive_messages = [
    "em là ai? bot à? lừa đảo à?",
    "công ty nào? có an toàn không?",
    "bán data hay sao? tin được không?",
]
for i, msg in enumerate(defensive_messages, start=1):
    r = post({"session_id": sid, "message": msg})
    print(f"─── T{i+1} defensive #{i} ───")
    print(f"[DEALER]: {msg}")
    print(f"[BOT]: {r['reply'][:300]}")
    print(f"  Stage={r['stage']}\n")

# Status
status = json.loads(
    urllib.request.urlopen(f"{BASE}/api/chat/{sid}/status").read()
)
print(f"Flags: {status['flags']}")
print(f"Stage: {status['stage']}")

# Admin queue
queue = admin_get("/api/admin/queue?status=PENDING")
print(f"\nAdmin queue PENDING:")
for q in queue:
    if q["session_id"] == sid:
        print(f"  - trigger={q['trigger']} priority={q['priority']}")
