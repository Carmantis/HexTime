"""Application settings.

Every setting is read here and nowhere else. No other module may touch
``os.environ``. Routers and services receive the settings through
``Depends(get_settings)`` so tests can substitute their own.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from platformdirs import user_data_dir
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Names the OS data directory for the desktop build.
APP_NAME = "HexTime"

SUPPORTED_LOCALES: tuple[str, ...] = ("fi", "en")

#: Refusing to start server mode with this value keeps an unconfigured
#: deployment from signing sessions with a publicly known key.
PLACEHOLDER_SECRET_KEY = "change-me"


#: SMTP_HOST=console prints emails to the log instead of sending them; for
#: trying server mode on a laptop, never for production.
CONSOLE_SMTP = "console"


class SmtpSecurity(StrEnum):
    """How the connection to the mail server is protected."""

    STARTTLS = "starttls"  # port 587, the usual choice (Microsoft 365, Gmail)
    SSL = "ssl"  # port 465
    NONE = "none"  # an internal relay that accepts plain connections


class AppMode(StrEnum):
    """The two ways this one codebase can run."""

    LOCAL = "local"
    SERVER = "server"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment and an optional .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_mode: AppMode = AppMode.LOCAL
    database_url: str | None = None
    default_locale: str = "fi"

    #: Migrate the database when the app starts, so `uvicorn app.main:app`
    #: in development needs no separate step. The desktop window migrates
    #: before it starts the server, and the container entrypoint and the
    #: tests run `alembic upgrade head` themselves; all of them turn it off.
    auto_migrate: bool = True

    # Server mode only. Validated below so local mode stays zero-configuration.
    allowed_email_domain: str | None = None
    public_base_url: str | None = None
    secret_key: str = PLACEHOLDER_SECRET_KEY
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_security: SmtpSecurity = SmtpSecurity.STARTTLS
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    #: How long a sign-in lasts without being used. Each use starts it again,
    #: so someone working daily stays signed in.
    session_days: int = 14
    #: Server mode: anyone with an address in allowed_email_domain may sign
    #: up. Off by default; people then join only when an administrator adds
    #: them.
    allow_self_registration: bool = False
    #: The organisation's time zone, an IANA name. A team report counts whole
    #: days in this zone whatever the browser says, so a member cannot narrow
    #: the range to read when colleagues worked (decided 2026-10-08: totals
    #: only). One's own reports use the browser's zone.
    time_zone: str = "UTC"

    @property
    def is_server(self) -> bool:
        """True when running as the multi-user web app."""
        return self.app_mode is AppMode.SERVER

    @model_validator(mode="after")
    def _check_default_locale(self) -> Self:
        if self.default_locale not in SUPPORTED_LOCALES:
            raise ValueError(
                f"default_locale must be one of {', '.join(SUPPORTED_LOCALES)}, "
                f"got {self.default_locale!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_time_zone(self) -> Self:
        try:
            ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"time_zone is not a known time zone: {self.time_zone!r}") from exc
        return self

    @model_validator(mode="after")
    def _check_server_requirements(self) -> Self:
        """Fail fast rather than start a half-configured server."""
        if not self.is_server:
            return self

        missing = [
            name
            for name in ("allowed_email_domain", "public_base_url", "database_url")
            if not getattr(self, name)
        ]
        if self.secret_key == PLACEHOLDER_SECRET_KEY:
            missing.append("secret_key")
        # Without mail, nobody can be invited or reset a password, and that
        # would only show once somebody tried. Refuse to start instead.
        if not self.smtp_host:
            missing.append("smtp_host")
        elif self.smtp_host != CONSOLE_SMTP and not self.smtp_from:
            missing.append("smtp_from")

        if missing:
            raise ValueError("server mode requires these settings: " + ", ".join(sorted(missing)))
        return self

    @property
    def mail_sender(self) -> str:
        """The From address; the console mailer gets by without one."""
        return self.smtp_from or "hextime@localhost"

    @property
    def cookie_secure(self) -> bool:
        """Send the session cookie over HTTPS only, when the site is HTTPS.

        Production always is (Caddy terminates TLS); a plain-HTTP address is
        only for trying server mode on localhost.
        """
        return bool(self.public_base_url and self.public_base_url.startswith("https://"))

    @property
    def local_database_path(self) -> Path:
        """Where the desktop build keeps its SQLite file.

        platformdirs returns the OS-native location (%APPDATA%\\HexTime on
        Windows, ~/.local/share/HexTime on Linux). Data never goes next to the
        executable: an installed program may not be able to write there.
        """
        return Path(user_data_dir(APP_NAME, appauthor=False)) / "hextime.db"

    @property
    def resolved_database_url(self) -> str:
        """The URL to connect to, filling in the local-mode default.

        Server mode always has an explicit DATABASE_URL because the validator
        above refuses to start without one.
        """
        if self.database_url:
            return self.database_url
        return f"sqlite+pysqlite:///{self.local_database_path}"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, built once on first use."""
    return Settings()
