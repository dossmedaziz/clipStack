# Build ClipStack: a Win+V style clipboard history for Ubuntu
 
You are working in an empty Git repository at `~/projects/clipstack`.
Build **ClipStack**, a clipboard history manager for Ubuntu that works like the
Windows "Win + V" feature, and package it so it installs with `sudo apt install clipstack`.
 
All the tools are already installed (Python 3, PyGObject + GTK 3, wl-clipboard,
xclip, xdotool, ydotool, sqlite3, debhelper, dh-python, devscripts, lintian, dput, gnupg).
If you need anything else, tell me before installing it.
 
Before writing code, check my environment (`lsb_release -a`, `echo $XDG_SESSION_TYPE`,
`echo $XDG_CURRENT_DESKTOP`) and show me a short plan. Then build it step by step,
committing to Git after each working step.
 
---
 
## Tech stack (use exactly this)
 
| Part | Technology |
|---|---|
| Language | Python 3 (standard library + PyGObject only, no pip dependencies) |
| Popup window | GTK 3 via PyGObject |
| Clipboard on Wayland | `wl-paste --watch` / `wl-copy` |
| Clipboard on X11 | `xclip` |
| History storage | SQLite in `~/.local/share/clipstack/history.db` |
| Images | Saved as files in `~/.local/share/clipstack/images/`, path stored in SQLite |
| Settings | JSON in `~/.config/clipstack/config.json` |
| Shortcut | GNOME custom keybinding via `gsettings`: **Super + B** → `clipstack show` |
| Autostart | XDG autostart `.desktop` file running `clipstack daemon` |
| Packaging | Debian native package with `debhelper` + `dh-python` |
 
## Project structure
 
```
clipstack/
├── clipstack/
│   ├── __init__.py       # version
│   ├── __main__.py       # CLI: clipstack daemon | show | clear | setup-shortcut | remove-shortcut | --version
│   ├── daemon.py         # watches the clipboard and saves new items
│   ├── popup.py          # GTK popup window
│   ├── storage.py        # SQLite: add, list, search, pin, delete, clear, trim
│   ├── clipboard.py      # Wayland / X11 backends (read, write, watch)
│   ├── paste.py          # auto-paste (xdotool / ydotool / fallback)
│   ├── shortcut.py       # add / remove the Super + B GNOME shortcut safely
│   └── config.py         # load / save config.json with defaults
├── data/
│   ├── clipstack.desktop
│   ├── clipstack-autostart.desktop
│   └── clipstack.svg     # simple original icon
├── debian/
│   ├── changelog  control  copyright  rules  install
│   ├── postinst  prerm  postrm
│   └── source/format     # "3.0 (native)"
├── tests/                # unit tests for storage.py and config.py
├── docs/PUBLISHING.md
├── setup.py
├── README.md
└── LICENSE               # MIT
```
 
## Features
 
1. `clipstack daemon` runs in the background and records everything I copy
   (text, images, links). Low CPU and memory when idle (event-based watching, no busy polling).
2. Keep the last **25** items (configurable: `max_items` in config.json). Pinned items don't count toward the limit.
3. Pressing **Super + B** runs `clipstack show`, which opens a small popup.
   If the popup is already open, the same command closes it (toggle, single instance).
   - On X11, open it near the mouse cursor.
   - On Wayland, apps can't read the global cursor position, so center it on the
     current screen. Explain this in the README.
4. Items listed newest first, with a preview: first line of text (max ~80 chars),
   or a small thumbnail for images. Pinned items always at the top with a pin icon.
5. Click an item or press Enter → put it on the clipboard, close the popup, then paste
   into the previous window:
   - X11: `xdotool key ctrl+v`
   - Wayland: use `ydotool` only if it is set up and working; otherwise just copy
     and show a small notification "Copied, press Ctrl+V". Make this configurable
     (`auto_paste: true/false`) and document how to set up ydotool.
6. Pin / unpin items (button + `P` key). Pinned items survive reboot and "clear all".
7. Delete one item (button + `Delete` key) or "Clear all" (keeps pinned).
   Also `clipstack clear` on the command line.
