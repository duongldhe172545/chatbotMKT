"""HTTP Basic Auth dependency cho admin endpoints.

Refer F2C.8 + KE_HOACH § action 22.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings


_security = HTTPBasic()


def require_admin(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> str:
    """Verify HTTP Basic credentials. Trả về username nếu OK.

    Raises:
        HTTPException 401 nếu credentials sai.
    """
    settings = get_settings()
    correct_user = secrets.compare_digest(
        credentials.username, settings.ADMIN_USERNAME
    )
    correct_pass = secrets.compare_digest(
        credentials.password, settings.ADMIN_PASSWORD
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai username/password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
