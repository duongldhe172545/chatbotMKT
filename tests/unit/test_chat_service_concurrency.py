"""P2 — concurrency: LLM moved OUT of the DB write transaction (2026-06-10).

`send_text_message` now runs as 3 short write transactions with the LLM work
in between (no lock held during Gemini calls). These tests prove:
- a single send still produces a bot reply (3-phase split didn't break the flow),
- concurrent sends across sessions don't collide on `event_cursor` and don't
  raise IntegrityError / 'database is locked' (BEGIN IMMEDIATE serializes the
  short writes → MAX()+1 stays safe).

Runs with CONVERSATION_RUNTIME=stub + empty Gemini key → deterministic, no API.
"""
from __future__ import annotations

import threading

from app.core.config_v2 import Settings
from app.db.connection import Database
from app.db.store import Store
from app.services.chat_service import ChatService


def _make_service(tmp_path):
    db_file = str(tmp_path / "concur.sqlite3")
    db = Database(db_file)
    db.initialize()
    store = Store(db)
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        conversation_runtime="stub",
        gemini_api_key="",
    )
    svc = ChatService(store=store, settings=settings)
    # Warm the lazy TurnProcessor (loads YAML once) before spawning threads.
    _ = svc.turn_processor
    return svc, store, db


def _new_session(store, db, i: int) -> str:
    with db.transaction() as conn:
        row = store.create_session(
            conn,
            channel="web",
            token_hash=f"tok-{i}",
            ip_hash=None,
            user_agent_hash=None,
            metadata={},
        )
        return row["id"]


def test_single_send_produces_reply(tmp_path):
    svc, store, db = _make_service(tmp_path)
    sid = _new_session(store, db, 0)
    result = svc.send_text_message(
        session_id=sid, text="alo em ơi", client_message_id="m0"
    )
    assert result["events"], "không sinh được reply"
    assert result["turn_id"]
    assert result["user_message_id"]
    assert result["session_id"] == sid


def test_concurrent_sends_no_cursor_collision(tmp_path):
    svc, store, db = _make_service(tmp_path)
    n_sessions = 8
    msgs_per = 4
    sessions = [_new_session(store, db, i) for i in range(n_sessions)]
    errors: list[Exception] = []

    def worker(sid: str):
        try:
            for j in range(msgs_per):
                svc.send_text_message(
                    session_id=sid, text=f"tin nhắn {j}", client_message_id=f"{sid}-{j}"
                )
        except Exception as exc:  # pragma: no cover - only on failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(s,)) for s in sessions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"gửi song song bị lỗi: {errors!r}"

    with db.transaction() as conn:
        cursors = [
            r["event_cursor"]
            for r in conn.execute("SELECT event_cursor FROM messages")
        ]
        n_turns = conn.execute(
            "SELECT COUNT(*) AS c FROM conversation_turns"
        ).fetchone()["c"]

    # Mọi cursor message là duy nhất toàn cục — không có đua MAX()+1.
    assert len(cursors) == len(set(cursors)), "PHÁT HIỆN cursor collision!"
    # Mỗi send = 1 user msg + 1 bot msg.
    assert len(cursors) == n_sessions * msgs_per * 2
    assert n_turns == n_sessions * msgs_per
