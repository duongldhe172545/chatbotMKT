"""Guards — bảo vệ bot khỏi attack + lệch luật.

Refer LUAT_2B § F2B.8.

4 lớp guard:
- G1 injection: regex pattern (Phase 3 R2) + LLM input sanitize (Phase 4+)
"""
from app.guards.injection import (
    check_prompt_injection,
    sanitize_injection,
)

__all__ = [
    "check_prompt_injection",
    "sanitize_injection",
]
