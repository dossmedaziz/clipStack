"""Auto-paste into the previously focused window, and the fallback notification.

* X11: ``xdotool key --clearmodifiers ctrl+v``
* Wayland: ``ydotool`` (needs the ``ydotoold`` service and access to
  /dev/uinput). Used only if its socket exists and is writable; otherwise we
  just leave the item on the clipboard and show "Copied, press Ctrl+V".
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess

from . import clipboard

log = logging.getLogger("clipstack.paste")

# Linux input event codes used by ydotool: KEY_LEFTCTRL = 29, KEY_V = 47.
_YDOTOOL_CTRL_V = ["29:1", "47:1", "47:0", "29:0"]


def ydotool_socket() -> str | None:
    """Path of a usable ydotoold socket, or None."""
    candidates = [os.environ.get("YDOTOOL_SOCKET", ""),
                  os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), ".ydotool_socket"),
                  "/tmp/.ydotool_socket"]
    for path in candidates:
        if not path:
            continue
        try:
            if stat.S_ISSOCK(os.stat(path).st_mode) and os.access(path, os.W_OK):
                return path
        except OSError:
            continue
    return None


def ydotool_ready() -> bool:
    return shutil.which("ydotool") is not None and ydotool_socket() is not None


def can_auto_paste() -> bool:
    """True if a paste keystroke can be sent in this session."""
    st = clipboard.session_type()
    if st == "x11":
        return shutil.which("xdotool") is not None
    if st == "wayland":
        return ydotool_ready()
    return False


def send_paste() -> bool:
    """Send Ctrl+V to the focused window. Returns True on success."""
    st = clipboard.session_type()
    try:
        if st == "x11" and shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                           check=True, timeout=3, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return True
        if st == "wayland":
            sock = ydotool_socket()
            if sock and shutil.which("ydotool"):
                env = dict(os.environ, YDOTOOL_SOCKET=sock)
                subprocess.run(["ydotool", "key", *_YDOTOOL_CTRL_V], check=True,
                               timeout=3, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                return True
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("auto-paste failed: %s", exc)
    return False


def notify(summary: str, body: str = "") -> None:
    """Show a desktop notification over D-Bus (no extra packages needed)."""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        hints = {"transient": GLib.Variant("b", True),
                 "desktop-entry": GLib.Variant("s", "clipstack")}
        bus.call_sync("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                      "org.freedesktop.Notifications", "Notify",
                      GLib.Variant("(susssasa{sv}i)",
                                   ("ClipStack", 0, "clipstack", summary, body, [],
                                    hints, 2000)),
                      None, Gio.DBusCallFlags.NONE, 2000, None)
    except Exception as exc:  # noqa: BLE001 - a notification must never crash us
        log.info("notification failed: %s", exc)
