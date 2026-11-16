# PyInstaller spec for the desktop build.
#
#   cd frontend && npm ci && npm run build
#   cd backend && uv run --extra desktop pyinstaller hextime.spec --noconfirm
#
# Output: dist/hextime/ — a folder with the `hextime` executable and everything
# it needs. A folder ("onedir") rather than one self-extracting file: it starts
# faster, because nothing is unpacked to a temporary directory on every launch,
# and the installers (packaging/) ship the folder as it is.
#
# PyInstaller does not cross-compile: build on Windows for Windows and on Linux
# for Linux. CI does both (.github/workflows/release.yml).

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)
APP = HERE / "app"

if not (APP / "static" / "index.html").is_file():
    raise SystemExit("The UI is not built: run `npm run build` in frontend/ first.")

# Files the app reads at run time, placed where the code expects them:
# app/core/startup.py looks for alembic.ini and alembic/ two levels above
# itself, which in the bundle is its root.
datas = [
    (str(HERE / "alembic.ini"), "."),
    (str(HERE / "alembic"), "alembic"),
    (str(APP / "static"), "app/static"),
    (str(APP / "i18n"), "app/i18n"),
    (str(APP / "reports" / "fonts"), "app/reports/fonts"),
    # IANA time zones: Windows has no system database for zoneinfo to use.
    *collect_data_files("tzdata"),
    # ReportLab's own font metrics and resources.
    *collect_data_files("reportlab"),
]

hiddenimports = [
    # Alembic loads env.py and the migrations from files, and uvicorn picks
    # its protocol implementations by name, so the analysis cannot see them.
    *collect_submodules("app"),
    *collect_submodules("uvicorn"),
    *collect_submodules("alembic"),
]

if sys.platform == "linux":
    # pywebview chooses its GTK back end at run time.
    hiddenimports += ["webview.platforms.gtk", "gi.repository.WebKit2"]
    # PyGObject's Python-side fixes to the GLib and GTK APIs (GLib.idle_add
    # taking a function first, for one). PyInstaller's gi hooks add them only
    # when they can find the typelibs at build time, which fails on Ubuntu;
    # without them the window stays blank. Listed here so every build has them.
    hiddenimports += collect_submodules("gi.overrides")
elif sys.platform == "win32":
    hiddenimports += ["webview.platforms.edgechromium", "webview.platforms.winforms"]

a = Analysis(
    [str(APP / "desktop.py")],
    pathex=[str(HERE)],
    datas=datas,
    hiddenimports=hiddenimports,
    # Test and server-only tools never run in the desktop build.
    excludes=["pytest", "ruff", "psycopg", "tkinter"],
    runtime_hooks=[str(HERE / "pyinstaller" / "rthook_system_gtk.py")],
    noarchive=False,
)

if sys.platform == "linux":
    # Use the system's GTK and WebKitGTK instead of bundling them; see
    # pyinstaller/rthook_system_gtk.py for why. The .deb declares them as
    # dependencies. Without this filter PyInstaller also copies every icon
    # theme on the build machine, several hundred megabytes of them.
    SYSTEM_LIBS = ("/usr/lib", "/lib", "/usr/lib64", "/lib64")
    GTK_DATA = ("share/", "gi_typelibs/", "lib/gdk-pixbuf", "etc/", "gio_modules/")
    a.binaries = [entry for entry in a.binaries if not entry[1].startswith(SYSTEM_LIBS)]
    a.datas = [entry for entry in a.datas if not entry[0].startswith(GTK_DATA)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hextime",
    # A windowed app: no console window behind it on Windows.
    console=False,
    # The .exe's own icon in Explorer and the taskbar (Windows only).
    icon=str(HERE.parent / "packaging" / "icons" / "hextime.ico"),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="hextime", upx=False)
