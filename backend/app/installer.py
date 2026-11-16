"""Interactive server setup: ``python -m app.cli setup``.

The administrator never edits a settings file. The installation script
(``deploy/hextime-install.sh``) starts this inside the HexTime image, with a
directory of the server mounted at ``--config-dir``. It asks a handful of
questions, checks what it can (DNS, sending an email), and writes:

=================  ==========================================================
``hextime.env``    settings of the HexTime container, secrets included
``postgres.env``   the database's name, user and password
``caddy.env``      the address Caddy gets a certificate for
``install.vars``   what the installation script still needs: the address and
                   the first administrator (shell-quoted, to be sourced)
=================  ==========================================================

Every file is readable by its owner only.

Running it again shows the current values as defaults, so changing one
setting is a matter of pressing Enter through the rest. The secret key and
the database password are never changed: a new key would sign everybody out,
and a new database password would no longer match the database.

The terminal, DNS and the mail server are handed in (``Io``, ``Checks``) so
the tests can drive every question without a network.
"""

import getpass
import os
import re
import secrets
import shlex
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from app.core.config import CONSOLE_SMTP, SUPPORTED_LOCALES, AppMode, Settings, SmtpSecurity
from app.core.email import Email, mailer_for
from app.core.errors import EmailFailedError

#: What the Quadlet units call the database container. DATABASE_URL points
#: at it, so the two must agree (deploy/quadlet/hextime-postgres.container).
POSTGRES_HOST = "hextime-postgres"
POSTGRES_DB = "hextime"
POSTGRES_USER = "hextime"

APP_FILE = "hextime.env"
POSTGRES_FILE = "postgres.env"
CADDY_FILE = "caddy.env"
VARS_FILE = "install.vars"

#: Usual ports for each kind of SMTP connection.
SMTP_PORTS = {SmtpSecurity.STARTTLS: 587, SmtpSecurity.SSL: 465, SmtpSecurity.NONE: 25}

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
#: A host name: dot-separated labels, at least two, or "localhost" for a try-out.
HOSTNAME = re.compile(rf"^(?:{_LABEL}\.)+{_LABEL}$|^localhost$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


# ---------------------------------------------------------------------------
# The terminal and the outside world, replaceable in tests
# ---------------------------------------------------------------------------


class Io(Protocol):
    def say(self, text: str = "") -> None: ...

    def ask(self, question: str, default: str = "") -> str: ...

    def secret(self, question: str) -> str: ...


class TerminalIo:
    """Questions on the terminal. Enter takes the default shown in brackets."""

    def say(self, text: str = "") -> None:
        print(text)

    def ask(self, question: str, default: str = "") -> str:
        shown = f" [{default}]" if default else ""
        answer = input(f"{question}{shown}: ").strip()
        return answer or default

    def secret(self, question: str) -> str:
        return getpass.getpass(f"{question}: ")


def _resolve(host: str) -> list[str]:
    """The addresses a host name resolves to; empty if it does not."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    return sorted({str(info[4][0]) for info in infos})


def _send_test_email(settings: Settings, to: str) -> None:
    mailer_for(settings).send(
        Email(
            to=to,
            subject="HexTime: test email",
            body=(
                "This is a test from the HexTime installation.\n\n"
                "If you can read this, HexTime can send invitations and "
                "password links.\n"
            ),
        )
    )


@dataclass(frozen=True)
class Checks:
    resolve: Callable[[str], list[str]] = _resolve
    send_test_email: Callable[[Settings, str], None] = _send_test_email


class SetupCancelledError(Exception):
    """The administrator chose to stop; nothing was written."""


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines, as Podman's --env-file reads them: no quoting."""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value
    return values


def read_vars(path: Path) -> dict[str, str]:
    """The shell-quoted file this module writes for the installation script."""
    return {key: (shlex.split(value) or [""])[0] for key, value in read_env(path).items()}


def _write_private(path: Path, text: str) -> None:
    """Write a file only its owner can read, never readable even briefly.

    The file is created with mode 600 from the start rather than chmod-ed
    after writing, and replaced in one step so a reader never sees half.
    """
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _env_text(heading: str, values: dict[str, str]) -> str:
    lines = [f"# {heading}", "# Written by `hextime setup`; run it again to change.", ""]
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} must be on one line")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _vars_text(values: dict[str, str]) -> str:
    """For `source` in bash: every value quoted, so a name cannot run code."""
    lines = ["# Written by `hextime setup` for the installation script."]
    lines += [f"{key}={shlex.quote(value)}" for key, value in values.items()]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The answers
