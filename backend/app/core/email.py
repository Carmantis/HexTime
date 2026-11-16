"""Sending email (server mode): invitations, password resets, verification.

Routes receive a Mailer through ``Depends(get_mailer)``, so tests can swap in
one that only records what would have been sent. Messages are plain text: they
carry one link, and plain text survives every mail client and spam filter.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Annotated, Protocol

from fastapi import Depends

from app.core.config import CONSOLE_SMTP, Settings, SmtpSecurity, get_settings
from app.core.errors import EmailFailedError

log = logging.getLogger("hextime.email")

SMTP_TIMEOUT = 15


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, email: Email) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _message(self, email: Email) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._settings.mail_sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)
        return message

    def send(self, email: Email) -> None:
        settings = self._settings
        host = settings.smtp_host or ""
        try:
            if settings.smtp_security is SmtpSecurity.SSL:
                server = smtplib.SMTP_SSL(
                    host,
                    settings.smtp_port,
                    timeout=SMTP_TIMEOUT,
                    context=ssl.create_default_context(),
                )
            else:
                server = smtplib.SMTP(host, settings.smtp_port, timeout=SMTP_TIMEOUT)
            with server:
                if settings.smtp_security is SmtpSecurity.STARTTLS:
                    server.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password or "")
                server.send_message(self._message(email))
        except (smtplib.SMTPException, OSError) as error:
            # The address and server go to the log; the user sees only the code.
            log.error("sending to %s via %s failed: %s", email.to, host, error)
            raise EmailFailedError("the email could not be sent") from error


class ConsoleMailer:
    """Prints instead of sending, for trying server mode without a mail server."""

    def send(self, email: Email) -> None:
        log.warning("EMAIL to %s: %s\n%s", email.to, email.subject, email.body)


def mailer_for(settings: Settings) -> Mailer:
    if settings.smtp_host == CONSOLE_SMTP:
        return ConsoleMailer()
    return SmtpMailer(settings)


def get_mailer(settings: Annotated[Settings, Depends(get_settings)]) -> Mailer:
    return mailer_for(settings)


MailerDep = Annotated[Mailer, Depends(get_mailer)]
