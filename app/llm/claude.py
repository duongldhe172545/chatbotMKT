"""Claude provider — dùng tool_use để ép structured output.

Có retry với exponential backoff khi gặp lỗi tạm thời (rate limit, network).
Logging mọi LLM call vào logs/llm_calls.jsonl (timing + token + cost tracking).
"""
from __future__ import annotations

import logging
import time

import anthropic

from .base import LLMProvider
from .call_logger import Timer, log_call

logger = logging.getLogger(__name__)

# Retry với 3 attempt, delay 1s, 2s, 4s khi gặp lỗi tạm thời.
RETRY_DELAYS = [1.0, 2.0, 4.0]
RETRYABLE_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._client: anthropic.Anthropic | None = None
        self.model = model

    def _get_client(self) -> anthropic.Anthropic:
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY chưa được set trong .env. "
                "Mở file .env và điền: ANTHROPIC_API_KEY=sk-ant-..."
            )
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _call_with_retry(self, fn, method: str):
        """Chạy fn() với retry. Log mỗi attempt vào jsonl."""
        last_err: Exception | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                with Timer() as t:
                    response = fn()
                # Lấy token usage — gồm cache tokens cho prompt caching tracking
                usage = getattr(response, "usage", None)
                log_call(
                    method=method,
                    model=self.model,
                    duration_ms=t.elapsed_ms,
                    input_tokens=getattr(usage, "input_tokens", None) if usage else None,
                    output_tokens=getattr(usage, "output_tokens", None) if usage else None,
                    cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None) if usage else None,
                    cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None) if usage else None,
                    success=True,
                    retry_count=attempt,
                )
                return response
            except RETRYABLE_ERRORS as exc:
                last_err = exc
                if attempt < len(RETRY_DELAYS):
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        "LLM %s lỗi tạm thời (%s), retry sau %.0fs (attempt %d)",
                        method, type(exc).__name__, delay, attempt + 1,
                    )
                    time.sleep(delay)
                    continue
            except Exception as exc:
                # Lỗi không retry được (vd: auth, bad request)
                last_err = exc
                break

        # Đã hết retry hoặc lỗi không retryable
        log_call(
            method=method,
            model=self.model,
            duration_ms=0,
            success=False,
            error=str(last_err),
            retry_count=len(RETRY_DELAYS) if isinstance(last_err, RETRYABLE_ERRORS) else 0,
        )
        raise last_err  # type: ignore[misc]

    def extract_structured(
        self,
        system_prompt: str,
        conversation_text: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
    ) -> dict:
        def _do():
            return self._get_client().messages.create(
                model=self.model,
                # 768 đủ cho extract output ~500 tokens — cap thấp để dừng sớm.
                max_tokens=768,
                # Prompt caching: system prompt 13-14K tokens (persona + playbook)
                # cache 5 phút. Lần đầu 1.25× giá, các call sau 0.1× giá.
                # Tiết kiệm ~70% input cost.
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": conversation_text}],
                tools=[{
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": input_schema,
                }],
                tool_choice={"type": "tool", "name": tool_name},
            )

        response = self._call_with_retry(_do, method="extract_structured")

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input

        # Fallback: LLM không trả tool_use đúng. Trả empty extraction để
        # conversation flow không crash. Sẽ ask lại ở turn sau.
        logger.warning("LLM không trả tool_use %s — trả empty fallback", tool_name)
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
        def _do():
            return self._get_client().messages.create(
                model=self.model,
                max_tokens=max_tokens,
                # Prompt caching cho chat replier — chung cache key với extractor.
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            )

        try:
            response = self._call_with_retry(_do, method="chat")
        except Exception as exc:
            logger.exception("LLM chat fail sau retry")
            return "Dạ em xin lỗi, em đang gặp xíu trục trặc kỹ thuật. Anh thử nhắn lại em sau ít phút nhé ạ."

        for block in response.content:
            if block.type == "text":
                return block.text.strip()
        return ""
