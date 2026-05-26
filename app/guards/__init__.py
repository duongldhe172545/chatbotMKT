"""Guards — bảo vệ bot khỏi attack + lệch luật.

Refer LUAT_2B § F2B.8.

4 lớp guard:
- G1 injection: regex pattern (Phase 3 R2) + LLM input sanitize (Phase 4+)
- G2 hallucinate: value_in_message check
- G3 drift: forbidden vocab + auto-rewrite
- G4 pii_leak: cross-session PII check (Phase 4)
"""
from app.guards.drift import (
    auto_rewrite,
    check_drift,
    check_parrot,
    count_emojis,
    has_forbidden_scoring_vocab,
    trim_emojis,
)
from app.guards.hallucinate import (
    check_ack_hallucinate,
    check_hallucinate,
    value_appears_in_message,
)
from app.guards.injection import (
    check_prompt_injection,
    sanitize_injection,
)

__all__ = [
    "check_drift",
    "auto_rewrite",
    "has_forbidden_scoring_vocab",
    "count_emojis",
    "trim_emojis",
    "check_parrot",
    "check_hallucinate",
    "check_ack_hallucinate",
    "value_appears_in_message",
    "check_prompt_injection",
    "sanitize_injection",
]