# ---------------------------------------------------------------------------


@dataclass
class Answers:
    domain: str
    email_domain: str
    locale: str
    time_zone: str
    self_registration: bool
    admin_name: str
    admin_email: str
    smtp: dict[str, str] = field(default_factory=dict)


def _ask_valid(io: Io, question: str, default: str, check: Callable[[str], str | None]) -> str:
    """Ask until `check` finds nothing wrong (it returns a complaint, or None)."""
    while True:
        answer = io.ask(question, default).strip()
        problem = check(answer)
        if problem is None:
            return answer
        io.say(f"  {problem}")


def _yes(io: Io, question: str, default: bool) -> bool:
    answer = io.ask(f"{question} (y/n)", "y" if default else "n").lower()
    return answer.startswith("y") or answer.startswith("k")


def _one_line(value: str) -> str | None:
    if not value:
        return "Please give a value."
    if "\n" in value or "\r" in value:
        return "One line, please."
    return None


def _hostname_problem(value: str) -> str | None:
    if not HOSTNAME.match(value.lower()):
        return "That is not a host name, e.g. hextime.example.org (no https://, no path)."
    return None


def _email_domain_problem(value: str) -> str | None:
    if value.lower() != "localhost" and not HOSTNAME.match(value.lower()):
        return "That is not a domain, e.g. example.org."
    return None


def _time_zone_problem(value: str) -> str | None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return "That is not a time zone, e.g. Europe/Helsinki."
    return None


def _parent_domain(host: str) -> str:
    """hextime.example.org -> example.org; anything shorter stays as it is."""
    parts = host.split(".")
    return ".".join(parts[1:]) if len(parts) > 2 else host


def _check_dns(io: Io, checks: Checks, domain: str, host_addresses: list[str]) -> None:
    """Warn, never refuse: DNS may simply not have spread yet."""
    if domain == "localhost":
        return
    found = checks.resolve(domain)
    if not found:
        io.say(f"  {domain} does not resolve yet. Caddy cannot get an HTTPS certificate")
        io.say("  until it points at this server.")
    elif host_addresses and not set(found) & set(host_addresses):
        io.say(f"  {domain} points at {', '.join(found)},")
        io.say(f"  but this server has {', '.join(host_addresses)}.")
        io.say("  Fine if the server is behind NAT; otherwise fix the DNS record.")
    else:
        io.say(f"  {domain} -> {', '.join(found)}")
        return
    if not _yes(io, "Continue anyway?", True):
        raise SetupCancelledError


