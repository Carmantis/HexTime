"""The desktop build: HexTime in its own window, no browser and no terminal.

    uv run --extra desktop python -m app.desktop

The FastAPI app runs in a background thread on 127.0.0.1 and pywebview shows
it in a native window: Edge WebView2 on Windows, WebKitGTK on Linux. Closing
the window stops the server.

Only one copy may own the database at a time. A second launch starts neither
a server nor a window: it asks the running copy to bring its window to the
front, and exits. (Two windows would also share one WebKit storage folder,
which WebKit locks; the second window then stops answering, even to "close".)

pywebview is imported inside the functions that draw windows, never at the
top: it belongs to the optional "desktop" extra, and the server build and the
test suite must be able to import this module without it.
"""

import base64
import html
import locale
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

import uvicorn
from fastapi import APIRouter, status

from app.core.config import Settings, get_settings
from app.core.csrf import CSRF_HEADER
from app.core.i18n import resolve_locale, translator
from app.core.startup import DatabaseTooNewError, prepare_local_database
from app.main import STATIC_DIR, create_app

HOST = "127.0.0.1"

#: Theme and language live in the window's localStorage, which belongs to the
#: origin *including the port*. A stable port keeps them from one run to the
#: next; a random one is only the fallback when this one is taken.
#: (HexStickyNote's sidecar uses 47613, so this is deliberately different.)
PREFERRED_PORT = 47612

#: The window and taskbar icon; `npm run build` copies it from frontend/public.
ICON = STATIC_DIR / "hextime.png"

STARTUP_TIMEOUT = 30.0
#: How long a second launch keeps trying to reach the first, which may still
#: be starting up.
SHOW_TIMEOUT = 10.0
WINDOW_SIZE = (1280, 800)
MIN_WINDOW_SIZE = (900, 600)


# ---------------------------------------------------------------------------
# One copy at a time
# ---------------------------------------------------------------------------


