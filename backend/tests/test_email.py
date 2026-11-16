"""The SMTP mailer and the create-admin command's --send-link.

smtplib is replaced by a fake that records what the mailer asked of it, so
nothing here touches the network.
"""

import smtplib
from typing import Any, ClassVar

import pytest
from sqlalchemy.orm import Session

from app import cli
from app.core.config import SmtpSecurity
from app.core.email import ConsoleMailer, Email, SmtpMailer, mailer_for
from app.core.errors import EmailFailedError
from app.models import User
from tests.conftest import SERVER_SETTINGS, Outbox, build_settings

EMAIL = Email(to="anna@example.org", subject="Hei", body="Linkki")


class FakeSmtp:
    """Stands in for smtplib.SMTP / SMTP_SSL and remembers every call."""

    instances: ClassVar[list["FakeSmtp"]] = []
    fail_on_send: ClassVar[bool] = False

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.host, self.port = host, port
        self.calls: list[str] = []
        self.sent: list[Any] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user}")

    def send_message(self, message: Any) -> None:
        if FakeSmtp.fail_on_send:
            raise smtplib.SMTPRecipientsRefused({})
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.instances = []
    FakeSmtp.fail_on_send = False
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)


def smtp_settings(**overrides: Any):
    return build_settings(
        **SERVER_SETTINGS
        | {
            "smtp_host": "smtp.example.org",
            "smtp_from": "hextime@example.org",
            "smtp_username": "hextime@example.org",
            "smtp_password": "secret",
        }
        | overrides
    )


def test_starttls_is_the_default_and_comes_before_login() -> None:
    SmtpMailer(smtp_settings()).send(EMAIL)

    server = FakeSmtp.instances[0]
    assert (server.host, server.port) == ("smtp.example.org", 587)
    assert server.calls[:2] == ["starttls", "login hextime@example.org"]
    message = server.sent[0]
    assert message["From"] == "hextime@example.org"
    assert message["To"] == "anna@example.org"
    assert message["Subject"] == "Hei"


def test_ssl_on_465_skips_starttls() -> None:
    SmtpMailer(smtp_settings(smtp_security=SmtpSecurity.SSL, smtp_port=465)).send(EMAIL)

    assert "starttls" not in FakeSmtp.instances[0].calls


def test_an_internal_relay_needs_no_login() -> None:
    settings = smtp_settings(
        smtp_security=SmtpSecurity.NONE, smtp_port=25, smtp_username=None, smtp_password=None
    )
    SmtpMailer(settings).send(EMAIL)

    assert FakeSmtp.instances[0].calls == ["quit"]
    assert len(FakeSmtp.instances[0].sent) == 1


def test_a_refused_message_is_an_email_failed_error() -> None:
    FakeSmtp.fail_on_send = True

    with pytest.raises(EmailFailedError):
        SmtpMailer(smtp_settings()).send(EMAIL)


def test_the_console_setting_never_opens_a_connection() -> None:
    mailer = mailer_for(build_settings(**SERVER_SETTINGS))

    assert isinstance(mailer, ConsoleMailer)
    mailer.send(EMAIL)
    assert FakeSmtp.instances == []


def test_create_admin_can_send_a_link_instead_of_asking_a_password(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    outbox = Outbox()
    monkeypatch.setattr(cli, "get_settings", lambda: build_settings(**SERVER_SETTINGS))
    monkeypatch.setattr(cli, "get_session_factory", lambda: lambda: db)
    monkeypatch.setattr(cli, "mailer_for", lambda settings: outbox)
    # The session the command closes is the test's; keep it usable afterwards.
    monkeypatch.setattr(db, "close", lambda: None)

    cli.main(["create-admin", "--email", "anna@example.org", "--name", "Anna", "--send-link"])

    anna = db.query(User).filter_by(email="anna@example.org").one()
    assert anna.is_admin
    assert anna.password_hash is None
    assert outbox[0].subject == "Tervetuloa HexTimeen"
