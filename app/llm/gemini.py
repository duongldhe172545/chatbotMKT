"""Gemini provider — Google AI SDK (google-genai).

DÙNG JSON MODE (response_schema) thay vì function calling.
Lý do: Gemini 2.5 Flash hay sinh MALFORMED_FUNCTION_CALL với schema 10 field +
enum + nested array. JSON mode stable hơn nhiều cho structured output phức tạp.

Trade-off: JSON mode không "force" tool name như tool_use của Anthropic, nhưng
Gemini sẽ luôn output JSON theo schema khi đặt response_mime_type=application/json.
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .base import LLMProvider
from .call_logger import Timer, log_call

logger = logging.getLogger(__name__)

# P3-event (2026-06-10): retry NGẮN — sleep dài chỉ giam thread khi đông người.
# 429/RESOURCE_EXHAUSTED không retry (xem _is_rate_limit) — quota đang cạn thì
# ngồi chờ vô ích, fail nhanh để caller rơi fallback thân thiện.
RETRY_DELAYS = [0.5, 1.5]
RETRYABLE_ERRORS = (
    genai_errors.ServerError,
    genai_errors.APIError,  # bao gồm rate limit
    httpx.HTTPError,
)

# Timeout mỗi call — chống 1 call treo giam thread cả phút (từng thấy hang 2.27h).
HTTP_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "25000"))

# Trần số call Gemini in-flight toàn process — burst 100 người không dội thẳng
# ~200 request cùng tích tắc lên API thành bão 429. Quá _SLOT_WAIT_S không có
# slot → GeminiBusyError → fallback, không xếp hàng vô hạn.
GEMINI_MAX_CONCURRENCY = int(os.getenv("GEMINI_MAX_CONCURRENCY", "50"))
_SLOT_WAIT_S = float(os.getenv("GEMINI_SLOT_WAIT_S", "20"))
_gemini_slots = threading.BoundedSemaphore(GEMINI_MAX_CONCURRENCY)


class GeminiBusyError(RuntimeError):
    """Không lấy được slot gọi Gemini trong thời gian chờ — đang quá tải."""


def _is_rate_limit(exc: Exception) -> bool:
    """True nếu lỗi là rate-limit (429 / RESOURCE_EXHAUSTED) — không nên retry."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    try:
        text = str(exc)
    except Exception:
        return False
    return "RESOURCE_EXHAUSTED" in text or "429" in text[:80]



def _drop_dead_local_proxy_env() -> None:
    """Avoid inheriting sandbox/dev proxy values that make Gemini unusable.

    Some local shells set HTTP(S)_PROXY/ALL_PROXY to 127.0.0.1:9. Port 9 is a
    discard port, so google-genai fails immediately with WinError 10061. Only
    strip that known-dead value; leave real user proxies intact.
    """
    dead_values = {
        "http://127.0.0.1:9",
        "https://127.0.0.1:9",
        "http://localhost:9",
        "https://localhost:9",
    }
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(key)
        if value and value.rstrip("/").lower() in dead_values:
            os.environ.pop(key, None)


def _build_thinking_config(model: str) -> "types.ThinkingConfig | None":
    """Build thinking config theo model.

    - Flash models: disable thinking (thinking_budget=0) — save cost.
    - Pro models: cần thinking_budget > 0. Đặt 512 để vừa đủ reasoning
      mà vẫn còn budget cho text output (1024 từng ăn hết budget gây
      empty response.text dù caller cho max_output_tokens=768).
    - Không xác định: None (dùng default).
    """
    name = model.lower()
    if "flash" in name:
        return types.ThinkingConfig(thinking_budget=0)
    if "pro" in name:
        return types.ThinkingConfig(thinking_budget=512)
    return None