def _ask_smtp(io: Io, old: dict[str, str], email_domain: str) -> dict[str, str]:
    io.say()
    io.say("Email. HexTime sends invitations and password links; it needs a mail server.")
    io.say(f"(Answer {CONSOLE_SMTP!r} as the server to print emails in the log instead.)")
    host = _ask_valid(io, "SMTP server", old.get("SMTP_HOST", ""), _one_line)
    if host == CONSOLE_SMTP:
        return {"SMTP_HOST": CONSOLE_SMTP}

    choices = ", ".join(security.value for security in SmtpSecurity)
    security = _ask_valid(
        io,
        f"Connection security ({choices})",
        old.get("SMTP_SECURITY", SmtpSecurity.STARTTLS.value),
        lambda value: None if value in {s.value for s in SmtpSecurity} else f"One of {choices}.",
    )
    port = _ask_valid(
        io,
        "Port",
        old.get("SMTP_PORT", str(SMTP_PORTS[SmtpSecurity(security)])),
        lambda value: None if value.isdigit() and 0 < int(value) < 65536 else "A port number.",
    )
    username = io.ask("User name (empty if none)", old.get("SMTP_USERNAME", "")).strip()
    password = old.get("SMTP_PASSWORD", "")
    if username:
        kept = " (Enter keeps the current one)" if password else ""
        typed = io.secret(f"Password{kept}")
        password = typed or password
    sender = _ask_valid(
        io,
        "Sender address",
        old.get("SMTP_FROM", f"HexTime <hextime@{email_domain}>"),
        _one_line,
    )
    return {
        "SMTP_HOST": host,
        "SMTP_PORT": port,
        "SMTP_SECURITY": security,
        "SMTP_USERNAME": username,
        "SMTP_PASSWORD": password if username else "",
        "SMTP_FROM": sender,
    }


def _settings(answers: Answers, secret_key: str, db_password: str) -> Settings:
    """The settings the server will run with, checked by the same rules."""
    smtp = answers.smtp
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_mode=AppMode.SERVER,
        auto_migrate=False,
        database_url=_database_url(db_password),
        public_base_url=f"https://{answers.domain}",
        allowed_email_domain=answers.email_domain,
        secret_key=secret_key,
        default_locale=answers.locale,
        allow_self_registration=answers.self_registration,
        smtp_host=smtp["SMTP_HOST"],
        smtp_port=int(smtp.get("SMTP_PORT") or 587),
        smtp_security=SmtpSecurity(smtp.get("SMTP_SECURITY") or SmtpSecurity.STARTTLS.value),
        smtp_username=smtp.get("SMTP_USERNAME") or None,
        smtp_password=smtp.get("SMTP_PASSWORD") or None,
        smtp_from=smtp.get("SMTP_FROM") or None,
    )


def _database_url(password: str) -> str:
    return f"postgresql+psycopg://{POSTGRES_USER}:{password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"


def _test_email(io: Io, checks: Checks, settings: Settings, to: str) -> str:
    """Send one; returns "ok", "edit" (ask the mail questions again) or "skip"."""
    if settings.smtp_host == CONSOLE_SMTP:
        return "ok"
    while True:
        io.say(f"Sending a test email to {to}...")
        try:
            checks.send_test_email(settings, to)
        except EmailFailedError as error:
            io.say(f"  It did not go: {error.__cause__ or error.message}")
            choice = io.ask("[r]etry, [e]dit the mail settings, or [s]kip", "e").lower()
            if choice.startswith("r"):
                continue
            return "skip" if choice.startswith("s") else "edit"
        io.say("  Sent. Check that it arrived (also in the spam folder).")
        return "ok"


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------


