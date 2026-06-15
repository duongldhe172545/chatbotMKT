"""Load test Em Linh MKT — P3.5 (sự kiện ~100 người cùng lúc).

Stdlib thuần (không cần cài gì). Mỗi VU (virtual user):
  1. POST /api/v1/sessions  → lấy session + token
  2. Gửi N lượt chat; lượt ĐẦU đồng loạt cả đàn (Barrier) = burst xấu nhất,
     các lượt sau cách nhau --pace giây (nhịp người thật).

Chạy:
  # Vòng 1 — stub (đo khung app/DB, không gọi Gemini):
  python scripts/load_test.py --base-url http://127.0.0.1:8083 --users 100 --turns 3 --pace 0.5

  # Vòng 2 — server bật CONVERSATION_RUNTIME=gemini (đo end-to-end thật):
  python scripts/load_test.py --base-url http://127.0.0.1:8083 --users 100 --turns 5 --pace 15

Tiêu chí đậu (KE_HOACH_TONG P3.5): p95 ≤ 10s ở burst, error < 1%,
0 'database is locked' / db_busy, không bão 429.
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
import uuid

RESULTS_LOCK = threading.Lock()
RESULTS: list[dict] = []  # {vu, turn, status, latency_s, error_code}

TURN_TEXTS = [
    "chào em",
    "anh là Hùng, cửa hàng nhôm kính Hùng Phát",
    "ở Hà Đông, Hà Nội",
    "0912345678",
    "anh làm cửa nhôm với cửa cuốn",
    "có xưởng, tự sản xuất thi công",
    "4 thợ em ạ",
    "nhập Xingfa là chính",
    "khách hay gọi Zalo",
    "không có facebook",
]


def _post(url: str, body: dict, headers: dict | None = None, timeout: float = 60.0):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload, time.monotonic() - start
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        return exc.code, payload, time.monotonic() - start
    except Exception as exc:  # timeout / connection refused
        return 0, {"error": {"code": type(exc).__name__}}, time.monotonic() - start


def _record(vu: int, turn: int, status: int, latency: float, payload: dict):
    code = ""
    if status != 200:
        code = (payload.get("error") or {}).get("code", str(status))
    with RESULTS_LOCK:
        RESULTS.append(
            {"vu": vu, "turn": turn, "status": status, "latency_s": latency, "error_code": code}
        )


def run_vu(vu: int, base: str, turns: int, pace: float, barrier: threading.Barrier):
    status, payload, latency = _post(f"{base}/api/v1/sessions", {"channel": "web_text"})
    _record(vu, -1, status, latency, payload)
    if status != 200:
        return
    data = payload["data"]
    sid, tok = data["session_id"], data["session_token"]

    for turn in range(turns):
        if turn == 0:
            try:
                barrier.wait(timeout=120)  # BURST: cả đàn bắn cùng tích tắc
            except threading.BrokenBarrierError:
                pass
        else:
            time.sleep(pace)
        text = TURN_TEXTS[turn % len(TURN_TEXTS)]
        status, payload, latency = _post(
            f"{base}/api/v1/sessions/{sid}/messages",
            {"message_type": "text", "text": text},
            headers={
                "Authorization": f"Bearer {tok}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        _record(vu, turn, status, latency, payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8083")
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--pace", type=float, default=0.5, help="giây giữa các lượt sau burst")
    args = ap.parse_args()

    print(f"== LOAD TEST: {args.users} VU x {args.turns} lượt, burst lượt đầu, pace {args.pace}s ==")
    barrier = threading.Barrier(args.users)
    threads = [
        threading.Thread(
            target=run_vu, args=(i, args.base_url.rstrip("/"), args.turns, args.pace, barrier)
        )
        for i in range(args.users)
    ]
    wall_start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - wall_start

    msgs = [r for r in RESULTS if r["turn"] >= 0]
    sess = [r for r in RESULTS if r["turn"] == -1]
    ok = [r for r in msgs if r["status"] == 200]
    errors = [r for r in msgs if r["status"] != 200]
    burst = [r for r in msgs if r["turn"] == 0 and r["status"] == 200]

    def pct(values, p):
        if not values:
            return 0.0
        values = sorted(values)
        return values[min(len(values) - 1, int(len(values) * p / 100))]

    lat = [r["latency_s"] for r in ok]
    burst_lat = [r["latency_s"] for r in burst]

    print(f"\nTổng thời gian: {wall:.1f}s")
    print(f"Session tạo:   {sum(1 for r in sess if r['status']==200)}/{len(sess)} OK")
    print(f"Message:       {len(ok)}/{len(msgs)} OK  ({len(errors)} lỗi = {100*len(errors)/max(1,len(msgs)):.1f}%)")
    if lat:
        print(f"Latency ALL:   p50={pct(lat,50):.2f}s  p95={pct(lat,95):.2f}s  p99={pct(lat,99):.2f}s  max={max(lat):.2f}s")
    if burst_lat:
        print(f"Latency BURST: p50={pct(burst_lat,50):.2f}s  p95={pct(burst_lat,95):.2f}s  max={max(burst_lat):.2f}s")
    if errors:
        breakdown: dict[str, int] = {}
        for r in errors:
            key = f"{r['status']}:{r['error_code']}"
            breakdown[key] = breakdown.get(key, 0) + 1
        print(f"Lỗi breakdown: {breakdown}")

    locked = [r for r in errors if "db_busy" in r["error_code"] or "locked" in r["error_code"].lower()]
    rate429 = [r for r in errors if r["status"] == 429]
    p95_burst = pct(burst_lat, 95) if burst_lat else 0.0
    err_rate = len(errors) / max(1, len(msgs))

    print("\n== TIÊU CHÍ ĐẬU (KE_HOACH_TONG P3.5) ==")
    print(f"  p95 burst ≤ 10s:        {'✅' if p95_burst <= 10 else '❌'} ({p95_burst:.2f}s)")
    print(f"  error rate < 1%:        {'✅' if err_rate < 0.01 else '❌'} ({100*err_rate:.1f}%)")
    print(f"  0 database-locked:      {'✅' if not locked else f'❌ ({len(locked)})'}")
    print(f"  không bão 429:          {'✅' if len(rate429) < max(1, len(msgs)//100) else f'❌ ({len(rate429)})'}")


if __name__ == "__main__":
    main()
