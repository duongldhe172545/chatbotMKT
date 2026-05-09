"""HTTP Basic Auth cho /admin + /api/admin/*.

Dùng FastAPI HTTPBasic — browser tự popup hỏi user/pass.
Constant-time compare để chống timing attack.

Username + password lấy từ env (.env hoặc Railway Variables).
"""
from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic()


def _get_credentials() -> tuple[str, str]:
    """Đọc credentials từ env mỗi lần (cho phép rotate password runtime)."""
    return (
        os.getenv("ADMIN_USERNAME", "admin"),
        os.getenv("ADMIN_PASSWORD", ""),
    )


def require_admin(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> str:
    """Dependency cho admin routes. Trả username nếu OK, raise 401 nếu sai.

    Bảo vệ:
    - secrets.compare_digest constant-time → chống timing attack đoán password
    - Compare cả 2 field (user + pass) trước khi cho qua → không leak info
      "user đúng nhưng pass sai" qua latency.
    """
    expected_user, expected_pass = _get_credentials()
    if not expected_pass:
        # Server quên config → fail loud thay vì cho qua
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin auth chưa được cấu hình",
        )

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        expected_user.encode("utf-8"),
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        expected_pass.encode("utf-8"),
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai user hoặc password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