# Safety settings — relax xuống BLOCK_ONLY_HIGH cho tất cả category.
# Lý do: dealer ngành cửa/VLXD thường chửi tục ("đéo", "đm", "vcl") khi bực mình.
# Default threshold MEDIUM_AND_ABOVE sẽ chặn content → response.content = None → app crash.
# Playbook đã có rule xử case cộc (scenario F), bot sẽ phản hồi lịch sự không cần safety filter của Gemini.
SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._client: genai.Client | None = None
        self.model = model

    def _get_client(self) -> genai.Client:
        if not self._api_key:
            raise RuntimeError(
                "GEMINI_API_KEY chưa set trong .env. "
                "Lấy free tại https://aistudio.google.com/apikey"
            )
        if self._client is None:
            _drop_dead_local_proxy_env()
            # Timeout cứng (default 25s, env GEMINI_TIMEOUT_MS) — chống hang khi
            # Gemini overload (đã thấy 1 call hang 8133s = 2.27h trong test).
            # Hết timeout → APIError → retry policy + cuối cùng fallback.
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS),
            )
        return self._client

    def _call_with_retry(self, fn, method: str):
        last_err: Exception | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            # Slot in-flight: giữ CHỈ trong lúc call mạng; sleep retry nằm ngoài
            # slot để không chiếm chỗ của người khác trong lúc chờ.
            if not _gemini_slots.acquire(timeout=_SLOT_WAIT_S):
                last_err = GeminiBusyError(
                    f"Gemini kín {GEMINI_MAX_CONCURRENCY} slot sau {_SLOT_WAIT_S:.0f}s chờ"
                )
                break
            retry_delay: float | None = None
            try:
                with Timer() as t:
                    response = fn()
                usage = getattr(response, "usage_metadata", None)
                log_call(
                    method=method,
                    model=self.model,
                    duration_ms=t.elapsed_ms,
                    input_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
                    output_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
                    cache_read_input_tokens=getattr(usage, "cached_content_token_count", None) if usage else None,
                    success=True,
                    retry_count=attempt,
                )
                return response
            except RETRYABLE_ERRORS as exc:
                last_err = exc
                if _is_rate_limit(exc):
                    # Quota đang cạn — retry chỉ giam thread vô ích, fail nhanh.
                    logger.warning("Gemini %s dính rate-limit — fail nhanh, không retry", method)
                    break
                if attempt < len(RETRY_DELAYS):
                    # Jitter ±30% — tránh trăm thread retry cùng nhịp.
                    retry_delay = RETRY_DELAYS[attempt] * (0.7 + 0.6 * random.random())
            except Exception as exc:
                last_err = exc
                break
            finally:
                _gemini_slots.release()
            if retry_delay is None:
                break
            logger.warning(
                "Gemini %s lỗi tạm thời (%s), retry sau %.1fs",
                method, type(last_err).__name__, retry_delay,
            )
            time.sleep(retry_delay)

        try:
            err_text = str(last_err)
        except Exception:
            err_text = type(last_err).__name__
        log_call(
            method=method,
            model=self.model,
            duration_ms=0,
            success=False,
            error=err_text,
            retry_count=len(RETRY_DELAYS) if isinstance(last_err, RETRYABLE_ERRORS) else 0,
        )
        raise last_err  # type: ignore[misc]

    @staticmethod
    def _convert_schema_for_gemini(schema: dict) -> dict:
        """JSON Schema từ Anthropic format → Gemini-compatible.

        Khác biệt cần convert:
        - `["string", "null"]` (union types) → `"string"` + `nullable: True`
        - `enum` chứa `None` → strip None ra (Gemini chỉ accept strings)
        - `additionalProperties` ở top level — bỏ
        """
        def _normalize(node):
            if isinstance(node, dict):
                result = {}
                for k, v in node.items():
                    if k == "type" and isinstance(v, list):
                        non_null = [t for t in v if t != "null"]
                        result["type"] = non_null[0] if non_null else "string"
                        if "null" in v:
                            result["nullable"] = True
                    elif k == "enum" and isinstance(v, list):
                        # Strip None khỏi enum — Gemini chỉ accept string values
                        result["enum"] = [x for x in v if x is not None]
                    elif k == "additionalProperties":
                        continue
                    else:
                        result[k] = _normalize(v)
                return result
            if isinstance(node, list):
                return [_normalize(x) for x in node]
            return node

        return _normalize(schema)

    def extract_structured(
        self,
        system_prompt: str,
        conversation_text: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        # JSON mode thay vì function calling — Gemini stable hơn cho schema phức tạp
        gemini_schema = self._convert_schema_for_gemini(input_schema)

        # Inject hướng dẫn vào system_prompt để Gemini biết cần output đúng tool semantics
        json_instruction = (
            f"\n\n---\nNHIỆM VỤ ĐẦU RA: {tool_description}\n"
            "BẮT BUỘC trả về JSON đúng schema, KHÔNG markdown, KHÔNG comment, "
            "KHÔNG thêm field ngoài schema."
        )

        def _do():
            return self._get_client().models.generate_content(
                model=self.model,
                contents=conversation_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt + json_instruction,
                    response_mime_type="application/json",
                    response_schema=gemini_schema,
                    safety_settings=SAFETY_SETTINGS,
                    # Thinking: disable cho flash (save cost), budget tối thiểu
                    # cho pro (model bắt buộc thinking_budget > 0).
                    thinking_config=_build_thinking_config(self.model),
                    temperature=0.3,
                    top_p=0.9,
                    max_output_tokens=1024,
                ),
            )

        response = self._call_with_retry(_do, method="extract_structured")

        # Defensive: Gemini đôi khi trả candidate.content=None khi safety filter / malformed.
        text = ""
        try:
            text = (response.text or "").strip()
        except Exception:
            for candidate in (response.candidates or []):
                logger.warning(
                    "Gemini extract content=None (finish_reason=%s)",
                    getattr(candidate, "finish_reason", "?"),
                )

        if not text:
            logger.warning("Gemini không sinh được JSON output — trả empty")
            return self._empty_extraction()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Gemini JSON parse fail: %s; raw=%s", exc, text[:200])
            return self._empty_extraction()

    @staticmethod
    def _empty_extraction() -> dict:
        return {
            "extracted_fields": {},
            "confidence": {},
            "missing_fields": [],
            "confirm_questions": [],
            "cleaned_summary": "",
        }

    def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 512,
    ) -> str:
        # Convert messages từ Anthropic format → Gemini format.
        # Anthropic role "user|assistant" → Gemini role "user|model".
        gemini_contents = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            content_text = m.get("content", "")
            gemini_contents.append(
                types.Content(role=role, parts=[types.Part(text=content_text)])
            )

        def _do():
            return self._get_client().models.generate_content(
                model=self.model,
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    safety_settings=SAFETY_SETTINGS,
                    thinking_config=_build_thinking_config(self.model),
                    temperature=0.6,
                    top_p=0.9,
                    max_output_tokens=max_tokens,
                ),
            )

        try:
            response = self._call_with_retry(_do, method="chat")
        except Exception:
            logger.exception("Gemini chat fail sau retry")
            return "Dạ em xin lỗi, em đang gặp xíu trục trặc kỹ thuật. Anh thử nhắn lại em sau ít phút nhé ạ."

        text = ""
        try:
            text = (response.text or "").strip()
        except Exception:
            # Có thể content bị block safety filter → response.text raise
            pass
        if not text:
            logger.warning("Gemini chat trả empty — có thể bị safety filter chặn")
            # Neutral fallback (không assert dealer "bận" — gây hiểu nhầm
            # nếu dealer KHÔNG bận). Caller (ack_generator) sẽ catch và
            # rơi safe_ack random.
            return ""
        return text
