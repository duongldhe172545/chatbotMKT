"""Middleware — CORS + X-Request-ID.

X-Request-ID:
- Mỗi request gen UUID 8 ký tự đầu (đủ unique cho debug, gọn cho log).
- Inject vào contextvars → mọi logger.* trong request đều có request_id.
- Trả qua response header X-Request-ID để client có thể tag báo cáo lỗi.

Use case: dealer báo "lỗi lúc 2h chiều" + screenshot có header X-Request-ID
→ grep log 10 giây ra full flow turn đó. Không phải lục DB đoán.
"""
from __future__ import annotations

import contextvars
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ContextVar — Python 3.7+ thread-safe + asyncio-safe propagation
# Default "-" để log của background task (no request) không crash format.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def get_request_id() -> str:
    """Lấy request_id của request đang xử (hoặc '-' nếu không có)."""
    return request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Sinh request_id cho mỗi request, propagate qua logger context.

    - Nếu client gửi header X-Request-ID → reuse (để client correlate).
    - Nếu không → gen UUID 8 ký tự đầu.
    - Set vào contextvars cho logger format đọc được.
    - Trả qua response header X-Request-ID.
    """

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


class RequestIDLogFilter(logging.Filter):
    """Inject request_id vào mỗi log record để format sử dụng."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
