"""Setup logging với PII redaction filter — không leak SĐT/Zalo dealer ra log file.

Áp dụng filter ở root logger để mọi logger con tự động redact.
"""
from __future__ import annotations

import logging
import re

# Pattern SĐT VN: bắt đầu 0, 9-10 chữ số sau (tổng 10-11 chữ số)
PHONE_RE = re.compile(r"\b0\d{8,10}\b")
# Pattern email (chỉ redact một phần để vẫn debug được)
EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def redact_pii(text: str) -> str:
    """Mask SĐT thành [PHONE], email một phần."""
    if not text:
        return text
    text = PHONE_RE.sub("[PHONE]", text)
    text = EMAIL_RE.sub(r"\1***@\2", text)
    return text


class PIIRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Redact message + args
        if isinstance(record.msg, str):
            record.msg = redact_pii(record.msg)
        if record.args:
            try:
                record.args = tuple(
                    redact_pii(a) if isinstance(a, str) else a for a in record.args
                )
            except Exception:
                pass
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Cấu hình logging cho toàn app — gọi 1 lần ở main.py.

    Format có request_id (8 ký tự) — debug production: dealer báo lỗi kèm
    header X-Request-ID, anh grep log thấy ngay full flow.
    """
    # Import muộn để tránh circular import (middleware import logging_setup)
    from app.middleware import RequestIDLogFilter

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(request_id)s] %(levelname)s %(name)s: %(message)s",
    )
    root = logging.getLogger()
    pii_filter = PIIRedactionFilter()
    rid_filter = RequestIDLogFilter()
    for handler in root.handlers:
        handler.addFilter(pii_filter)
        handler.addFilter(rid_filter)
