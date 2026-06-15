"""Regression: annotation phải resolve được — chặn lỗi thiếu import Optional.

Bug 2026-06-10: observation_detector dùng Optional trong chữ ký nhưng chỉ
import Any. Không crash runtime (PEP 563) nhưng vỡ get_type_hints/introspection.
"""
from __future__ import annotations

import typing


def test_detect_observations_type_hints_resolve():
    from app.parlant import observation_detector as od

    hints = typing.get_type_hints(od.detect_observations)
    assert "message" in hints
