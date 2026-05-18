"""Test retry helper với exponential backoff. Refer F2C.4."""
from __future__ import annotations

import time

import pytest

from app.utils.retry import RetryExhaustedError, call_with_retry


class TestSuccessFirstTry:
    def test_success_no_retry(self):
        """Func thành công lần đầu → return ngay, không sleep."""
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        result = call_with_retry(fn, max_attempts=3)
        assert result == "ok"
        assert len(calls) == 1


class TestRetryThenSuccess:
    def test_fail_once_then_succeed(self):
        """Fail lần 1 → retry lần 2 → succeed."""
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 2:
                raise ConnectionError("transient")
            return "ok"

        result = call_with_retry(fn, max_attempts=3, base_delay_s=0.001)
        assert result == "ok"
        assert len(calls) == 2

    def test_fail_twice_then_succeed(self):
        """Fail 2 lần → retry lần 3 → succeed."""
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("transient")
            return "ok"

        result = call_with_retry(fn, max_attempts=3, base_delay_s=0.001)
        assert result == "ok"
        assert len(calls) == 3


class TestRetryExhausted:
    def test_all_attempts_fail_raises(self):
        """Hết max_attempts vẫn fail → RetryExhaustedError."""
        calls = []

        def fn():
            calls.append(1)
            raise ConnectionError("always fail")

        with pytest.raises(RetryExhaustedError) as exc_info:
            call_with_retry(fn, max_attempts=3, base_delay_s=0.001)

        assert len(calls) == 3
        # Original exception attached via __cause__
        assert isinstance(exc_info.value.__cause__, ConnectionError)


class TestExponentialBackoff:
    def test_delay_doubles_each_attempt(self):
        """Delay: 0.01 → 0.02 (2^0, 2^1). Total ≈ 0.03s cho 3 attempts."""
        calls = []
        timestamps = []

        def fn():
            timestamps.append(time.monotonic())
            calls.append(1)
            raise ConnectionError("fail")

        with pytest.raises(RetryExhaustedError):
            call_with_retry(fn, max_attempts=3, base_delay_s=0.01)

        # 3 attempts → 2 delays (0.01s + 0.02s)
        assert len(timestamps) == 3
        # Gap attempt 1 → 2: ~0.01s
        gap1 = timestamps[1] - timestamps[0]
        assert 0.008 < gap1 < 0.05, f"Expected ~0.01s, got {gap1}"
        # Gap attempt 2 → 3: ~0.02s
        gap2 = timestamps[2] - timestamps[1]
        assert 0.018 < gap2 < 0.08, f"Expected ~0.02s, got {gap2}"


class TestTimeout:
    def test_total_timeout_exceeded(self):
        """Total timeout < retry delay → TimeoutError."""
        calls = []

        def fn():
            calls.append(1)
            raise ConnectionError("fail")

        with pytest.raises(TimeoutError):
            call_with_retry(
                fn,
                max_attempts=5,
                base_delay_s=1.0,  # 1s, 2s, 4s, 8s
                timeout_s=0.5,  # nhanh hơn delay đầu
            )


class TestNonRetryableException:
    def test_non_retryable_raises_immediately(self):
        """Exception KHÔNG trong retryable_exceptions → raise ngay, no retry."""
        calls = []

        def fn():
            calls.append(1)
            raise ValueError("invalid input")

        with pytest.raises(ValueError):
            call_with_retry(
                fn,
                max_attempts=3,
                base_delay_s=0.001,
                retryable_exceptions=(ConnectionError,),
            )

        assert len(calls) == 1  # No retry


class TestEdgeCases:
    def test_max_attempts_1_no_retry(self):
        """max_attempts=1 → call 1 lần, không retry."""
        calls = []

        def fn():
            calls.append(1)
            raise ConnectionError("fail")

        with pytest.raises(RetryExhaustedError):
            call_with_retry(fn, max_attempts=1)
        assert len(calls) == 1

    def test_max_attempts_0_raises(self):
        """max_attempts < 1 → ValueError."""

        def fn():
            return "ok"

        with pytest.raises(ValueError):
            call_with_retry(fn, max_attempts=0)
