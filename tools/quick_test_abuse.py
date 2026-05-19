"""Test abuse + address blacklist 3 cấp live."""
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


# Scenario A: Abuse 3 cấp
print("=== SCENARIO A: Abuse 3 cấp ===")
r0 = post({"message": ""})
sid_a = r0["session_id"]
post({"session_id": sid_a, "message": "ok em làm đi"})

for i, msg in enumerate([
    "đm con bot này ngu vl",
    "bot ngu vcl đéo cho gì",
    "câm mồm đi đồ máy",
], start=1):
    r = post({"session_id": sid_a, "message": msg})
    print(f"  T{i+1}: {msg}")
    print(f"     → [{r['stage']}] {r['reply'][:150]}\n")

status = json.loads(urllib.request.urlopen(f"{BASE}/api/chat/{sid_a}/status").read())
print(f"  Flags: {status['flags']}")
print(f"  Stage: {status['stage']}\n")

# Scenario B: Address blacklist 3 lần
print("=== SCENARIO B: Address blacklist 3 lần ===")
r0 = post({"message": ""})
sid_b = r0["session_id"]
post({"session_id": sid_b, "message": "ok em làm đi"})
post({"session_id": sid_b, "message": "anh tên Tùng, Nhôm Kính Thanh Tùng"})

for i, msg in enumerate([
    "Lăng Bác Ba Đình Hà Nội",
    "Bác Hồ phường 5",
    "Đức Phật quận 10",
], start=1):
    r = post({"session_id": sid_b, "message": msg})
    print(f"  T{i+2}: {msg}")
    print(f"     → [{r['stage']}] {r['reply'][:150]}\n")

status = json.loads(urllib.request.urlopen(f"{BASE}/api/chat/{sid_b}/status").read())
print(f"  Flags: {status['flags']}")
print(f"  Stage: {status['stage']}\n")

# Queue
queue = admin_get("/api/admin/queue?status=PENDING")
print(f"\n=== Admin queue: {len(queue)} PENDING ===")
for q in queue:
    if q["session_id"] in (sid_a, sid_b):
        prefix = "A" if q["session_id"] == sid_a else "B"
        print(f"  [{prefix}] {q['session_id'][:8]}.. trigger={q['trigger']:>22s} priority={q['priority']}")
