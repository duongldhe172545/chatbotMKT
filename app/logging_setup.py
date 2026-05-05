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
    """Cấu hình logging cho toàn app — gọi 1 lần ở main.py."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Add PII redaction filter to root logger
    root = logging.getLogger()
    pii_filter = PIIRedactionFilter()
    for handler in root.handlers:
        handler.addFilter(pii_filter)
