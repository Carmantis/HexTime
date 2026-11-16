"""PyInstaller runtime hook: use the system's GTK and WebKitGTK on Linux.

hextime.spec leaves the GTK stack out of the Linux bundle, because WebKitGTK
cannot be bundled sensibly (it starts helper processes from system paths) and
a bundled GTK next to the system's WebKit would mix two versions. PyInstaller's
own GTK runtime hooks have already pointed GTK at the bundle by the time this
runs; this hook points it back at the system.
"""

import os
import sys

if sys.platform == "linux":
    for name in (
        "GI_TYPELIB_PATH",
        "GTK_DATA_PREFIX",
        "GTK_EXE_PREFIX",
        "GTK_PATH",
        "PANGO_LIBDIR",
        "PANGO_SYSCONFDIR",
        "GDK_PIXBUF_MODULE_FILE",
        "GIO_MODULE_DIR",
    ):
        os.environ.pop(name, None)

    bundled_share = os.path.join(sys._MEIPASS, "share")  # type: ignore[attr-defined]
    data_dirs = [
        path
        for path in os.environ.get("XDG_DATA_DIRS", "").split(os.pathsep)
        if path and path != bundled_share
    ]
    os.environ["XDG_DATA_DIRS"] = os.pathsep.join(data_dirs or ["/usr/local/share", "/usr/share"])
