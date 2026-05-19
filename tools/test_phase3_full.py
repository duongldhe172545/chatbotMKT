"""Phase 3 R10 — 5 scenario end-to-end (Gemini API thật).

Cover full Phase 3 spec:
1. CLEAN — dealer Khoe đầy đủ
2. DEFENSIVE 3 lần → escalation L3
3. ABUSE cá nhân 3 lần → escalation L3
4. ADDRESS BLACKLIST 3 lần → escalation L3
5. EDIT trong CONFIRMING — dealer sửa SĐT trên card
"""
from __future__ import annotations

import base64
import json
import time
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


def get_status(sid):
    return json.loads(urllib.request.urlopen(f"{BASE}/api/chat/{sid}/status").read())


def init_session():
    return post({"message": ""})["session_id"]


def turn(sid, msg, label=""):
    t0 = time.monotonic()
    r = post({"session_id": sid, "message": msg})
    dur = time.monotonic() - t0
    if label:
        print(f"  ({dur:.1f}s) {label}: {msg[:60]}")
        print(f"    → [{r['stage']}/{r.get('current_slot')}] {r['reply'][:150]}")
    return r


def check(cond, msg):
    mark = "✓" if cond else "✗ FAIL"
    print(f"  {mark} {msg}")
    return cond


# ============================================================
# S1 — CLEAN dealer Khoe đầy đủ
# ============================================================


def scenario_1():
    print("\n" + "=" * 70)
    print("S1 CLEAN — Dealer Khoe đầy đủ 19 turn")
    print("=" * 70)
    sid = init_session()
    print(f"sid={sid[:8]}")

    msgs = [
        "ok em làm đi",
        "anh tên Tùng, Nhôm Kính Thanh Tùng",
        "123 Lê Lợi Hoàn Kiếm Hà Nội 3km",
        "0912345678",
        "nhôm kính Xingfa",
        "bán + thi công",
        "2 thợ 4-5 năm anh tự hào",
        "Xingfa PMA 2 NPP",
        "khách cũ giới thiệu",
        "FB cá nhân, thợ giới thiệu",
        "60-70%",
        "sổ Zalo",
        "khó nhớ khách cũ",
        "cọc 50%",
        "anh ký bảo hành",
        "ok em làm",
        "ok em chọn",
        "xanh dương",
        "đúng rồi em chốt",
    ]
    for m in msgs:
        turn(sid, m)
    s = get_status(sid)
    print(f"\nFlags: {s['flags']}, Stage: {s['stage']}")
    check(s["stage"] == "DONE", "Stage = DONE")
    check(s["confirmation_status"] == "CONFIRMED", "CONFIRMED")
    return sid


# ============================================================
# S2 — DEFENSIVE 3 lần
# ============================================================


def scenario_2():
    print("\n" + "=" * 70)
    print("S2 DEFENSIVE 3 lần → escalation L3")
    print("=" * 70)
    sid = init_session()
    turn(sid, "ok em làm đi")
    for i, msg in enumerate([
        "em là ai? bot à?",
        "lừa đảo à? công ty nào?",
        "có an toàn không? bán data hay sao?",
    ], 1):
        turn(sid, msg, f"T{i+1} defensive")
    s = get_status(sid)
    check(s["stage"] == "DONE", "Stage = DONE")
    check("escalation" in s["flags"], "Flag escalation")
    queue = admin_get("/api/admin/queue?status=PENDING")
    triggers = {q["trigger"] for q in queue if q["session_id"] == sid}
    check("escalation" in triggers, "Queue trigger=escalation HIGH")
    return sid


# ============================================================
# S3 — ABUSE cá nhân 3 lần
# ============================================================


def scenario_3():
    print("\n" + "=" * 70)
    print("S3 ABUSE cá nhân 3 lần → escalation L3")
    print("=" * 70)
    sid = init_session()
    turn(sid, "ok em làm đi")
    for i, msg in enumerate([
        "đm con bot này",
        "bot ngu vcl",
        "câm mồm đi đồ máy",
    ], 1):
        turn(sid, msg, f"T{i+1} abuse")
    s = get_status(sid)
    check(s["stage"] == "DONE", "Stage = DONE")
    check("abusive_language" in s["flags"], "Flag abusive_language")
    check("escalation" in s["flags"], "Flag escalation")
    queue = admin_get("/api/admin/queue?status=PENDING")
    triggers = {q["trigger"] for q in queue if q["session_id"] == sid}
    check("abusive_language" in triggers, "Queue trigger=abusive_language")
    check("escalation" in triggers, "Queue trigger=escalation")
    return sid


# ============================================================
# S4 — ADDRESS BLACKLIST 3 lần
# ============================================================


def scenario_4():
    print("\n" + "=" * 70)
    print("S4 ADDRESS BLACKLIST 3 lần → escalation L3")
    print("=" * 70)
    sid = init_session()
    turn(sid, "ok em làm đi")
    turn(sid, "anh tên Tùng, Nhôm Kính Thanh Tùng")
    for i, msg in enumerate([
        "Lăng Bác Ba Đình Hà Nội",
        "Bác Hồ phường 5",
        "Đức Phật quận 10",
    ], 1):
        turn(sid, msg, f"T{i+2} address_bl")
    s = get_status(sid)
    check(s["stage"] == "DONE", "Stage = DONE")
    check("address_blacklist" in s["flags"], "Flag address_blacklist")
    check("escalation" in s["flags"], "Flag escalation")
    return sid


# ============================================================
# S5 — EDIT trong CONFIRMING
# ============================================================


def scenario_5():
    print("\n" + "=" * 70)
    print("S5 EDIT — dealer sửa SĐT trong CONFIRMING")
    print("=" * 70)
    sid = init_session()
    # Setup: chạy fast tới CONFIRMING
    setup_msgs = [
        "ok em làm đi",
        "anh tên Tùng, Nhôm Kính Thanh Tùng",
        "123 Lê Lợi Hoàn Kiếm Hà Nội 3km",
        "0912345678",
        "nhôm kính Xingfa",
        "bán + thi công",
        "2 thợ",
        "Xingfa",
        "Zalo",
        "FB cá nhân",
        "60%",
        "sổ",
        "khó nhớ khách",
        "cọc 50%",
        "anh ký",
        "ok",
        "ok",
        "xanh",
    ]
    for m in setup_msgs:
        turn(sid, m)
    s = get_status(sid)
    print(f"  Setup done, stage={s['stage']}")
    if s["stage"] != "CONFIRMING":
        print("  ⚠ Setup không đến CONFIRMING — skip edit test")
        return sid

    # EDIT
    r = turn(sid, "sửa SĐT thành 0987654321", label="T_edit")
    check(
        "0987654321" in r["reply"] or "đã cập nhật" in r["reply"].lower(),
        "Bot ack edit SĐT",
    )
    # Confirm sau edit
    turn(sid, "đúng rồi em chốt")
    s = get_status(sid)
    check(s["stage"] == "DONE", "Sau edit + confirm → DONE")
    return sid


# ============================================================
# MAIN
# ============================================================


if __name__ == "__main__":
    print("\nPhase 3 R10 — 5 scenario full coverage")
    t0 = time.monotonic()
    for fn in [scenario_1, scenario_2, scenario_3, scenario_4, scenario_5]:
        try:
            fn()
        except Exception as e:
            print(f"  ✗ Exception: {type(e).__name__}: {e}")
    print(f"\nTotal: {time.monotonic()-t0:.1f}s")
    print(f"Admin: {BASE}/admin")
