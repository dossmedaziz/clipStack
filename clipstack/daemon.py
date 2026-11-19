"""``clipstack daemon``: watch the clipboard and save new items.

The daemon sleeps in the GLib main loop and only wakes up when the clipboard
changes (XFixes event or a line from ``wl-paste --watch``), so it uses no CPU
while idle.
"""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import sys
from typing import IO

from . import clipboard, config
from .storage import Storage, StorageError

log = logging.getLogger("clipstack.daemon")

DEBOUNCE_MS = 120  # several owner-change events often arrive for one copy


def _lock_file() -> IO[str] | None:
    """Take a per-user lock so only one daemon runs. None if already taken."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or str(config.data_dir())
    os.makedirs(runtime, exist_ok=True)
    fh = open(os.path.join(runtime, "clipstack-daemon.lock"), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def _active_app_x11() -> str | None:
    """X11 only: process name of the focused window (for ``ignore_apps``)."""
    import shutil
    import subprocess
    if clipboard.session_type() != "x11" or not shutil.which("xdotool"):
        return None
    try:
        out = subprocess.run(["xdotool", "getactivewindow", "getwindowpid"],
                             capture_output=True, text=True, timeout=2)
        pid = int(out.stdout.strip())
        with open(f"/proc/{pid}/comm", encoding="utf-8") as fh:
            return fh.read().strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class Daemon:
    def __init__(self, backend: clipboard.Backend, store: Storage) -> None:
        self.backend = backend
        self.store = store
        self._pending = 0

    # Called for every clipboard change event.
    def on_change(self) -> None:
        from gi.repository import GLib
        if self._pending:
            GLib.source_remove(self._pending)
        self._pending = GLib.timeout_add(DEBOUNCE_MS, self._capture)

    def _capture(self) -> bool:
        self._pending = 0
        try:
            self.capture()
        except StorageError as exc:
            log.error("%s", exc)
        except Exception:  # noqa: BLE001 - keep the daemon alive no matter what
            log.exception("unexpected error while saving a clipboard item")
        return False  # one-shot timeout

    def capture(self) -> None:
        """Read the current clipboard and store it if it should be kept."""
        cfg = config.load()  # re-read each time so edits apply without restart
        limit = int(cfg["max_item_bytes"])
        targets = self.backend.targets()
        if not targets:
            return
        if clipboard.PASSWORD_HINT in targets:
            log.info("skipped item from a password manager")
            return
        ignore = [a.casefold() for a in cfg.get("ignore_apps", [])]
        if ignore:
            app = _active_app_x11()
            if app and app.casefold() in ignore:
                log.info("skipped item copied from ignored app %s", app)
                return

        text_type = clipboard.pick_text_type(targets)
        if text_type:
            data = self.backend.read(text_type, limit)
            if data is None:
                return
            text = data.decode("utf-8", "replace")
            if not text.strip():
                return
            self.store.add_text(text, max_items=cfg["max_items"])
            log.debug("saved text (%d bytes)", len(data))
            return

        image_type = clipboard.pick_image_type(targets)
        if image_type:
            data = self.backend.read(image_type, limit)
            if data:
                self.store.add_image(data, image_type, max_items=cfg["max_items"])
                log.debug("saved %s (%d bytes)", image_type, len(data))


def first_run_shortcut() -> None:
    """Add the Super + B shortcut once per user (remembered in config.json)."""
    cfg = config.load()
    if cfg.get("shortcut_configured"):
        return
    from . import shortcut
    try:
        ok, message = shortcut.setup()
        log.info("%s", message)
    except shortcut.ShortcutError as exc:
        log.warning("could not add the keyboard shortcut: %s", exc)
        return  # try again next login
    config.update(shortcut_configured=True)


def run(verbose: bool = False) -> int:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="clipstack: %(message)s")
    lock = _lock_file()
    if lock is None:
        print("clipstack: the daemon is already running", file=sys.stderr)
        return 0

    try:
        backend = clipboard.detect()
    except clipboard.ClipboardError as exc:
        print(f"clipstack: {exc}", file=sys.stderr)
        return 1
    if backend.needs_x11_gtk:
        # Must happen before Gtk is imported anywhere in this process.
        os.environ["GDK_BACKEND"] = "x11"

    import gi
    gi.require_version("GLib", "2.0")
    from gi.repository import GLib

    try:
        store = Storage()
        store.trim(config.load()["max_items"])
    except StorageError as exc:
        print(f"clipstack: {exc}", file=sys.stderr)
        return 1

    first_run_shortcut()

    daemon = Daemon(backend, store)
    try:
        backend.watch(daemon.on_change)
    except clipboard.ClipboardError as exc:
        print(f"clipstack: {exc}", file=sys.stderr)
        return 1
    log.info("watching the clipboard using %s", backend.name)

    loop = GLib.MainLoop()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, lambda *_: (loop.quit(), False)[1])
    try:
        loop.run()
    finally:
        backend.stop()
        store.close()
        lock.close()
    return 0
