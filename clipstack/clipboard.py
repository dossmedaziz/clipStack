"""Clipboard backends: read, write and watch the system clipboard.

Three backends, picked automatically by :func:`detect`:

``WaylandBackend``
    Compositors with the (wlr|ext)-data-control protocol (KDE Plasma, Sway,
    Hyprland, ...). Watches with ``wl-paste --watch``; reads with ``wl-paste``;
    writes with ``wl-copy``.

``GnomeWaylandBackend``
    GNOME (Mutter) does not implement data-control, so ``wl-paste --watch``
    refuses to run there. Mutter mirrors the Wayland clipboard into XWayland,
    so we watch for XFixes "selection owner changed" events through GTK's X11
    backend (event-based, no polling) and read with ``xclip``. Writing still
    uses ``wl-copy`` so native Wayland apps get the data directly.

``X11Backend``
    Classic X11 sessions: XFixes events through GTK, ``xclip`` for read/write.

Nothing in this module imports Gtk at import time, because the GDK backend
must be chosen (``GDK_BACKEND``) before Gtk is first imported.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

log = logging.getLogger("clipstack.clipboard")

# MIME type set by KeePassXC, KDE and others on secrets. Never record these.
PASSWORD_HINT = "x-kde-passwordManagerHint"

# Text targets in order of preference.
TEXT_TYPES = ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain",
              "STRING", "TEXT")
# Preferred image types; any other image/* is accepted after these.
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp")

READ_TIMEOUT = 3.0  # seconds; a frozen source app must not hang the daemon


class ClipboardError(Exception):
    """A clear, user-facing clipboard problem (missing tool, no display...)."""


def _require(tool: str, package: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ClipboardError(f"'{tool}' is not installed. Install it with: "
                             f"sudo apt install {package}")
    return path


def _read_limited(cmd: list[str], limit: int) -> bytes | None:
    """Run ``cmd`` and return its stdout, or None if it fails, times out,
    or produces more than ``limit`` bytes (the process is then killed)."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("cannot run %s: %s", cmd[0], exc)
        return None
    assert proc.stdout is not None
    # A frozen source app could block the read forever: kill after a timeout.
    timer = threading.Timer(READ_TIMEOUT, proc.kill)
    timer.start()
    chunks: list[bytes] = []
    total = 0
    too_big = False
    try:
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                too_big = True
                proc.kill()
                break
            chunks.append(chunk)
        proc.wait()
    finally:
        timer.cancel()
        proc.stdout.close()
    if too_big:
        log.info("clipboard item larger than %d bytes, not recorded", limit)
        return None
    if proc.returncode != 0:
        return None
    return b"".join(chunks)


