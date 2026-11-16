"""Passwords and tokens.

Passwords are stored as Argon2id hashes: slow to compute on purpose, so a
stolen database is expensive to brute-force. Session, invitation and reset
tokens are long random strings; only their SHA-256 hash is stored, so a
database leak hands nobody a usable token. (A plain hash is enough for those,
unlike passwords: a 256-bit random token cannot be guessed, only a human
password can.)
"""

import hashlib
import secrets
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.errors import PasswordTooShortError

MIN_PASSWORD_LENGTH = 12

#: argon2-cffi's defaults are the RFC 9106 recommendation for Argon2id.
_hasher = PasswordHasher()


def check_password_rules(password: str) -> None:
    """Length is the rule that matters; character-class rules mostly don't."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShortError(f"a password needs at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    check_password_rules(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker settings than today's."""
    return _hasher.check_needs_rehash(password_hash)


@cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


def waste_time_like_a_verify(password: str) -> None:
    """Spend as long as a real check, for an address with no account.

    Without this a login would answer an unknown address noticeably faster,
    which tells an attacker which addresses exist.
    """
    verify_password(_dummy_hash(), password)


def new_token() -> str:
    """A URL-safe random token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """What the database stores instead of the token: 64 hex characters."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
