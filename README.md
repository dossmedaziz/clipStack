# ClipStack

A clipboard history for Ubuntu that works like **Win + V** on Windows.

ClipStack records what you copy (text, links and images). Press **Super + B**
to open a small popup with your recent items, pick one, and it is pasted into
the window you were using.

- Keeps the last 25 items (configurable). Pinned items are kept forever.
- Search as you type, pin, delete, clear all.
- Copying the same thing again moves it to the top instead of making a duplicate.
- Never records passwords copied from password managers (KeePassXC, KDE and
  others mark them with `x-kde-passwordManagerHint`).
- Ignores empty or whitespace-only text and items larger than 5 MB.
- Emoji & symbols tab.
- Works on Wayland and X11 (GNOME, KDE, Sway, …). Uses almost no CPU while idle:
  it reacts to clipboard events instead of polling.

---

## Install

### From the PPA (recommended)

```bash
sudo add-apt-repository ppa:MY_NAME/clipstack
sudo apt update
sudo apt install clipstack
```

### From a local `.deb`

```bash
sudo apt install ./clipstack_1.0.0_all.deb
```

`apt` installs all dependencies automatically (`python3-gi`, `gir1.2-gtk-3.0`,
`wl-clipboard`, `xclip`, `xdotool`).

After installing, **log out and log back in**. ClipStack starts automatically,
and the first time it starts it adds the **Super + B** shortcut for you. To start
it right away without logging out:

```bash
clipstack daemon &
```

---

## Usage

| Command | What it does |
|---|---|
| `clipstack daemon` | Records the clipboard (started automatically at login). `-v` prints debug messages. |
| `clipstack show` | Opens the popup. Running it again while it is open closes it. |
| `clipstack clear` | Deletes the history, keeps pinned items. |
| `clipstack setup-shortcut` | Adds the Super + B shortcut (if it is free). |
| `clipstack remove-shortcut` | Removes only ClipStack's shortcut. |
| `clipstack --version` | Prints the version. |

### Keys in the popup

| Key | Action |
|---|---|
| *type* | Search (the search box is focused when the popup opens) |
| ↑ / ↓ | Move through the list |
| Enter or click | Paste the selected item |
| Delete | Delete the selected item |
| P | Pin / unpin the selected item (when the list has focus; Ctrl + P works anywhere) |
| Ctrl + Tab | Switch between the Clipboard and Emoji tabs |
| Esc | Close (the popup also closes when you click elsewhere) |

The pin and trash buttons on each row do the same with the mouse. **Clear all**
asks for a second click to confirm and keeps pinned items.

### The shortcut

The daemon adds Super + B once per user, the first time it runs. It reads your
existing custom shortcuts and **adds** to the list, so your other shortcuts
are not deleted. If Super + B is already used, it prints what uses it and changes
nothing. To pick another key, open *Settings → Keyboard → View and Customize
Shortcuts → Custom Shortcuts*, edit "ClipStack clipboard history", or add your
own shortcut that runs `clipstack show`.

---

## Settings

Edit `~/.config/clipstack/config.json`. It is created the first time you run
the daemon. Changes apply to the next copy (no restart needed).

| Key | Default | Meaning |
|---|---|---|
| `max_items` | `25` | How many unpinned items to keep. Pinned items don't count. |
| `auto_paste` | `true` | Paste into the previous window after choosing an item. If `false` (or not possible), the item is copied and a "Copied, press Ctrl+V" notification is shown. |
| `paste_delay_ms` | `200` | Wait time before sending Ctrl+V, so the previous window gets the focus back. |
| `max_item_bytes` | `5242880` | Items larger than this (5 MB) are not recorded. |
| `ignore_apps` | `[]` | **X11 only.** Process names whose copies are not recorded, e.g. `["keepassxc", "bitwarden"]`. |
| `emoji_tab` | `true` | Show the Emoji & symbols tab. |
| `popup_width` / `popup_height` | `440` / `520` | Popup size in pixels. |
| `shortcut_configured` | – | Internal: ClipStack already tried to add the shortcut. |

