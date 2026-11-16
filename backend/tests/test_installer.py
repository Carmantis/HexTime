"""The installation questions (`hextime setup`), driven without a terminal.

Answers come from a list; DNS and the mail server are stand-ins that record
what they were asked. An empty answer takes the default, as Enter does.
"""

import stat
import subprocess
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import EmailFailedError
from app.installer import (
    APP_FILE,
    CADDY_FILE,
    POSTGRES_FILE,
    VARS_FILE,
    Checks,
    SetupCancelledError,
    _env_text,
    read_env,
    run,
)

SERVER_IP = "203.0.113.5"


class ScriptedIo:
    """Answers in order; complains instead of hanging when they run out."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.output: list[str] = []
        self.questions: list[str] = []

    def say(self, text: str = "") -> None:
        self.output.append(text)

    def _next(self, question: str) -> str:
        self.questions.append(question)
        if not self.answers:
            raise AssertionError(f"no answer left for {question!r}")
        return self.answers.pop(0)

    def ask(self, question: str, default: str = "") -> str:
        return self._next(question) or default

    def secret(self, question: str) -> str:
        return self._next(question)

    @property
    def text(self) -> str:
        return "\n".join(self.output)


class FakeWorld:
    """DNS answers and a mail server that can be told to fail."""

    def __init__(self, addresses: list[str] | None = None, failures: int = 0) -> None:
        self.addresses = [SERVER_IP] if addresses is None else addresses
        self.failures = failures
        self.sent: list[tuple[Settings, str]] = []

    def resolve(self, host: str) -> list[str]:
        return self.addresses

    def send(self, settings: Settings, to: str) -> None:
        if self.failures:
            self.failures -= 1
            raise EmailFailedError("the email could not be sent") from OSError("refused")
        self.sent.append((settings, to))

    @property
    def checks(self) -> Checks:
        return Checks(resolve=self.resolve, send_test_email=self.send)


#: A first installation, every question answered.
FRESH = [
    "hextime.example.org",  # address
    "",  # email domain: the default, example.org
    "",  # language: fi
    "Europe/Helsinki",  # time zone
    "",  # self-registration: no
    "Anna Admin",
    "Anna@Example.org",
    "smtp.example.org",
    "",  # security: starttls
    "",  # port: 587
    "hextime@example.org",  # SMTP user
    "mail password",  # SMTP password
    "",  # sender: the default
]


def install(
    tmp_path: Path, answers: list[str], world: FakeWorld | None = None
) -> tuple[ScriptedIo, FakeWorld]:
    io, world = ScriptedIo(answers), world or FakeWorld()
    run(tmp_path, io=io, checks=world.checks, host_addresses=[SERVER_IP])
    assert io.answers == [], "not every answer was asked for"
    return io, world


# ---------------------------------------------------------------------------
# A first installation
# ---------------------------------------------------------------------------


def test_a_fresh_install_writes_the_settings(tmp_path: Path) -> None:
    install(tmp_path, FRESH)

    app = read_env(tmp_path / APP_FILE)
    assert app["PUBLIC_BASE_URL"] == "https://hextime.example.org"
    assert app["ALLOWED_EMAIL_DOMAIN"] == "example.org"
    assert app["DEFAULT_LOCALE"] == "fi"
    assert app["ALLOW_SELF_REGISTRATION"] == "false"
    assert app["SMTP_HOST"] == "smtp.example.org"
    assert app["SMTP_PORT"] == "587"
    assert app["SMTP_SECURITY"] == "starttls"
    assert app["SMTP_PASSWORD"] == "mail password"
    assert app["SMTP_FROM"] == "HexTime <hextime@example.org>"
    assert read_env(tmp_path / CADDY_FILE) == {"HEXTIME_DOMAIN": "hextime.example.org"}


def test_secrets_are_generated_and_the_database_url_matches(tmp_path: Path) -> None:
    install(tmp_path, FRESH)

    app = read_env(tmp_path / APP_FILE)
    password = read_env(tmp_path / POSTGRES_FILE)["POSTGRES_PASSWORD"]
    assert len(app["SECRET_KEY"]) >= 48
    assert len(password) >= 32
    assert app["DATABASE_URL"] == (
        f"postgresql+psycopg://hextime:{password}@hextime-postgres:5432/hextime"
    )


def test_the_written_settings_start_a_server(tmp_path: Path) -> None:
    """The same validation the app runs at startup accepts them."""
    install(tmp_path, FRESH)

    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        **{key.lower(): value for key, value in read_env(tmp_path / APP_FILE).items()},
    )

    assert settings.is_server
    assert settings.cookie_secure


@pytest.mark.parametrize("name", [APP_FILE, POSTGRES_FILE, CADDY_FILE, VARS_FILE])
def test_only_the_owner_can_read_the_files(tmp_path: Path, name: str) -> None:
    install(tmp_path, FRESH)

    assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600


def test_a_test_email_goes_to_the_first_administrator(tmp_path: Path) -> None:
    _, world = install(tmp_path, FRESH)

    assert [to for _, to in world.sent] == ["anna@example.org"]


def test_the_installation_script_can_source_its_variables(tmp_path: Path) -> None:
    """Quoted for bash, so a name with quotes or $(...) is only a name."""
    tricky = "Anna 'Ö' $(touch pwned) `id`"
    answers = list(FRESH)
    answers[5] = tricky
    install(tmp_path, answers)

    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{tmp_path / VARS_FILE}"; printf "%s|%s|%s" '
            '"$HEXTIME_DOMAIN" "$ADMIN_NAME" "$ADMIN_EMAIL"',
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    assert result.stdout == f"hextime.example.org|{tricky}|anna@example.org"
    assert not (tmp_path / "pwned").exists()


# ---------------------------------------------------------------------------
# Running it again
# ---------------------------------------------------------------------------


def test_running_again_keeps_everything_with_enter(tmp_path: Path) -> None:
    install(tmp_path, FRESH)
    before = {name: (tmp_path / name).read_text() for name in (APP_FILE, POSTGRES_FILE)}

    # Enter at every question; an empty password keeps the current one.
    install(tmp_path, [""] * len(FRESH))

    after = {name: (tmp_path / name).read_text() for name in (APP_FILE, POSTGRES_FILE)}
    assert after == before


def test_running_again_changes_one_setting_but_never_the_secrets(tmp_path: Path) -> None:
    install(tmp_path, FRESH)
    secret = read_env(tmp_path / APP_FILE)["SECRET_KEY"]
    password = read_env(tmp_path / POSTGRES_FILE)["POSTGRES_PASSWORD"]

    answers = [""] * len(FRESH)
    answers[2] = "en"
    install(tmp_path, answers)

    app = read_env(tmp_path / APP_FILE)
    assert app["DEFAULT_LOCALE"] == "en"
    assert app["SECRET_KEY"] == secret
    assert read_env(tmp_path / POSTGRES_FILE)["POSTGRES_PASSWORD"] == password


# ---------------------------------------------------------------------------
# Wrong answers are asked again
# ---------------------------------------------------------------------------


def test_a_url_is_not_a_host_name(tmp_path: Path) -> None:
    io, _ = install(tmp_path, ["https://hextime.example.org/", *FRESH])

    assert "That is not a host name" in io.text


def test_the_administrator_must_be_in_the_email_domain(tmp_path: Path) -> None:
    answers = list(FRESH)
    answers[6:6] = ["anna@gmail.com"]
    io, _ = install(tmp_path, answers)

    assert "must be @example.org" in io.text


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------


def test_dns_pointing_elsewhere_can_stop_the_setup(tmp_path: Path) -> None:
    io = ScriptedIo(["hextime.example.org", "n"])
    world = FakeWorld(addresses=["198.51.100.7"])

    with pytest.raises(SetupCancelledError):
        run(tmp_path, io=io, checks=world.checks, host_addresses=[SERVER_IP])

    assert "points at 198.51.100.7" in io.text
    assert not (tmp_path / APP_FILE).exists()


def test_dns_not_set_up_yet_is_a_warning(tmp_path: Path) -> None:
    answers = list(FRESH)
    answers[1:1] = ["y"]  # continue anyway
    io, _ = install(tmp_path, answers, FakeWorld(addresses=[]))

    assert "does not resolve yet" in io.text
    assert (tmp_path / APP_FILE).exists()


# ---------------------------------------------------------------------------
# The test email
# ---------------------------------------------------------------------------


def test_a_failed_test_email_lets_the_settings_be_fixed(tmp_path: Path) -> None:
    answers = [*FRESH, "e", "smtp2.example.org", "", "", "", "", ""]
    io, world = install(tmp_path, answers, FakeWorld(failures=1))

    assert "It did not go: refused" in io.text
    assert read_env(tmp_path / APP_FILE)["SMTP_HOST"] == "smtp2.example.org"
    # The password typed the first time is the default the second time.
    assert read_env(tmp_path / APP_FILE)["SMTP_PASSWORD"] == "mail password"
    assert len(world.sent) == 1


def test_a_failed_test_email_can_be_skipped(tmp_path: Path) -> None:
    _, world = install(tmp_path, [*FRESH, "s"], FakeWorld(failures=1))

    assert world.sent == []
    assert read_env(tmp_path / APP_FILE)["SMTP_HOST"] == "smtp.example.org"


def test_console_mail_needs_no_mail_questions(tmp_path: Path) -> None:
    _, world = install(tmp_path, [*FRESH[:7], "console"])

    app = read_env(tmp_path / APP_FILE)
    assert app["SMTP_HOST"] == "console"
    assert "SMTP_FROM" not in app
    assert world.sent == []


def test_a_value_cannot_span_lines() -> None:
    with pytest.raises(ValueError, match="one line"):
        _env_text("x", {"SMTP_FROM": "a\nSECRET_KEY=mine"})


def test_the_time_zone_is_checked_and_written(tmp_path: Path) -> None:
    answers = list(FRESH)
    answers[3:3] = ["Mars/Olympus"]
    io, _ = install(tmp_path, answers)

    assert "not a time zone" in io.text
    assert read_env(tmp_path / APP_FILE)["TIME_ZONE"] == "Europe/Helsinki"


def test_the_servers_own_time_zone_is_the_default(tmp_path: Path) -> None:
    answers = list(FRESH)
    answers[3] = ""
    io, world = ScriptedIo(answers), FakeWorld()
    run(
        tmp_path,
        io=io,
        checks=world.checks,
        host_addresses=[SERVER_IP],
        host_time_zone="Europe/Stockholm",
    )

    assert read_env(tmp_path / APP_FILE)["TIME_ZONE"] == "Europe/Stockholm"
