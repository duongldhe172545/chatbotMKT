"""LLM call logger — append JSONL vào logs/llm_calls.jsonl.

Log đủ thông tin debug + cost tracking, KHÔNG log nội dung prompt/response để
tránh leak PII dealer vào file log.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_PATH = Path("logs/llm_calls.jsonl")


def log_call(
    *,
    method: str,
    model: str,
    duration_ms: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_creation_input_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
    success: bool,
    error: str | None = None,
    retry_count: int = 0,
) -> None:
    """Append 1 dòng JSON vào log file. Best-effort, không raise nếu fail.

    Prompt caching tokens:
    - cache_creation_input_tokens: tokens được WRITE vào cache (lần đầu, 1.25× giá)
    - cache_read_input_tokens: tokens đọc từ cache (0.1× giá → tiết kiệm ~90%)
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "method": method,
            "model": model,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "success": success,
            "retry_count": retry_count,
        }
        if error:
            entry["error"] = error[:200]  # truncate, không log full traceback
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("LLM call logger failed: %s", exc)


class Timer:
    """Context manager đo thời gian. `with Timer() as t: ...; t.elapsed_ms`."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed_ms = int((time.perf_counter() - self._start) * 1000)
