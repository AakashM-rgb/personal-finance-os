"""Per-account login throttle, alongside the per-IP limit on /auth/login.

The per-IP limit alone can be sidestepped by rotating client IPs (or by
spoofing X-Forwarded-For where it is trusted - see docs/DEPLOYMENT.md, "Client
IP behind the proxy"). This throttle is keyed by the account being attacked,
so it holds no matter where attempts come from:

- An account that collects `login_account_max_failures` failed logins within
  `login_account_window_minutes` refuses every further attempt - including a
  correct password, or the throttle would become a password oracle - until
  the oldest failure ages out of the window. Refused attempts are not
  recorded, so the lock never outlasts the window: no permanent lockout.
- Attempts against unregistered emails are throttled identically, so the
  throttle can't reveal which emails have accounts.
- A successful login clears the account's failures.
- Wrong current passwords on /auth/change-password are counted the same
  way under a separate key (password_change_key), so the two counters
  never lock each other.
- State lives in PostgreSQL (the only shared store this app provisions), so
  it holds across workers, instances, and restarts.
"""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.login_failure_repository import LoginFailureRepository

settings = get_settings()

# A purpose-specific key derived from the JWT secret, so the account keys
# stored in login_failures can't be matched against guessed emails without
# it, and no separate secret has to be provisioned. Rotating JWT_SECRET_KEY
# resets every throttle counter, which is harmless.
_ACCOUNT_KEY_SECRET = hmac.new(
    settings.jwt_secret_key.encode(), b"login-throttle-account-key-v1", hashlib.sha256
).digest()


_PASSWORD_CHANGE_KEY_SECRET = hmac.new(
    settings.jwt_secret_key.encode(), b"password-change-throttle-key-v1", hashlib.sha256
).digest()


def account_key(email: str) -> str:
    """Normalized the same way as UserRepository.get_by_email, so every
    spelling that reaches the same account shares one counter."""
    normalized = email.strip().lower()
    return hmac.new(_ACCOUNT_KEY_SECRET, normalized.encode(), hashlib.sha256).hexdigest()


def password_change_key(user_id: uuid.UUID) -> str:
    """The counter for wrong current passwords on /auth/change-password,
    kept apart from the login counter so an attacker holding a stolen session
    can't use failed change attempts to lock the real user out of signing in.
    Derived from its own secret, so no input to account_key can collide."""
    return hmac.new(_PASSWORD_CHANGE_KEY_SECRET, str(user_id).encode(), hashlib.sha256).hexdigest()


def _lock_id(key: str) -> int:
    """A signed 64-bit id for pg_advisory_xact_lock, taken from the key itself."""
    return int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True)


def _window_start() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=settings.login_account_window_minutes)


async def acquire(db: AsyncSession, key: str) -> bool:
    """Takes the account's lock for the rest of the transaction and reports
    whether a login attempt may proceed. False when the account is throttled,
    or when another attempt on it is in flight right now - a real user never
    submits two logins for one account at the same instant."""
    repo = LoginFailureRepository(db)
    if not await repo.try_lock_account(_lock_id(key)):
        return False
    failures = await repo.count_since(key, _window_start())
    return failures < settings.login_account_max_failures


async def record_failure(db: AsyncSession, key: str) -> None:
    repo = LoginFailureRepository(db)
    await repo.add(key)
    # Opportunistic pruning keeps the table bounded to one window's worth of
    # failures without needing a scheduler.
    await repo.delete_older_than(_window_start())


async def clear(db: AsyncSession, key: str) -> None:
    await LoginFailureRepository(db).delete_for_account(key)