8. Search box at the top, focused on open, filters as I type (case-insensitive).
9. Keyboard: arrows to move, Enter to paste, Delete to remove, P to pin, Esc to close.
   Close when the window loses focus.
10. If I copy the same thing again, move it to the top instead of making a duplicate.
11. Don't record items from password managers: skip clipboard content that carries the
    `x-kde-passwordManagerHint` MIME type (used by KeePassXC and others). Also add an
    `ignore_apps` list in config if you find a reliable way to detect the source app.
12. Ignore empty or whitespace-only text and items larger than 5 MB.
13. Optional (do last, only if everything else works): an emoji/symbols tab.
## Shortcut rules
 
- `clipstack setup-shortcut` adds the Super + B custom keybinding **without deleting
  my other custom shortcuts** (read the existing list from
  `org.gnome.settings-daemon.plugins.media-keys custom-keybindings` and append to it).
- Before adding it, check whether Super + B is already used. If it is, print what
  uses it and don't overwrite it.
- `clipstack remove-shortcut` removes only ClipStack's entry.
- `gsettings` changes are per-user, so the package's `postinst` can't set them for the
  user. Instead, the first time `clipstack daemon` runs for a user, it sets up the
  shortcut automatically (once; remember this in config.json).
## Packaging (apt install)
 
- Package name: `clipstack`, version `1.0.0`, architecture `all`.
- `debian/control` must list every runtime dependency (python3, python3-gi,
  gir1.2-gtk-3.0, wl-clipboard, xclip, xdotool) so apt installs them automatically.
  Put `ydotool` in `Suggests`.
- Install to standard places:
  - `/usr/bin/clipstack`
  - `/usr/share/applications/clipstack.desktop`
  - `/etc/xdg/autostart/clipstack-autostart.desktop`
  - `/usr/share/icons/hicolor/scalable/apps/clipstack.svg`
- `apt remove clipstack`: the program is removed; on next login nothing starts.
  Document the command a user runs to remove the shortcut (`clipstack remove-shortcut`
  before removing, or the gsettings command after).
- `apt purge clipstack`: same, and document that per-user data in
  `~/.local/share/clipstack` and `~/.config/clipstack` must be removed by the user
  (packages must not touch home folders).
- Build with `debuild -us -uc -b`, then run `lintian` on the .deb and fix all errors
  and as many warnings as reasonable.
- Test the install for real: `sudo apt install ./../clipstack_1.0.0_all.deb`,
  start the daemon, copy a few things, run `clipstack show`, then remove it again.
  Tell me which steps I need to check by hand (like pressing Super + B).
## Publishing guide
 
Don't publish anything yourself. Write `docs/PUBLISHING.md`, a clear step-by-step guide for me:
 
1. Create a Launchpad account and a PPA named `clipstack`.
2. Create a GPG key, upload it to keyserver.ubuntu.com, add it to Launchpad.
3. Build a signed source package (`debuild -S`) and upload with `dput ppa:MY_NAME/clipstack`.
4. Support Ubuntu 22.04, 24.04 and newer (changelog distribution names, one upload per release).
5. Release a new version later (`dch -i`, rebuild, upload) so users get it with `sudo apt upgrade`.
6. Alternative: host my own APT repository for free on GitHub Pages.
The final user install should be:
 
```
sudo add-apt-repository ppa:MY_NAME/clipstack
sudo apt update
sudo apt install clipstack
```
 
## Quality
 
- Clean, commented code. Type hints. Handle errors (missing tools, clipboard empty,
  database locked) with clear messages instead of crashes.
- Unit tests in `tests/` for storage and config; run them with `python3 -m unittest`.
- `README.md`: what it is, install (PPA + local .deb), usage, keyboard keys,
  config options, Wayland vs X11 notes, uninstall.
## When you finish
 
Give me a short summary: what works, what I must test by hand, any Wayland limits,
and the exact next command to run.
 