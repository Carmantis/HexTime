"""Password hashing, tokens and creating the first administrator."""

import pytest
from sqlalchemy.orm import Session

from app.core.errors import PasswordTooShortError, ValidationFailedError
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    verify_password,
)
from app.services.users import make_admin


def test_a_password_hash_verifies_only_the_right_password() -> None:
    stored = hash_password("correct horse battery")

    assert stored.startswith("$argon2id$")
    assert verify_password(stored, "correct horse battery")
    assert not verify_password(stored, "correct horse batterY")
    assert not needs_rehash(stored)


def test_the_same_password_hashes_differently_each_time() -> None:
    """A salt per hash: equal passwords cannot be spotted in the database."""
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


def test_a_garbled_hash_is_a_failed_check_not_a_crash() -> None:
    assert not verify_password("not-a-hash", "anything at all")


def test_short_passwords_are_refused() -> None:
    with pytest.raises(PasswordTooShortError):
        hash_password("x" * (MIN_PASSWORD_LENGTH - 1))


def test_tokens_are_long_random_and_stored_hashed() -> None:
    token = new_token()

    assert len(token) >= 43
    assert token != new_token()
    assert len(hash_token(token)) == 64
    assert hash_token(token) == hash_token(token)


def test_make_admin_creates_a_verified_administrator(db: Session) -> None:
    user = make_admin(
        db, email=" Anna@Example.ORG ", display_name="Anna", password="correct horse battery"
    )

    assert user.email == "anna@example.org"
    assert user.is_admin and user.is_active
    assert user.email_verified_at is not None


def test_running_it_again_resets_the_password(db: Session) -> None:
    first = make_admin(
        db, email="anna@example.org", display_name="Anna", password="first password!"
    )
    first.is_active = False
    db.commit()

    again = make_admin(db, email="anna@example.org", display_name="", password="second password!")

    assert again.id == first.id
    assert again.is_active
    assert verify_password(again.password_hash or "", "second password!")


def test_make_admin_needs_an_email_address(db: Session) -> None:
    with pytest.raises(ValidationFailedError):
        make_admin(db, email="anna", display_name="Anna", password="correct horse battery")
