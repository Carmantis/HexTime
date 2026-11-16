"""Settings validation: local mode must stay zero-configuration, server mode
must refuse to start until it is fully configured."""

import pytest
from pydantic import ValidationError

from app.core.config import AppMode, Settings
from app.main import create_app
from tests.conftest import SERVER_SETTINGS, build_settings


def test_local_mode_is_the_default() -> None:
    settings = build_settings()
    assert settings.app_mode is AppMode.LOCAL
    assert not settings.is_server


def test_local_mode_needs_no_configuration() -> None:
    """A desktop user never edits a config file, so this must never raise."""
    assert build_settings().default_locale == "fi"


def test_server_mode_lists_every_missing_setting() -> None:
    with pytest.raises(ValidationError) as excinfo:
        build_settings(app_mode=AppMode.SERVER)

    message = str(excinfo.value)
    assert "allowed_email_domain" in message
    assert "public_base_url" in message
    assert "secret_key" in message
    assert "database_url" in message
    assert "smtp_host" in message


def test_a_real_mail_server_needs_a_sender_address() -> None:
    with pytest.raises(ValidationError, match="smtp_from"):
        build_settings(**SERVER_SETTINGS | {"smtp_host": "smtp.example.org"})


def test_the_console_mailer_needs_no_sender() -> None:
    assert build_settings(**SERVER_SETTINGS).mail_sender == "hextime@localhost"


def test_server_mode_rejects_the_placeholder_secret_key() -> None:
    with pytest.raises(ValidationError, match="secret_key"):
        build_settings(**SERVER_SETTINGS | {"secret_key": "change-me"})


def test_server_mode_accepts_complete_settings() -> None:
    settings = build_settings(**SERVER_SETTINGS)
    assert settings.is_server
    assert settings.allowed_email_domain == "example.org"


def test_unsupported_locale_is_rejected() -> None:
    with pytest.raises(ValidationError, match="default_locale"):
        build_settings(default_locale="sv")


def test_a_server_without_a_time_zone_warns(caplog: pytest.LogCaptureFixture) -> None:
    create_app(settings=build_settings(**SERVER_SETTINGS), serve_static=False)
    assert "TIME_ZONE is not set" in caplog.text

    caplog.clear()
    create_app(
        settings=build_settings(**SERVER_SETTINGS | {"time_zone": "Europe/Helsinki"}),
        serve_static=False,
    )
    assert "TIME_ZONE" not in caplog.text


def test_an_unknown_time_zone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="time_zone"):
        build_settings(time_zone="Mars/Olympus")


def test_app_mode_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "server")
    for key, value in SERVER_SETTINGS.items():
        if key != "app_mode":
            monkeypatch.setenv(key.upper(), str(value))

    assert Settings(_env_file=None).is_server
