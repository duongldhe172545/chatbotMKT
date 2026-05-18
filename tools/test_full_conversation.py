"""Test 1 luồng trò chuyện full với Gemini API thật + đo chi phí.

Run: .venv/Scripts/python.exe tools/test_full_conversation.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Path setup
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Test DB tmp
os.environ["SQLITE_PATH"] = "data/test_full_conv.db"
test_db = ROOT / "data" / "test_full_conv.db"
if test_db.exists():
    test_db.unlink()
for suffix in ("-wal", "-shm"):
    p = ROOT / "data" / f"test_full_conv.db{suffix}"
    if p.exists():
        p.unlink()

# Clear LLM call log
log_path = ROOT / "logs" / "llm_calls.jsonl"
if log_path.exists():
    log_path.unlink()

# Reset singletons
from app.config import reset_settings
from app.llm.client import reset_default_client

reset_settings()
reset_default_client()

from app.core.conversation import handle_message, start_session
from app.core.session import create_session
from app.llm.client import LLMClient
from app.models.schema import DealerProfileRaw

# Init real Gemini client
client = LLMClient()

# Track timing
overall_start = time.monotonic()

# ============================================================
# Conversation
# ============================================================

session = create_session(channel="web", ip_address="127.0.0.1")
profile = DealerProfileRaw()

print("=" * 78)
print("EM LINH MKT v8 — TEST FULL CONVERSATION (Gemini API thật)")
print("=" * 78)
print(f"Session ID: {session.session_id}")
print()

# ===== TURN 0: greeting =====
print("─" * 78)
print(f"TURN 0 (init session)")
print("─" * 78)
greeting = start_session(session)
print(f"[BOT]:")
print(greeting)
print()
print(f"  [Stage: {session.stage.value}, Slot: {session.current_slot}]")
print()


def run_turn(turn_num: int, dealer_msg: str) -> None:
    """Chạy 1 turn + print + log."""
    print("─" * 78)
    print(f"TURN {turn_num}")
    print("─" * 78)
    print(f"[DEALER]: {dealer_msg}")
    print()
    t0 = time.monotonic()
    reply, _, _ = handle_message(session, profile, dealer_msg, client)
    elapsed = time.monotonic() - t0
    print(f"[BOT] ({elapsed:.1f}s):")
    print(reply)
    print()
    print(
        f"  [Stage: {session.stage.value} | Slot: {session.current_slot} | "
        f"Turn: {session.turn_count}]"
    )
    print(
        f"  [Profile: owner={profile.owner_name!r}, "
        f"dealer={profile.dealer_name!r}]"
    )
    print(
        f"           [addr={profile.address!r}, "
        f"consent={profile.brandkit_consent!r}]"
    )
    print()


# ===== TURN 1: ack greeting =====
run_turn(1, "OK em làm đi")

# ===== TURN 2: slot 1.1 (tên người + tên cửa hàng) =====
run_turn(2, "Anh tên Tùng, cửa hàng Nhôm Kính Thanh Tùng nha em")

# ===== TURN 3: slot 1.2 (địa chỉ + bán kính khách) =====
run_turn(
    3,
    "Cửa hàng anh ở 123 đường Lê Lợi, quận 1, TP.HCM. Khách thường đến từ "
    "bán kính 5km xung quanh",
)

# ===== Force jump tới slot 4.0 (Phase 1 chưa có extractor 1.3/2.1/2.2) =====
print("─" * 78)
print("[INTERNAL] Phase 1 không có extractor cho slot 1.3/2.1/2.2/2.x/3.x")
print("           Skip qua để test luôn 4.0 (consent) → CONFIRMING.")
print("─" * 78)
session.skipped_slots.extend(["1.3", "2.1", "2.2", "2.3", "2.4", "2.5",
                              "2.6", "3.1", "3.2", "3.3", "3.4", "3.5"])
session.current_slot = "4.0"
print()

# ===== TURN 4: slot 4.0 consent =====
run_turn(4, "OK em làm đi, anh đồng ý nhận bộ thương hiệu")

# ===== Force advance: 4.0 → 4.1 (thông báo logo) =====
# Note: Bot ack consent + ask 4.1 logo. Dealer ack 4.1 → advance 4.2.
# Phase 1 skip 4.2 (chưa có extractor). → CONFIRMING.

# ===== TURN 5: ack slot 4.1 =====
session.skipped_slots.append("4.2")
run_turn(5, "vâng em cứ chọn cho anh")

# ===== TURN 6: confirm card =====
run_turn(6, "đúng rồi em, chốt vậy đi")

# ============================================================
# Final state
# ============================================================
overall_elapsed = time.monotonic() - overall_start
print("=" * 78)
print("FINAL STATE")
print("=" * 78)
print(f"Total elapsed: {overall_elapsed:.1f}s")
print(f"Final stage: {session.stage.value}")
print(f"Total turns: {session.turn_count}")
print(f"Confirmation status: {session.confirmation_status.value}")
print(f"Flags: {[f.value for f in session.flags]}")
print(f"Skipped slots: {session.skipped_slots}")
print()
print("Profile extracted:")
print(f"  owner_name:   {profile.owner_name!r}")
print(f"  dealer_name:  {profile.dealer_name!r}")
print(f"  address:      {profile.address!r}")
print(f"  brandkit_consent: {profile.brandkit_consent!r}")
print(f"  local_dominance_signal: {profile.local_dominance_signal!r}")

# ============================================================
# Cost calculation
# ============================================================
print()
print("=" * 78)
print("LLM USAGE + COST")
print("=" * 78)

# Gemini pricing (cập nhật 2026-05, https://ai.google.dev/pricing)
# Gemini 2.5 Flash: $0.30 / 1M input tokens, $2.50 / 1M output tokens
# Gemini 2.5 Pro:   $1.25 / 1M input tokens, $10.00 / 1M output tokens
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}
USD_TO_VND = 25500  # rough

total_in = 0
total_out = 0
per_model_in = {}
per_model_out = {}
calls = []

if log_path.exists():
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        calls.append(entry)
        model = entry.get("model", "unknown")
        in_tok = entry.get("input_tokens") or 0
        out_tok = entry.get("output_tokens") or 0
        total_in += in_tok
        total_out += out_tok
        per_model_in[model] = per_model_in.get(model, 0) + in_tok
        per_model_out[model] = per_model_out.get(model, 0) + out_tok

print(f"Total LLM calls: {len(calls)}")
print(f"Total input tokens:  {total_in:,}")
print(f"Total output tokens: {total_out:,}")
print()

total_usd = 0.0
print(f"{'Model':<25} {'Calls':>6} {'In':>10} {'Out':>10} {'Cost USD':>12}")
print(f"{'-' * 25} {'-' * 6} {'-' * 10} {'-' * 10} {'-' * 12}")
for model in sorted(set(list(per_model_in.keys()) + list(per_model_out.keys()))):
    n_calls = sum(1 for c in calls if c.get("model") == model)
    in_tok = per_model_in.get(model, 0)
    out_tok = per_model_out.get(model, 0)
    pricing = PRICING.get(model, {"input": 0, "output": 0})
    cost = (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000
    total_usd += cost
    print(
        f"{model:<25} {n_calls:>6} {in_tok:>10,} {out_tok:>10,} "
        f"${cost:>10.6f}"
    )

print(f"{'-' * 25} {'-' * 6} {'-' * 10} {'-' * 10} {'-' * 12}")
print(
    f"{'TOTAL':<25} {len(calls):>6} {total_in:>10,} {total_out:>10,} "
    f"${total_usd:>10.6f}"
)
print()
print(f"≈ {total_usd * USD_TO_VND:,.0f} VND (rate 1 USD = {USD_TO_VND:,} VND)")
print()

# Breakdown per call
if calls:
    print("Detail per call:")
    print(f"{'Method':<25} {'Model':<22} {'In':>6} {'Out':>6} {'ms':>6}")
    for c in calls:
        method = c.get("method", "?")[:24]
        model = c.get("model", "?")[:21]
        ti = c.get("input_tokens") or 0
        to_ = c.get("output_tokens") or 0
        dur = c.get("duration_ms") or 0
        print(f"{method:<25} {model:<22} {ti:>6} {to_:>6} {dur:>6}")
