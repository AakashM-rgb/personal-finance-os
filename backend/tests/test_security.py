import uuid
from datetime import timedelta

import jwt
import pytest

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
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
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
