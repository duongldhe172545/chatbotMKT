"""Profile CPU cua 1 luot chat stub — tim hot spot truoc khi toi uu (P3.5)."""
from __future__ import annotations

import cProfile
import pstats
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config_v2 import Settings
from app.db.connection import Database
from app.db.store import Store
from app.services.chat_service import ChatService

N_TURNS = 50


def main():
    tmp = tempfile.mkdtemp()
    db = Database(str(Path(tmp) / "prof.sqlite3"))
    db.initialize()
    store = Store(db)
    settings = Settings(
        database_url="sqlite:///x", conversation_runtime="stub", gemini_api_key=""
    )
    svc = ChatService(store=store, settings=settings)
    with db.transaction() as conn:
        sid = store.create_session(
            conn, channel="web", token_hash="t", ip_hash=None,
            user_agent_hash=None, metadata={},
        )["id"]

    # warm-up (load YAML/cache)
    svc.send_text_message(session_id=sid, text="warmup", client_message_id="w")

    pr = cProfile.Profile()
    pr.enable()
    for i in range(N_TURNS):
        svc.send_text_message(session_id=sid, text=f"tin nhan {i}", client_message_id=str(i))
    pr.disable()

    st = pstats.Stats(pr)
    st.sort_stats("cumulative")
    print(f"=== TOP CUMULATIVE ({N_TURNS} turns) ===")
    st.print_stats(25)


if __name__ == "__main__":
    main()
