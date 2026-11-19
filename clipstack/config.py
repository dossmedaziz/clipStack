"""Load and save ClipStack settings (``~/.config/clipstack/config.json``).

Unknown keys are kept, missing keys fall back to defaults, and values of the
wrong type are replaced by the default so a hand-edited file can never crash
the program.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Default settings. Every key the program reads must be listed here.
DEFAULTS: dict[str, Any] = {
    # How many unpinned items to keep. Pinned items do not count.
    "max_items": 25,
    # Paste into the previous window after choosing an item.
    # X11 uses xdotool; Wayland uses ydotool only if it works.
    "auto_paste": True,
    # Delay (milliseconds) between closing the popup and sending Ctrl+V,
    # so the previous window has time to get the keyboard focus back.
    "paste_delay_ms": 200,
    # Items bigger than this are not recorded (bytes). 5 MB.
    "max_item_bytes": 5 * 1024 * 1024,
    # X11 only: WM_CLASS names of apps whose copies are not recorded,
    # e.g. ["keepassxc", "1password"]. Case-insensitive.
    "ignore_apps": [],
    # Show the emoji / symbols tab in the popup.
    "emoji_tab": True,
    # Popup size in pixels.
    "popup_width": 440,
    "popup_height": 520,
    # Internal: set to true after the daemon has tried to add the
    # Super + B shortcut once, so it never touches your keybindings again.
    "shortcut_configured": False,
}


def config_dir() -> Path:
    """Return the config folder, honouring ``$XDG_CONFIG_HOME``."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "clipstack"


def data_dir() -> Path:
    """Return the data folder, honouring ``$XDG_DATA_HOME``."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "clipstack"


def config_path() -> Path:
    return config_dir() / "config.json"


def _validate(key: str, value: Any) -> bool:
    """True if ``value`` has an acceptable type/range for ``key``."""
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        # bool is a subclass of int; reject it for numeric settings.
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(default))


def load(path: Path | None = None) -> dict[str, Any]:
    """Return the settings merged with defaults.

    A missing file gives the defaults. A broken file prints a warning and
    gives the defaults (the broken file is left untouched for the user).
    """
    path = path or config_path()
    cfg: dict[str, Any] = dict(DEFAULTS)
    cfg["ignore_apps"] = list(DEFAULTS["ignore_apps"])
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as exc:
        print(f"clipstack: cannot read {path}: {exc}; using default settings",
              file=sys.stderr)
        return cfg
    if not isinstance(raw, dict):
        print(f"clipstack: {path} is not a JSON object; using default settings",
              file=sys.stderr)
        return cfg
    for key, value in raw.items():
        if key in DEFAULTS:
            if _validate(key, value):
                cfg[key] = value
            else:
                print(f"clipstack: invalid value for '{key}' in {path}: {value!r}; "
                      f"using default {DEFAULTS[key]!r}", file=sys.stderr)
        else:
            cfg[key] = value  # keep unknown keys (forward compatibility)
    if cfg["max_items"] < 1:
        cfg["max_items"] = 1
    return cfg


def save(cfg: dict[str, Any], path: Path | None = None) -> None:
    """Write settings atomically (temp file + rename)."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update(path: Path | None = None, **changes: Any) -> dict[str, Any]:
    """Load, change some keys, save, and return the new settings."""
    cfg = load(path)
    cfg.update(changes)
    save(cfg, path)
    return cfg
