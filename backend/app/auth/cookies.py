"""Helpers for setting/clearing the refresh-token and CSRF cookies.

Centralized so every endpoint that issues or clears a session applies the same
flags - it must never be up to each route handler to remember `httponly`,
`secure`, `samesite`, and `path` correctly.
"""

import secrets

from fastapi import Response

from app.auth.dependencies import CSRF_COOKIE_NAME
from app.core.config import get_settings

settings = get_settings()

REFRESH_COOKIE_NAME = "refresh_token"
_AUTH_COOKIE_PATH = "/api/v1/auth"


def set_session_cookies(response: Response, *, raw_refresh_token: str) -> None:
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=max_age,
        path=_AUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=max_age,
        path=_AUTH_COOKIE_PATH,
        httponly=False,
        secure=settings.is_production,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=_AUTH_COOKIE_PATH)
    response.delete_cookie(key=CSRF_COOKIE_NAME, path=_AUTH_COOKIE_PATH)