def run(
    config_dir: Path,
    io: Io | None = None,
    checks: Checks | None = None,
    host_addresses: list[str] | None = None,
    host_time_zone: str | None = None,
) -> Answers:
    """Ask, check and write. Raises SetupCancelledError if the administrator stops."""
    io = io or TerminalIo()
    checks = checks or Checks()
    config_dir.mkdir(parents=True, exist_ok=True)

    old = read_env(config_dir / APP_FILE)
    old_vars = read_vars(config_dir / VARS_FILE)
    old_postgres = read_env(config_dir / POSTGRES_FILE)
    rerun = bool(old)

    io.say("HexTime server setup" + (" (current values in brackets)" if rerun else ""))
    io.say()

    old_domain = old.get("PUBLIC_BASE_URL", "").removeprefix("https://")
    domain = _ask_valid(
        io, "Address people will open, e.g. hextime.example.org", old_domain, _hostname_problem
    ).lower()
    _check_dns(io, checks, domain, host_addresses or [])

    email_domain = _ask_valid(
        io,
        "Email domain allowed to have accounts",
        old.get("ALLOWED_EMAIL_DOMAIN", _parent_domain(domain)),
        _email_domain_problem,
    ).lower()
    locale = _ask_valid(
        io,
        f"Default language ({', '.join(SUPPORTED_LOCALES)})",
        old.get("DEFAULT_LOCALE", "fi"),
        lambda value: None if value in SUPPORTED_LOCALES else "Not a supported language.",
    )
    time_zone = _ask_valid(
        io,
        "Time zone for team reports, e.g. Europe/Helsinki",
        old.get("TIME_ZONE") or host_time_zone or "UTC",
        _time_zone_problem,
    )
    self_registration = _yes(
        io,
        f"May anyone @{email_domain} sign up without an invitation?",
        old.get("ALLOW_SELF_REGISTRATION", "false") == "true",
    )

    io.say()
    io.say("The first administrator. They get an email with a link to set a password.")
    admin_name = _ask_valid(io, "Name", old_vars.get("ADMIN_NAME", ""), _one_line)

    def admin_email_problem(value: str) -> str | None:
        if not EMAIL.match(value):
            return "That is not an email address."
        if value.lower().rpartition("@")[2] != email_domain:
            return f"The address must be @{email_domain}."
        return None

    admin_email = _ask_valid(
        io, "Email", old_vars.get("ADMIN_EMAIL", ""), admin_email_problem
    ).lower()

    secret_key = old.get("SECRET_KEY") or secrets.token_urlsafe(48)
    db_password = old_postgres.get("POSTGRES_PASSWORD") or secrets.token_urlsafe(32)

    answers = Answers(
        domain=domain,
        email_domain=email_domain,
        locale=locale,
        time_zone=time_zone,
        self_registration=self_registration,
        admin_name=admin_name,
        admin_email=admin_email,
    )
    smtp_defaults = old
    while True:
        answers.smtp = _ask_smtp(io, smtp_defaults, email_domain)
        try:
            settings = _settings(answers, secret_key, db_password)
        except ValidationError as error:
            io.say(f"  These settings would not start: {error.errors()[0]['msg']}")
            smtp_defaults = answers.smtp
            continue
        if _test_email(io, checks, settings, admin_email) != "edit":
            break
        smtp_defaults = answers.smtp

    _write(config_dir, answers, secret_key, db_password)
    io.say()
    io.say(f"Settings written to {config_dir}.")
    return answers


def _write(config_dir: Path, answers: Answers, secret_key: str, db_password: str) -> None:
    app = {
        "APP_MODE": AppMode.SERVER.value,
        "PUBLIC_BASE_URL": f"https://{answers.domain}",
        "ALLOWED_EMAIL_DOMAIN": answers.email_domain,
        "DEFAULT_LOCALE": answers.locale,
        "TIME_ZONE": answers.time_zone,
        "ALLOW_SELF_REGISTRATION": "true" if answers.self_registration else "false",
        "DATABASE_URL": _database_url(db_password),
        "SECRET_KEY": secret_key,
        **answers.smtp,
    }
    _write_private(config_dir / APP_FILE, _env_text("HexTime", app))
    _write_private(
        config_dir / POSTGRES_FILE,
        _env_text(
            "PostgreSQL",
            {
                "POSTGRES_DB": POSTGRES_DB,
                "POSTGRES_USER": POSTGRES_USER,
                "POSTGRES_PASSWORD": db_password,
            },
        ),
    )
    _write_private(config_dir / CADDY_FILE, _env_text("Caddy", {"HEXTIME_DOMAIN": answers.domain}))
    _write_private(
        config_dir / VARS_FILE,
        _vars_text(
            {
                "HEXTIME_DOMAIN": answers.domain,
                "ADMIN_NAME": answers.admin_name,
                "ADMIN_EMAIL": answers.admin_email,
            }
        ),
    )