def _run_input(cmd: list[str], data: bytes) -> None:
    """Pipe ``data`` into ``cmd``.

    wl-copy and xclip fork a background child that keeps serving the data, and
    that child inherits our pipes. So stderr goes to a temporary file (not a
    pipe, which would never reach EOF) and we only wait for the parent.
    """
    with tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                    stderr=err)
        except OSError as exc:
            raise ClipboardError(f"cannot run {cmd[0]}: {exc}") from exc
        assert proc.stdin is not None
        try:
            proc.stdin.write(data)
            proc.stdin.close()
            proc.wait(timeout=READ_TIMEOUT)
        except BrokenPipeError:
            proc.wait(timeout=READ_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise ClipboardError(f"{cmd[0]} timed out while setting the clipboard")
        if proc.returncode != 0:
            err.seek(0)
            msg = err.read().decode(errors="replace").strip()
            raise ClipboardError(f"{cmd[0]} failed: {msg or f'exit code {proc.returncode}'}")


def pick_text_type(targets: list[str]) -> str | None:
    for t in TEXT_TYPES:
        if t in targets:
            return t
    return None


def pick_image_type(targets: list[str]) -> str | None:
    for t in IMAGE_TYPES:
        if t in targets:
            return t
    for t in targets:
        if t.startswith("image/") and t != "image/svg+xml":
            return t
    return None


class Backend:
    """Common interface. Subclasses fill in the tool commands."""

    name = "base"
    #: True if :meth:`watch` needs GTK running on the X11 (or XWayland) backend.
    needs_x11_gtk = False

    def targets(self) -> list[str]:
        raise NotImplementedError

    def read(self, mime: str, limit: int) -> bytes | None:
        raise NotImplementedError

    def write(self, data: bytes, mime: str) -> None:
        raise NotImplementedError

    def write_text(self, text: str) -> None:
        self.write(text.encode("utf-8"), "text/plain;charset=utf-8")

    def write_file(self, path: str, mime: str) -> None:
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            raise ClipboardError(f"cannot read {path}: {exc}") from exc
        self.write(data, mime)

    def watch(self, on_change: Callable[[], None]) -> None:
        """Call ``on_change`` (from the GLib main loop) whenever the clipboard
        changes. The caller runs the main loop."""
        raise NotImplementedError

    def stop(self) -> None:
        pass


class WlCopyWriter(Backend):
    """Write-only backend using wl-copy (any Wayland compositor, incl. GNOME)."""

    name = "wl-copy"

    def __init__(self) -> None:
        _require("wl-copy", "wl-clipboard")

    def write(self, data: bytes, mime: str) -> None:
        # wl-copy forks and keeps serving the data after we return. For text/*
        # types it also offers the usual aliases (UTF8_STRING, STRING, ...).
        _run_input(["wl-copy", "--type", mime], data)


# ----------------------------------------------------------------- X11 --
class _XclipReader:
    """Read the clipboard through xclip (X11 or XWayland)."""

    def targets(self) -> list[str]:
        out = _read_limited(["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"],
                            1 << 16)
        if not out:
            return []
        return [t.strip() for t in out.decode("utf-8", "replace").splitlines() if t.strip()]

    def read(self, mime: str, limit: int) -> bytes | None:
        return _read_limited(["xclip", "-selection", "clipboard", "-o", "-t", mime], limit)


class _GtkOwnerWatch:
    """Watch XFixes selection-owner changes through GTK's X11 backend."""

    _clipboard = None
    _handler = 0

    def watch(self, on_change: Callable[[], None]) -> None:
        import gi
        gi.require_version("Gdk", "3.0")
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk, Gtk  # noqa: E402  (GDK_BACKEND set by caller)
        display = Gdk.Display.get_default()
        if display is None:
            raise ClipboardError("cannot connect to the X display (is $DISPLAY set?)")
        if "X11" not in type(display).__name__:
            raise ClipboardError("internal error: GTK is not using the X11 backend")
        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._handler = self._clipboard.connect("owner-change", lambda *_: on_change())

    def stop(self) -> None:
        if self._clipboard is not None and self._handler:
            self._clipboard.disconnect(self._handler)
            self._handler = 0


class X11Backend(_XclipReader, _GtkOwnerWatch, Backend):
    name = "x11"
    needs_x11_gtk = True

    def __init__(self) -> None:
        _require("xclip", "xclip")

    def write(self, data: bytes, mime: str) -> None:
        if mime.startswith("text/plain"):
            # No -t: xclip then offers UTF8_STRING, STRING, TEXT, ...
            _run_input(["xclip", "-selection", "clipboard", "-i"], data)
        else:
            _run_input(["xclip", "-selection", "clipboard", "-t", mime, "-i"], data)


class GnomeWaylandBackend(_XclipReader, _GtkOwnerWatch, WlCopyWriter):
    name = "gnome-wayland (XWayland bridge)"
    needs_x11_gtk = True

    def __init__(self) -> None:
        _require("xclip", "xclip")
        WlCopyWriter.__init__(self)


# ------------------------------------------------------------- Wayland --
class WaylandBackend(WlCopyWriter):
    name = "wayland (data-control)"

    def __init__(self) -> None:
        _require("wl-paste", "wl-clipboard")
        WlCopyWriter.__init__(self)
        self._proc: subprocess.Popen[bytes] | None = None
        self._watch_id = 0
        self._on_change: Callable[[], None] | None = None
        self._restarts = 0
        self._stopping = False

    def targets(self) -> list[str]:
        out = _read_limited(["wl-paste", "--list-types"], 1 << 16)
        if not out:
            return []
        return [t.strip() for t in out.decode("utf-8", "replace").splitlines() if t.strip()]

    def read(self, mime: str, limit: int) -> bytes | None:
        return _read_limited(["wl-paste", "--no-newline", "--type", mime], limit)

    def watch(self, on_change: Callable[[], None]) -> None:
        from gi.repository import GLib
        self._on_change = on_change
        # wl-paste runs the small shell command once per clipboard change and
        # passes the content on stdin (which we discard: the daemon reads the
        # types it wants afterwards). CLIPBOARD_STATE is set by wl-clipboard
        # >= 2.2 ("data", "nil", "clear" or "sensitive").
        cmd = ["wl-paste", "--watch", "sh", "-c",
               'cat >/dev/null; echo "${CLIPBOARD_STATE:-data}"']
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        assert self._proc.stdout is not None
        self._watch_id = GLib.io_add_watch(self._proc.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                                           GLib.IOCondition.IN | GLib.IOCondition.HUP,
                                           self._on_io)

    def _on_io(self, fd: int, cond: "object") -> bool:
        from gi.repository import GLib
        assert self._proc is not None and self._proc.stdout is not None
        line = self._proc.stdout.readline() if cond & GLib.IOCondition.IN else b""
        if not line:
            # wl-paste exited. Restart it a few times with a short delay.
            self._proc.wait()
            if not self._stopping and self._restarts < 5:
                self._restarts += 1
                log.warning("wl-paste --watch exited; restarting (%d/5)", self._restarts)
                GLib.timeout_add_seconds(2, self._restart)
            elif not self._stopping:
                log.error("wl-paste --watch keeps exiting; clipboard is no longer watched")
            return False
        state = line.decode(errors="replace").strip()
        if state == "sensitive":
            log.info("skipped clipboard item marked as sensitive")
        elif state == "data" and self._on_change:
            self._on_change()
        return True

    def _restart(self) -> bool:
        if self._on_change:
            self.watch(self._on_change)
        return False

    def stop(self) -> None:
        self._stopping = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ----------------------------------------------------------- detection --
def session_type() -> str:
    """'wayland', 'x11' or 'unknown'."""
    st = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if st in ("wayland", "x11"):
        return st
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def wayland_has_data_control() -> bool:
    """True if ``wl-paste --watch`` works on this compositor.

    On compositors without data-control (GNOME), wl-paste prints an error and
    exits at once; otherwise it keeps running and we stop it.
    """
    if not shutil.which("wl-paste"):
        return False
    try:
        proc = subprocess.Popen(["wl-paste", "--watch", "true"], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except OSError:
        return False
    try:
        proc.wait(timeout=0.7)
        return False  # exited by itself: not supported
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
        return True


def detect() -> Backend:
    """Pick the right backend for this session, or raise ClipboardError."""
    st = session_type()
    if st == "wayland":
        if wayland_has_data_control():
            return WaylandBackend()
        if os.environ.get("DISPLAY"):
            return GnomeWaylandBackend()
        raise ClipboardError(
            "this Wayland compositor does not support clipboard watching "
            "(no data-control protocol) and XWayland is not available")
    if st == "x11":
        return X11Backend()
    raise ClipboardError("no graphical session found ($WAYLAND_DISPLAY and $DISPLAY are unset)")


def writer() -> Backend:
    """A backend for *writing* only (used by the popup). Never probes watch support."""
    if session_type() == "wayland":
        return WlCopyWriter()
    return X11Backend()