def _lock(file: IO[str]) -> bool:
    """Take an exclusive OS lock on an open file without waiting.

    The operating system drops the lock when the process ends, crash included,
    so a stale lock file can never keep HexTime from starting.
    """
    try:
        if sys.platform == "win32":
            import msvcrt

            # Windows locks a byte range from the current position.
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextmanager
def single_instance(lock_path: Path) -> Iterator[bool]:
    """Yield True if this process got the lock, False if another copy has it."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as file:
        yield _lock(file)
    # Closing the file releases the lock.


def write_port(port_path: Path, port: int) -> None:
    port_path.write_text(str(port), encoding="utf-8")


def read_port(port_path: Path) -> int | None:
    """The running copy's port, or None if the file is missing or garbled."""
    try:
        return int(port_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


class WindowSlot:
    """The open window, once there is one, for the server thread to reach."""

    def __init__(self) -> None:
        self.window: Any = None

    def show(self) -> None:
        """Bring the window to the front, un-minimising it if need be.

        Safe from any thread: pywebview hands the call to the GUI thread. On
        Wayland the compositor decides whether the window really gets focus;
        at worst it is marked as wanting attention.
        """
        if self.window is not None:
            self.window.restore()


def desktop_router(show: Callable[[], None]) -> APIRouter:
    """Routes only the desktop window's server has.

    POST /api/v1/desktop/show is how a second launch reaches the first. It
    only raises the window, so there is nothing to protect behind it.
    """
    router = APIRouter(prefix="/api/v1/desktop", tags=["desktop"])

    @router.post("/show", status_code=status.HTTP_204_NO_CONTENT)
    def show_window() -> None:
        show()

    return router


def ask_running_copy_to_show(port: int, timeout: float = SHOW_TIMEOUT) -> bool:
    """Ask the copy on `port` to raise its window. False if it never answered."""
    request = urllib.request.Request(
        f"http://{HOST}:{port}/api/v1/desktop/show",
        method="POST",
        # Every state-changing request needs it, this one included (app/core/csrf.py)
        headers={CSRF_HEADER: "1"},
    )
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status == status.HTTP_204_NO_CONTENT
        except (urllib.error.URLError, OSError):
            if time.monotonic() > deadline:
                return False
            time.sleep(0.25)


# ---------------------------------------------------------------------------
# The server thread
# ---------------------------------------------------------------------------


def bind_socket(preferred: int | None) -> socket.socket:
    """A listening-ready socket on the loopback, on `preferred` if it is free.

    Binding here and handing the socket to uvicorn, instead of picking a
    number and letting uvicorn bind it later, leaves no gap in which another
    program could take the port.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != "win32":
        # Lets a restart reuse the port at once instead of after a timeout.
        # (On Windows this option means something else and would allow two
        # programs on one port, so it is left off there.)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if preferred is not None:
        try:
            sock.bind((HOST, preferred))
            return sock
        except OSError:
            pass
    sock.bind((HOST, 0))
    return sock


class ServerThread:
    """The FastAPI app served by uvicorn in a background thread."""

    def __init__(
        self,
        settings: Settings,
        preferred_port: int | None = PREFERRED_PORT,
        extra_routers: Sequence[APIRouter] = (),
    ) -> None:
        self._sock = bind_socket(preferred_port)
        self.port: int = self._sock.getsockname()[1]
        config = uvicorn.Config(
            create_app(settings, extra_routers=extra_routers),
            log_level="warning",
            # Whatever the lifespan does (desktop.main() has already migrated
            # and turns that off), a failure there must stop the start-up
            # rather than leave a window onto a broken server.
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._sock]}, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    def start(self, timeout: float = STARTUP_TIMEOUT) -> None:
        """Start serving and wait until requests are answered."""
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive():
                raise RuntimeError("HexTime's server stopped during start-up")
            if time.monotonic() > deadline:
                raise RuntimeError(f"HexTime's server did not start within {timeout:.0f} s")
            time.sleep(0.05)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
        self._sock.close()


# ---------------------------------------------------------------------------
# What the page can ask of the window
# ---------------------------------------------------------------------------

#: Asks the user where to save; returns the chosen path or None if cancelled.
SaveDialog = Callable[[str], str | None]


def make_save_file(ask_where_to_save: SaveDialog) -> Callable[[str, str], bool]:
    """The function the page calls as ``window.pywebview.api.save_file``.

    A browser saves a download by itself; an embedded web view has no
    download manager, so the page hands the file over (base64, because the
    bridge carries JSON) and the window shows the system's "Save as" dialog.
    """

    def save_file(filename: str, data_base64: str) -> bool:
        """Save a file the page fetched. False when the user cancels."""
        # Only the name: the page must not choose the folder.
        path = ask_where_to_save(Path(filename).name)
        if not path:
            return False
        Path(path).write_bytes(base64.b64decode(data_base64))
        return True

    return save_file


def _save_dialog(window: Any) -> SaveDialog:
    def ask(filename: str) -> str | None:
        import webview

        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=("PDF (*.pdf)", "All files (*.*)"),
        )
        # Depending on the back end the answer is a string or a sequence.
        if isinstance(chosen, str):
            return chosen or None
        return chosen[0] if chosen else None

    return ask


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def open_window(url: str, storage_path: Path, slot: WindowSlot) -> None:
    """Show HexTime at `url` and block until the window is closed."""
    if sys.platform == "linux":
        # WebKitGTK's DMABUF renderer crashes or draws a blank window on many
        # Wayland setups, NVIDIA in particular ("Error 71 (Protocol error)").
        # HexStickyNote sets the same. It must be in place before GTK starts.
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")

    import webview

    window = webview.create_window(
        "HexTime",
        url,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_WINDOW_SIZE,
        # Our own CSS decides what is selectable (inputs yes, chrome no).
        text_select=True,
        # The dark theme's background, so the window does not flash white.
        background_color="#0d1117",
    )
    if window is not None:
        # expose() rather than a js_api object: only this one function
        # becomes callable from the page.
        window.expose(make_save_file(_save_dialog(window)))
        slot.window = window

    # Private mode would forget localStorage, and with it the chosen theme
    # and language, every time the window closes.
    webview.start(
        private_mode=False,
        storage_path=str(storage_path),
        icon=str(ICON) if ICON.is_file() else None,
    )


#: The long names Windows gives locales ("Finnish_Finland"), for the
#: languages HexTime has.
WINDOWS_LANGUAGE_NAMES = {"finnish": "fi", "english": "en"}


def language_code(name: str) -> str:
    """The language part of a locale name.

    Takes "fi_FI", "fi-FI.UTF-8", "fi@euro" or Windows' "Finnish_Finland",
    and gives "fi".
    """
    first = name.replace("-", "_").split(":")[0]
    for separator in (".", "@", "_"):
        first = first.split(separator)[0]
    first = first.strip().lower()
    return WINDOWS_LANGUAGE_NAMES.get(first, first)


def _windows_ui_locale() -> str | None:
    """The language Windows itself is shown in, as "fi_FI"; None elsewhere."""
    if sys.platform != "win32":
        return None
    import ctypes

    ui_language = ctypes.windll.kernel32.GetUserDefaultUILanguage
    ui_language.restype = ctypes.c_ushort  # a LANGID is 16 bits
    return locale.windows_locale.get(ui_language())


def _message_locale() -> str:
    """Where gettext looks for the message language, in its order, on Linux."""
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable)
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return value
    return locale.getlocale()[0] or ""


def system_language() -> str:
    """The OS language for messages shown before the app's own UI exists."""
    return resolve_locale(language_code(_windows_ui_locale() or _message_locale()), "en")


def show_problem(title: str, text: str) -> None:
    """A small window with one message, for a problem that stops the start.

    The user started a desktop app; a message only on a terminal they never
    opened would look like the app silently failing to start.
    """
    import webview

    page = (
        "<body style='font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;"
        "margin:0;padding:32px;line-height:1.5'>"
        f"<h2 style='margin-top:0'>{html.escape(title)}</h2>"
        f"<p>{html.escape(text)}</p></body>"
    )
    webview.create_window(title, html=page, width=560, height=300, background_color="#0d1117")
    webview.start()


def main() -> None:
    settings = get_settings()
    if settings.is_server:
        sys.exit("The desktop window is for local mode; server mode runs in a container.")

    data_dir = settings.local_database_path.parent
    storage = data_dir / "webview"

    with single_instance(data_dir / "hextime.lock") as owner:
        if not owner:
            # Another copy owns the database: bring its window forward.
            port = read_port(data_dir / "hextime.port")
            if port is None or not ask_running_copy_to_show(port):
                sys.exit("HexTime is already running.")
            return

        # Here rather than in the server's start-up, which runs in a thread:
        # a problem with the database must reach the user as a window.
        try:
            prepare_local_database(settings)
        except DatabaseTooNewError as error:
            t = translator(system_language())
            print(f"HexTime: {error}", file=sys.stderr)
            show_problem(t("desktop.tooNewTitle"), t("desktop.tooNewBody"))
            sys.exit(1)
        except Exception as error:
            # A locked or read-only file, a full disk, a failed migration.
            traceback.print_exc()
            t = translator(system_language())
            show_problem(
                t("desktop.startFailedTitle"),
                t("desktop.startFailedBody", error=error, folder=data_dir),
            )
            sys.exit(1)

        slot = WindowSlot()
        server = ServerThread(
            settings.model_copy(update={"auto_migrate": False}),
            extra_routers=[desktop_router(slot.show)],
        )
        server.start()
        write_port(data_dir / "hextime.port", server.port)
        try:
            open_window(server.url, storage, slot)
        finally:
            server.stop()


if __name__ == "__main__":
    main()
