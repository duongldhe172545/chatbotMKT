"""Test full conversation 15 turn qua HTTP — kịch bản dealer Khoe.

Server phải đang chạy ở 127.0.0.1:8000. Session sẽ lưu vào data/chatbot.db.

Kịch bản (refer luồng chat lý tưởng anh đã duyệt):
- Anh Tùng, chủ Nhôm Kính Thanh Tùng, HN Hoàn Kiếm
- Bán Xingfa + PMA, 2 thợ chính 4-5 năm
- 60-70% khách cũ giới thiệu
- Pain: khó nhớ lịch sử khách cũ
- Dealer type expected: Khoe (detect turn 8)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8000"


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}")
        raise


def turn(session_id: str | None, msg: str) -> dict:
    body = {"message": msg}
    if session_id:
        body["session_id"] = session_id
    return _post("/api/chat", body)


# ============================================================
print("=" * 78)
print("TEST FULL 15-TURN — kịch bản dealer Khoe (anh Tùng, Nhôm Kính Thanh Tùng)")
print("=" * 78)

t_start = time.monotonic()

# Turn 0 — init session
print("\n─── TURN 0 (init) ───")
r0 = turn(None, "")
sid = r0["session_id"]
print(f"Session: {sid}")
print(f"[BOT] (greeting): {r0['reply'][:300]}...")
print(f"  stage={r0['stage']} slot={r0.get('current_slot')}")

# Kịch bản đầy đủ 1.1 → 1.2 → ... → 4.2 → CONFIRMING → DONE
msgs = [
    # T1: ack greeting
    "ok em làm đi",
    # T2: tên + cửa hàng (slot 1.1)
    "anh tên Tùng, cửa hàng Nhôm Kính Thanh Tùng nha em",
    # T3: địa chỉ + bán kính (slot 1.2)
    "123 Lê Lợi, Hoàn Kiếm, Hà Nội. khách quanh phố thôi chừng 3km",
    # T4: SĐT (slot 1.3)
    "0912 345 678",
    # T5: sản phẩm chính (slot 2.1) — auto-derive main_category
    "nhôm kính là chính, đặc biệt cửa sổ hệ Xingfa. thi thoảng làm vách kính lớn cho dự án",
    # T6: mô hình KD (slot 2.2)
    "anh bán + thi công luôn, đội anh tự lắp được hệ Xingfa",
    # T7: đội thợ (slot 2.3) — KHOE signal mạnh, detect turn 8
    "có 2 thợ chính làm với anh 4-5 năm rồi, thêm 1-2 thợ vặt theo dự án. cái này anh tự hào nhất đấy, không phải chỗ nào cũng giữ được thợ",
    # T8: hãng nhập (slot 2.4)
    "xingfa là chính, mấy năm gần đây em thử thêm PMA cho phân khúc thấp hơn. có 2 nhà phân phối anh quen thân",
    # T9: kênh khách (slot 2.5)
    "khách cũ giới thiệu là chính, có Facebook nhưng anh ít chăm",
    # T10: FB + network (slot 2.6)
    "chung facebook cá nhân thôi. có vài anh em thợ khác hay giới thiệu khách qua, anh cũng giới thiệu lại",
    # T11: tỉ lệ khách cũ (slot 3.1)
    "60-70% là khách cũ giới thiệu hoặc quay lại",
    # T12: storage method (slot 3.2)
    "ghi sổ với lưu trong Zalo thôi, chưa có file Excel",
    # T13: pain (slot 3.3) — re-confirm Khoe turn 13
    "chính ra là cái việc nhớ tên khách nào đã mua gì khi nào. nhiều khi khách gọi lại sau 2 năm anh không nhớ ra đã làm gì cho họ. nói thực anh cũng đang muốn có cái gì đó tra cứu nhanh",
    # T14: cọc + công nợ (slot 3.4)
    "anh cọc 50% lúc ký, hết sau khi bàn giao xong. khách quen có thể nợ 1-2 tuần",
    # T15: bảo hành (slot 3.5)
    "anh đứng ra ký bảo hành cho khách, mình chịu trách nhiệm chính",
    # T16: consent brandkit (slot 4.0)
    "ok em làm bộ thương hiệu đó cho anh",
    # T17: ack thông báo logo (slot 4.1)
    "ờ ok em chọn cho anh",
    # T18: màu + phong thủy (slot 4.2)
    "anh thích xanh dương, không quan tâm phong thủy mấy",
    # T19: CONFIRMING — chốt card
    "đúng rồi em, chốt vậy đi",
]

for i, m in enumerate(msgs, start=1):
    print(f"\n─── TURN {i} ───")
    print(f"[DEALER]: {m}")
    t0 = time.monotonic()
    try:
        r = turn(sid, m)
    except Exception as e:
        print(f"[ERR]: {e}")
        break
    dur = time.monotonic() - t0
    print(f"[BOT] ({dur:.1f}s):\n{r['reply']}")
    print(f"  stage={r['stage']} slot={r.get('current_slot')}")
    if r["stage"] == "DONE":
        print("\n>>> DONE — session closed <<<")
        break

# Final status
print("\n─── FINAL STATUS ───")
status = json.loads(
    urllib.request.urlopen(f"{BASE}/api/chat/{sid}/status").read()
)
print(json.dumps(status, indent=2, ensure_ascii=False))

elapsed = time.monotonic() - t_start
print(f"\nTotal elapsed: {elapsed:.1f}s")
print(f"Session ID for admin: {sid}")
print(f"Admin URL: http://127.0.0.1:8000/admin")