Files:

- History: `~/.local/share/clipstack/history.db` (SQLite)
- Images: `~/.local/share/clipstack/images/`
- Settings: `~/.config/clipstack/config.json`

---

## Wayland vs X11

| | X11 | Wayland |
|---|---|---|
| Watching the clipboard | XFixes events + `xclip` | `wl-paste --watch` (KDE, Sway, Hyprland…); on GNOME see below |
| Popup position | Next to the mouse pointer | Centered on the current screen |
| Auto-paste | `xdotool key ctrl+v` | `ydotool`, only if set up (see below); otherwise "Copied, press Ctrl+V" |
| `ignore_apps` | Supported | Not supported |

**GNOME on Wayland.** GNOME does not support the *data-control* protocol that
`wl-paste --watch` needs (it fails with *"Watch mode requires a compositor that
supports the wlroots data-control protocol"*). GNOME does copy the Wayland
clipboard to XWayland, so on GNOME ClipStack listens for clipboard events
there and reads them with `xclip`. Writing uses `wl-copy`. This is event-based
too and works for both Wayland and X11 apps. The daemon prints which method it
uses: `clipstack daemon -v`.

**Popup position on Wayland.** Wayland apps can't read the global mouse
position or choose where their windows go. ClipStack asks to be centered and
the compositor places it. On GNOME this works when *center new windows* is on,
which is the Ubuntu default:

```bash
gsettings set org.gnome.mutter center-new-windows true
```

**Why the source app can't be detected on Wayland.** Wayland doesn't tell other
apps which program owns the clipboard or which window is focused, so
`ignore_apps` only works on X11. Password managers that set
`x-kde-passwordManagerHint` are skipped everywhere.

### Auto-paste on Wayland with ydotool (optional)

Wayland doesn't let apps send keystrokes to other apps. `ydotool` gets around this
by creating a virtual keyboard through `/dev/uinput`. Without it, ClipStack
copies the item and shows "Copied, press Ctrl+V".

> Security note: to use ydotool your user must be in the `input` group. That
> lets programs you run read and send raw keyboard/mouse events. Only enable
> it if you are fine with that.

```bash
sudo apt install ydotool
sudo usermod -aG input "$USER"      # then log out and back in
systemctl --user enable --now ydotool
```

Check that it works: `ydotool type hello` should type "hello". ClipStack uses
ydotool automatically once its socket (`$YDOTOOL_SOCKET`,
`$XDG_RUNTIME_DIR/.ydotool_socket` or `/tmp/.ydotool_socket`) exists. To turn
auto-paste off, set `"auto_paste": false`.

---

## Uninstall

**1. Remove the keyboard shortcut** (it is a per-user setting, so `apt`
can't remove it). Run this **before** removing the package:

```bash
clipstack remove-shortcut
```

If you already removed the package, use `gsettings` instead. This removes only
ClipStack's entry from the list:

```bash
P=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
  "$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
     | sed "s#, '$P/clipstack/'##; s#'$P/clipstack/', ##; s#'$P/clipstack/'##")"
dconf reset -f "$P/clipstack/"
```

**2. Remove the program:**

```bash
sudo apt remove clipstack     # program removed, nothing starts at next login
sudo apt purge clipstack      # same, plus the system-wide autostart file
```

**3. Remove your history and settings.** Packages never touch home folders, so
each user deletes their own data:

```bash
rm -rf ~/.local/share/clipstack ~/.config/clipstack
```

---

## Development

```bash
python3 -m unittest -v          # unit tests (storage, config)
python3 -m clipstack daemon -v  # run from the source tree
python3 -m clipstack show
debuild -us -uc -b              # build ../clipstack_1.0.0_all.deb
lintian ../clipstack_1.0.0_all.deb
```

Only Python 3's standard library and PyGObject are used. See
[docs/PUBLISHING.md](docs/PUBLISHING.md) to publish to a Launchpad PPA.

## License

MIT, see [LICENSE](LICENSE).
