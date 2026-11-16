"""The desktop entry point, without opening a window.

pywebview is not needed here: the window is the one part left untested, and
everything it relies on (the lock, the server thread, saving a file) is.
"""

import base64
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from app import desktop
from app.core.startup import DatabaseTooNewError
from app.desktop import (
    ServerThread,
    WindowSlot,
    ask_running_copy_to_show,
    bind_socket,
    desktop_router,
    language_code,
    make_save_file,
    read_port,
    single_instance,
    write_port,
)
from tests.conftest import build_settings

# ---------------------------------------------------------------------------
# One copy at a time
# ---------------------------------------------------------------------------


def test_a_second_copy_does_not_get_the_lock(tmp_path: Path) -> None:
    lock = tmp_path / "hextime.lock"
    with single_instance(lock) as first, single_instance(lock) as second:
        assert first is True
        assert second is False


def test_the_lock_is_free_again_after_the_first_copy_ends(tmp_path: Path) -> None:
    lock = tmp_path / "hextime.lock"
    with single_instance(lock) as first:
        assert first
    with single_instance(lock) as again:
        assert again


def test_the_port_file_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "hextime.port"
    write_port(path, 47612)
    assert read_port(path) == 47612


def test_a_missing_or_garbled_port_file_reads_as_none(tmp_path: Path) -> None:
    path = tmp_path / "hextime.port"
    assert read_port(path) is None
    path.write_text("not a port")
    assert read_port(path) is None


# ---------------------------------------------------------------------------
# The server thread
# ---------------------------------------------------------------------------


def test_a_taken_port_falls_back_to_a_free_one() -> None:
    taken = bind_socket(None)
    taken.listen()
    try:
        other = bind_socket(taken.getsockname()[1])
        assert other.getsockname()[1] != taken.getsockname()[1]
        other.close()
    finally:
        taken.close()


def test_the_server_migrates_answers_and_stops(tmp_path: Path) -> None:
    database = tmp_path / "hextime.db"
    settings = build_settings(database_url=f"sqlite+pysqlite:///{database}", auto_migrate=True)
    server = ServerThread(settings, preferred_port=None)

    server.start()
    try:
        with urllib.request.urlopen(f"{server.url}api/v1/config", timeout=5) as response:
            assert json.load(response)["mode"] == "local"
        # The lifespan ran the migrations before the server reported ready.
        assert database.is_file()
        assert server.url.startswith("http://127.0.0.1:")
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# A second launch raises the first copy's window
# ---------------------------------------------------------------------------


class FakeWindow:
    def __init__(self) -> None:
        self.restored = 0

    def restore(self) -> None:
        self.restored += 1


def test_a_second_launch_raises_the_running_window(tmp_path: Path) -> None:
    slot = WindowSlot()
    slot.window = FakeWindow()
    settings = build_settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'h.db'}")
    server = ServerThread(settings, preferred_port=None, extra_routers=[desktop_router(slot.show)])

    server.start()
    try:
        assert ask_running_copy_to_show(server.port) is True
    finally:
        server.stop()

    assert slot.window.restored == 1


def test_no_running_copy_answers_false() -> None:
    sock = bind_socket(None)
    port = sock.getsockname()[1]
    sock.close()  # Nothing listens there now.

    assert ask_running_copy_to_show(port, timeout=0.5) is False


def test_showing_before_the_window_exists_does_nothing() -> None:
    WindowSlot().show()  # Must not raise while the window is still opening.


def test_the_show_route_is_only_on_the_desktop_server(api_client) -> None:
    """The plain app (and so server mode) has no such route."""
    assert api_client.post("/api/v1/desktop/show").status_code in (404, 405)


# ---------------------------------------------------------------------------
# Saving a file from the page
# ---------------------------------------------------------------------------


def test_the_page_can_save_a_file_where_the_user_chose(tmp_path: Path) -> None:
    target = tmp_path / "chosen.pdf"
    asked: list[str] = []

    def ask(filename: str) -> str:
        asked.append(filename)
        return str(target)

    saved = make_save_file(ask)("report.pdf", base64.b64encode(b"%PDF-1.4").decode())

    assert saved is True
    assert target.read_bytes() == b"%PDF-1.4"
    assert asked == ["report.pdf"]


def test_cancelling_the_dialog_saves_nothing(tmp_path: Path) -> None:
    assert make_save_file(lambda filename: None)("report.pdf", "") is False
    assert list(tmp_path.iterdir()) == []


