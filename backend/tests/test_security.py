import uuid
from datetime import timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_purpose_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)


def test_password_hash_is_never_the_plaintext() -> None:
    hashed = hash_password("correcthorse123")
    assert hashed != "correcthorse123"
    assert verify_password("correcthorse123", hashed) is True


def test_password_verify_rejects_wrong_password() -> None:
    hashed = hash_password("correcthorse123")
    assert verify_password("wrong-password", hashed) is False


def test_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    family_id = uuid.uuid4()
    token = create_access_token(user_id, family_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["sid"] == str(family_id)
    assert payload["type"] == TokenType.ACCESS.value


def test_expired_access_token_is_rejected() -> None:
    user_id = uuid.uuid4()
    token = create_purpose_token(user_id, TokenType.ACCESS, timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_refresh_token_hash_round_trip() -> None:
    raw = "some-high-entropy-refresh-secret"
    hashed = hash_refresh_token(raw)
    assert hashed != raw
    assert verify_refresh_token(raw, hashed) is True
    assert verify_refresh_token("a-different-secret", hashed) is False


# --- CORS configuration ------------------------------------------------------------------

def _settings(**overrides: str) -> Settings:
    base = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
        "TEST_DATABASE_URL": "postgresql+asyncpg://u:p@localhost/test",
        "JWT_SECRET_KEY": "x" * 32,
        "CORS_ORIGINS": "https://app.example.com",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_a_wildcard_cors_origin_is_refused_in_production() -> None:
    """The API is cookie-authenticated with allow_credentials=True, so a
    wildcard allow-list would let any site make authenticated requests."""
    with pytest.raises(ValidationError, match="explicit origins in production"):
        _settings(CORS_ORIGINS="*")

    with pytest.raises(ValidationError, match="explicit origins in production"):
        _settings(CORS_ORIGINS="https://app.example.com,*")


def test_explicit_origins_are_accepted_and_split() -> None:
    settings = _settings(CORS_ORIGINS="https://a.example.com, https://b.example.com")

    assert settings.cors_origin_list == ["https://a.example.com", "https://b.example.com"]


def test_a_wildcard_is_still_allowed_outside_production() -> None:
    """Local development may legitimately use it; nothing user-facing is
    exposed by a dev server."""
    settings = _settings(ENVIRONMENT="development", CORS_ORIGINS="*")

    assert settings.cors_origin_list == ["*"]
    assert settings.is_production is False
