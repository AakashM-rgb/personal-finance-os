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
# The refresh token itself is httpOnly and only ever needs to reach the auth
# endpoints, so it stays scoped to that path - no server-side code anywhere
# else ever needs it, and narrowing where the browser sends it is good
# hygiene for a sensitive, long-lived credential.
_REFRESH_COOKIE_PATH = "/api/v1/auth"
# The CSRF cookie's entire purpose - see verify_csrf's own docstring - is
# for the frontend's own JavaScript to read it and echo it back as a
# header. That only works if the cookie is visible from wherever that
# JavaScript actually runs: every frontend route (/dashboard, /budgets, ...),
# never /api/v1/auth itself (that path belongs to the separate backend
# deployable - no frontend page is ever served from it). Scoping this
# cookie's Path to /api/v1/auth, as the refresh token's is, would make it
# unreadable via document.cookie on every real page, silently breaking the
# app's own mount-time "restore my session after a hard reload" check -
# it must be readable site-wide instead.
_CSRF_COOKIE_PATH = "/"


def set_session_cookies(response: Response, *, raw_refresh_token: str) -> None:
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=max_age,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=max_age,
        path=_CSRF_COOKIE_PATH,
        httponly=False,
        secure=settings.is_production,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=_REFRESH_COOKIE_PATH)
    response.delete_cookie(key=CSRF_COOKIE_NAME, path=_CSRF_COOKIE_PATH)