def test_the_page_cannot_suggest_a_folder() -> None:
    asked: list[str] = []
    make_save_file(lambda name: asked.append(name))("../../etc/report.pdf", "")

    assert asked == ["report.pdf"]


def test_importing_the_module_does_not_need_pywebview() -> None:
    """The server build has no pywebview; the module must still import."""
    code = "import sys, app.desktop; sys.exit('webview' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).parents[1], check=False
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("fi_FI", "fi"),
        ("fi-FI.UTF-8", "fi"),
        ("Finnish_Finland", "fi"),
        ("English_United States", "en"),
        ("en_US", "en"),
        ("sv_SE", "sv"),
        ("fi@euro", "fi"),
        ("fi:en", "fi"),
        ("", ""),
    ],
)
def test_language_codes_from_linux_and_windows_names(name: str, code: str) -> None:
    assert language_code(name) == code


def test_a_finnish_windows_gets_the_finnish_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows sets none of the variables; its locale has the long name."""
    monkeypatch.setattr(desktop, "_windows_ui_locale", lambda: None)
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(desktop.locale, "getlocale", lambda: ("Finnish_Finland", "1252"))

    assert desktop.system_language() == "fi"


def test_an_unsupported_language_falls_back_to_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop, "_windows_ui_locale", lambda: None)
    monkeypatch.setenv("LANGUAGE", "")
    monkeypatch.setenv("LC_ALL", "")
    monkeypatch.setenv("LC_MESSAGES", "")
    monkeypatch.setenv("LANG", "sv_SE.UTF-8")

    assert desktop.system_language() == "en"


# ---------------------------------------------------------------------------
# Starting: the database is prepared once, before the server, and a problem
# with it is shown in a window
# ---------------------------------------------------------------------------


class Started:
    """Stands in for the server and the windows, recording what main() did."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.prepared = 0
        self.server_settings: object = None
        self.problems: list[tuple[str, str]] = []
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setattr(desktop, "get_settings", lambda: build_settings())
        monkeypatch.setattr(desktop, "system_language", lambda: "fi")
        monkeypatch.setattr(desktop, "show_problem", lambda *text: self.problems.append(text))
        monkeypatch.setattr(desktop, "open_window", lambda *args: None)
        started = self

        class FakeServer:
            port = 1
            url = "http://127.0.0.1:1/"

            def __init__(self, settings: object, **kwargs: object) -> None:
                started.server_settings = settings

            def start(self) -> None: ...

            def stop(self) -> None: ...

        monkeypatch.setattr(desktop, "ServerThread", FakeServer)

    def prepare_fails_with(self, monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
        def prepare(settings: object) -> None:
            self.prepared += 1
            raise error

        monkeypatch.setattr(desktop, "prepare_local_database", prepare)


def test_the_database_is_prepared_once_and_the_server_does_not_migrate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started = Started(monkeypatch, tmp_path)

    def prepare(settings: object) -> None:
        started.prepared += 1

    monkeypatch.setattr(desktop, "prepare_local_database", prepare)

    desktop.main()

    assert started.prepared == 1
    assert started.server_settings.auto_migrate is False  # type: ignore[attr-defined]


def test_a_database_from_a_newer_version_is_shown_in_a_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started = Started(monkeypatch, tmp_path)
    started.prepare_fails_with(monkeypatch, DatabaseTooNewError("revision f00d"))

    with pytest.raises(SystemExit) as stop:
        desktop.main()

    assert stop.value.code == 1
    assert [title for title, _ in started.problems] == ["Päivitä HexTime"]
    assert started.server_settings is None


def test_any_other_start_up_problem_is_shown_in_a_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started = Started(monkeypatch, tmp_path)
    started.prepare_fails_with(monkeypatch, OSError("disk full"))

    with pytest.raises(SystemExit):
        desktop.main()

    [(title, body)] = started.problems
    assert title == "HexTime ei käynnistynyt"
    assert "disk full" in body
    assert str(tmp_path) in body


def test_the_message_language_wins_over_lang_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop, "_windows_ui_locale", lambda: None)
    monkeypatch.setenv("LANGUAGE", "")
    monkeypatch.setenv("LC_ALL", "")
    monkeypatch.setenv("LC_MESSAGES", "fi_FI.UTF-8")
    monkeypatch.setenv("LANG", "en_US.UTF-8")

    assert desktop.system_language() == "fi"
