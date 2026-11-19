"""Add / remove the GNOME custom keyboard shortcut Super + B -> ``clipstack show``.

This edits the same settings as the ``gsettings`` command (dconf, per user):

* ``org.gnome.settings-daemon.plugins.media-keys custom-keybindings`` holds
  the list of custom shortcut paths. We *append* ours and never touch the
  others.
* Our entry lives at ``.../custom-keybindings/clipstack/``.

Before adding, every installed keybinding schema (window manager, shell,
media keys and all custom shortcuts) is checked; if Super + B is already
used we report what uses it and change nothing.
"""

from __future__ import annotations

import re

MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = MEDIA_KEYS + ".custom-keybinding"
LIST_KEY = "custom-keybindings"
BASE_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
OUR_PATH = BASE_PATH + "clipstack/"

BINDING = "<Super>b"
COMMAND = "clipstack show"
NAME = "ClipStack clipboard history"

_MOD_ALIASES = {"super": "super", "mod4": "super", "meta": "super",
                "ctrl": "ctrl", "control": "ctrl", "primary": "ctrl",
                "alt": "alt", "mod1": "alt", "shift": "shift"}


class ShortcutError(Exception):
    """GNOME settings are not available or could not be written."""


def normalize(accel: str) -> tuple[frozenset[str], str] | None:
    """Turn '<Super>B' / '<Mod4>b' into a comparable (modifiers, key) pair."""
    accel = accel.strip()
    if not accel or accel.lower() == "disabled":
        return None
    mods = frozenset(_MOD_ALIASES.get(m.lower(), m.lower())
                     for m in re.findall(r"<([^>]+)>", accel))
    key = re.sub(r"<[^>]+>", "", accel).strip().lower()
    return (mods, key) if key else None


def _gio():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    return Gio


def _source():
    Gio = _gio()
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(MEDIA_KEYS, True) is None \
            or source.lookup(CUSTOM_SCHEMA, True) is None:
        raise ShortcutError("GNOME keyboard settings were not found (is this GNOME?). "
                            f"Add a shortcut for '{COMMAND}' in your desktop's "
                            "keyboard settings instead.")
    return source


def _custom(path: str):
    Gio = _gio()
    return Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)


def _list_paths() -> list[str]:
    Gio = _gio()
    _source()
    return list(Gio.Settings.new(MEDIA_KEYS).get_strv(LIST_KEY))


def find_users(binding: str = BINDING) -> list[str]:
    """Describe every existing shortcut that already uses ``binding``
    (ClipStack's own entry is ignored)."""
    Gio = _gio()
    source = _source()
    wanted = normalize(binding)
    users: list[str] = []

    # 1) Built-in keybinding schemas (window manager, shell, media keys, ...)
    non_reloc, _reloc = source.list_schemas(True)
    for schema_id in non_reloc:
        if "keybindings" not in schema_id and "media-keys" not in schema_id:
            continue
        schema = source.lookup(schema_id, True)
        settings = Gio.Settings.new(schema_id)
        for key in schema.list_keys():
            vtype = schema.get_key(key).get_value_type().dup_string()
            if vtype == "as":
                values = settings.get_strv(key)
            elif vtype == "s":
                values = [settings.get_string(key)]
            else:
                continue
            if any(normalize(v) == wanted for v in values):
                users.append(f"{schema_id} {key}")

    # 2) Custom shortcuts made by the user (or other apps)
    for path in _list_paths():
        if path == OUR_PATH:
            continue
        c = _custom(path)
        if normalize(c.get_string("binding")) == wanted:
            users.append(f"custom shortcut '{c.get_string('name')}' "
                         f"(runs '{c.get_string('command')}', path {path})")
    return users


def is_installed() -> bool:
    try:
        return OUR_PATH in _list_paths()
    except ShortcutError:
        return False


def setup(binding: str = BINDING) -> tuple[bool, str]:
    """Add the shortcut. Returns (added, message). Never overwrites others."""
    Gio = _gio()
    paths = _list_paths()
    if OUR_PATH in paths:
        current = _custom(OUR_PATH).get_string("binding")
        return True, f"the ClipStack shortcut is already set up ({current})"

    users = find_users(binding)
    if users:
        lines = "\n  ".join(users)
        return False, (f"{binding} is already used by:\n  {lines}\n"
                       "ClipStack did not change it. Free that shortcut and run "
                       "'clipstack setup-shortcut' again, or pick another key in "
                       "Settings > Keyboard > Custom Shortcuts.")

    c = _custom(OUR_PATH)
    c.set_string("name", NAME)
    c.set_string("command", COMMAND)
    c.set_string("binding", binding)
    media = Gio.Settings.new(MEDIA_KEYS)
    if not media.set_strv(LIST_KEY, paths + [OUR_PATH]):
        raise ShortcutError("the custom-keybindings setting is read-only")
    Gio.Settings.sync()  # flush to dconf before the process exits
    return True, f"added shortcut {binding} -> '{COMMAND}'"


def remove() -> tuple[bool, str]:
    """Remove only ClipStack's shortcut. Returns (removed, message)."""
    Gio = _gio()
    paths = _list_paths()
    if OUR_PATH not in paths:
        return False, "the ClipStack shortcut is not installed"
    media = Gio.Settings.new(MEDIA_KEYS)
    media.set_strv(LIST_KEY, [p for p in paths if p != OUR_PATH])
    c = _custom(OUR_PATH)
    for key in ("name", "command", "binding"):
        c.reset(key)
    Gio.Settings.sync()
    return True, "removed the ClipStack shortcut"
