"""``clipstack show``: the GTK 3 history popup.

Single instance through Gtk.Application (D-Bus): running ``clipstack show``
while the popup is open closes it, so one shortcut toggles it.

Keys
  type          filter the list (search box is focused on open)
  Up / Down     move through the list
  Enter         paste the selected item (or click it)
  Delete        delete the selected item
  P             pin / unpin the selected item (when the list has focus)
  Ctrl+P        pin / unpin from anywhere
  Esc           close (the popup also closes when it loses focus)
"""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, clipboard, config, paste  # noqa: E402
from .storage import Item, Storage, StorageError  # noqa: E402

log = logging.getLogger("clipstack.popup")

THUMB_W, THUMB_H = 160, 72

CSS = b"""
.clipstack-window { border-radius: 10px; }
.clipstack-row { padding: 6px 8px; }
.clipstack-row.pinned:not(:selected) { background-color: alpha(@theme_selected_bg_color, 0.10); }
.clipstack-preview { font-size: 10.5pt; }
.clipstack-meta { opacity: 0.6; font-size: 8.5pt; }
.clipstack-row button { padding: 2px; min-height: 0; min-width: 0; opacity: 0.55; }
.clipstack-row button:hover { opacity: 1; }
.clipstack-row button.active { opacity: 1; color: @theme_selected_bg_color; }
.clipstack-row:selected button, .clipstack-row:selected button.active { color: inherit; }
.clipstack-empty { opacity: 0.6; padding: 24px; }
.clipstack-emoji flowboxchild { font-size: 17pt; padding: 4px; border-radius: 6px; }
"""


def _icon(name: str, fallback: str) -> str:
    theme = Gtk.IconTheme.get_default()
    return name if theme and theme.has_icon(name) else fallback


class ItemRow(Gtk.ListBoxRow):
    """One history entry: preview + pin and delete buttons."""

    def __init__(self, item: Item, popup: "Popup") -> None:
        super().__init__()
        self.item = item
        ctx = self.get_style_context()
        ctx.add_class("clipstack-row")
        if item.pinned:
            ctx.add_class("pinned")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        if item.pinned:
            box.pack_start(Gtk.Image.new_from_icon_name(
                _icon("view-pin-symbolic", "starred-symbolic"), Gtk.IconSize.MENU),
                False, False, 0)

        if item.is_image:
            box.pack_start(self._thumbnail(item), False, False, 0)
            label = Gtk.Label(label=item.preview, xalign=0)
            label.get_style_context().add_class("clipstack-meta")
            box.pack_start(label, True, True, 0)
        else:
            if item.kind == "link":
                box.pack_start(Gtk.Image.new_from_icon_name("insert-link-symbolic",
                                                            Gtk.IconSize.MENU),
                               False, False, 0)
            label = Gtk.Label(label=item.preview, xalign=0)
            label.set_ellipsize(3)  # Pango.EllipsizeMode.END
            label.set_single_line_mode(True)
            label.get_style_context().add_class("clipstack-preview")
            box.pack_start(label, True, True, 0)
            tip = item.content if len(item.content) <= 600 else item.content[:600] + "…"
            self.set_tooltip_text(tip)

        pin = Gtk.Button.new_from_icon_name(_icon("view-pin-symbolic", "starred-symbolic"),
                                            Gtk.IconSize.MENU)
        pin.set_relief(Gtk.ReliefStyle.NONE)
        pin.set_can_focus(False)
        pin.set_tooltip_text("Unpin (P)" if item.pinned else "Pin (P)")
        if item.pinned:
            pin.get_style_context().add_class("active")
        pin.connect("clicked", lambda *_: popup.toggle_pin(self))

        delete = Gtk.Button.new_from_icon_name("edit-delete-symbolic", Gtk.IconSize.MENU)
        delete.set_relief(Gtk.ReliefStyle.NONE)
        delete.set_can_focus(False)
        delete.set_tooltip_text("Delete (Delete)")
        delete.connect("clicked", lambda *_: popup.delete(self))

        box.pack_end(delete, False, False, 0)
        box.pack_end(pin, False, False, 0)
        self.add(box)

    @staticmethod
    def _thumbnail(item: Item) -> Gtk.Widget:
        try:
            # Scale large images down (keeping aspect); never scale small ones up.
            _fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(item.content)
            if w and h and (w > THUMB_W or h > THUMB_H):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(item.content, THUMB_W,
                                                                THUMB_H, True)
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(item.content)
            return Gtk.Image.new_from_pixbuf(pixbuf)
        except GLib.Error:
            return Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.DND)


class Popup(Gtk.ApplicationWindow):
    def __init__(self, app: "PopupApp") -> None:
        super().__init__(application=app, title="ClipStack")
        self.app = app
        self.cfg = config.load()
        self.store = app.store
        self._had_focus = False
        self._closing = False
        self._clear_armed = 0

        self.set_icon_name("clipstack")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_default_size(self.cfg["popup_width"], self.cfg["popup_height"])
        self.get_style_context().add_class("clipstack-window")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(8)
        self.add(outer)

        # --- top bar: search + clear all ---
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search = Gtk.SearchEntry(placeholder_text="Search clipboard history")
        self.search.connect("search-changed", lambda *_: self.reload())
        top.pack_start(self.search, True, True, 0)
        self.clear_btn = Gtk.Button(label="Clear all")
        self.clear_btn.set_tooltip_text("Delete all items except pinned ones")
        self.clear_btn.set_can_focus(False)
        self.clear_btn.connect("clicked", self._on_clear)
        top.pack_end(self.clear_btn, False, False, 0)
        outer.pack_start(top, False, False, 0)

        # --- clipboard list ---
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect("row-activated", lambda _lb, row: self.choose(row))
        self.empty = Gtk.Label(label="Nothing copied yet.\nCopy some text or an image.",
                               justify=Gtk.Justification.CENTER)
        self.empty.get_style_context().add_class("clipstack-empty")
        self.empty.show()
        self.listbox.set_placeholder(self.empty)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(self.listbox)

        self.emoji_page: Gtk.Widget | None = None
        if self.cfg.get("emoji_tab"):
            try:
                from . import emoji
                self.emoji_page = emoji.EmojiPage(self.choose_text)
            except ImportError:
                self.emoji_page = None
        if self.emoji_page is not None:
            self.notebook = Gtk.Notebook()
            self.notebook.append_page(scroll, Gtk.Label(label="Clipboard"))
            self.notebook.append_page(self.emoji_page, Gtk.Label(label="Emoji & symbols"))
            self.notebook.set_can_focus(False)
            self.notebook.connect("switch-page", lambda *_: GLib.idle_add(self.reload))
            outer.pack_start(self.notebook, True, True, 0)
        else:
            self.notebook = None
            outer.pack_start(scroll, True, True, 0)

        self.connect("key-press-event", self._on_key)
        self.connect("focus-in-event", self._on_focus_in)
        self.connect("focus-out-event", self._on_focus_out)
        self.reload()

    # ------------------------------------------------------------ data --
    def _on_emoji_tab(self) -> bool:
        return self.notebook is not None and self.notebook.get_current_page() == 1

    def reload(self, keep_index: int | None = None, select_id: int | None = None,
               focus_list: bool = False) -> bool:
        """Rebuild the list. Selection goes to ``select_id`` if given, else to
        ``keep_index`` (clamped), else to the top row."""
        query = self.search.get_text()
        self.clear_btn.set_visible(not self._on_emoji_tab())
        if self._on_emoji_tab():
            assert self.emoji_page is not None
            self.emoji_page.filter(query)  # type: ignore[attr-defined]
            return False
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        try:
            items = self.store.search(query)
        except StorageError as exc:
            self.empty.set_text(f"Cannot read history:\n{exc}")
            return False
        self.empty.set_text("No matches." if query else
                            "Nothing copied yet.\nCopy some text or an image.")
        for item in items:
            self.listbox.add(ItemRow(item, self))
        self.listbox.show_all()
        rows = self.listbox.get_children()
        if rows:
            idx = min(keep_index or 0, len(rows) - 1)
            for r in rows:
                if select_id is not None and r.item.id == select_id:
                    idx = r.get_index()
                    break
            self.listbox.select_row(rows[idx])
            if focus_list:
                rows[idx].grab_focus()
        return False

    def _selected(self) -> ItemRow | None:
        row = self.listbox.get_selected_row()
        return row if isinstance(row, ItemRow) else None

    # --------------------------------------------------------- actions --
    def toggle_pin(self, row: ItemRow) -> None:
        in_list = not self.search.has_focus()
        try:
            self.store.toggle_pin(row.item.id)
        except StorageError as exc:
            log.error("%s", exc)
        self.reload(select_id=row.item.id, focus_list=in_list)

    def delete(self, row: ItemRow) -> None:
        in_list = not self.search.has_focus()
        idx = row.get_index()
        try:
            self.store.delete(row.item.id)
        except StorageError as exc:
            log.error("%s", exc)
        self.reload(keep_index=idx, focus_list=in_list)

    def _on_clear(self, *_: object) -> None:
        # Two clicks: the first one asks for confirmation for 3 seconds.
        if not self._clear_armed:
            self.clear_btn.set_label("Click to confirm")
            self._clear_armed = GLib.timeout_add_seconds(3, self._disarm_clear)
            return
        GLib.source_remove(self._clear_armed)
        self._disarm_clear()
        try:
            self.store.clear()
        except StorageError as exc:
            log.error("%s", exc)
        self.reload()

    def _disarm_clear(self) -> bool:
        self._clear_armed = 0
        self.clear_btn.set_label("Clear all")
        return False

    def choose(self, row: Gtk.ListBoxRow) -> None:
        """Put the item on the clipboard, close, then paste."""
        if not isinstance(row, ItemRow):
            return
        item = row.item
        try:
            writer = clipboard.writer()
            if item.is_image:
                writer.write_file(item.content, item.mime or "image/png")
            else:
                writer.write_text(item.content)
        except clipboard.ClipboardError as exc:
            paste.notify("ClipStack could not copy", str(exc))
            self.close_popup()
            return
        try:
            self.store.touch(item.id)
        except StorageError as exc:
            log.warning("%s", exc)
        self._finish_with_paste()

    def choose_text(self, text: str) -> None:
        """Used by the emoji tab: copy text without recording a history row."""
        try:
            clipboard.writer().write_text(text)
        except clipboard.ClipboardError as exc:
            paste.notify("ClipStack could not copy", str(exc))
            self.close_popup()
            return
        self._finish_with_paste()

    def _finish_with_paste(self) -> None:
        self._closing = True
        self.hide()  # give the focus back to the previous window
        delay = int(self.cfg.get("paste_delay_ms", 200))
        GLib.timeout_add(delay, self._paste_and_quit)

    def _paste_and_quit(self) -> bool:
        pasted = False
        if self.cfg.get("auto_paste") and paste.can_auto_paste():
            pasted = paste.send_paste()
        if not pasted:
            paste.notify("Copied", "Press Ctrl+V to paste")
        self.app.quit()
        return False

    def close_popup(self) -> None:
        self._closing = True
        self.app.quit()

    # ---------------------------------------------------------- events --
    def _on_focus_in(self, *_: object) -> bool:
        self._had_focus = True
        return False

    def _on_focus_out(self, *_: object) -> bool:
        # Close when the user clicks somewhere else. Wait a moment, because
        # focus can bounce briefly while the window is being mapped.
        if self._had_focus and not self._closing:
            GLib.timeout_add(150, self._close_if_unfocused)
        return False

    def _close_if_unfocused(self) -> bool:
        if not self.is_active() and not self._closing:
            self.close_popup()
        return False

    def _move_selection(self, step: int) -> None:
        rows = self.listbox.get_children()
        if not rows:
            return
        cur = self.listbox.get_selected_row()
        idx = cur.get_index() if cur else -1
        idx = max(0, min(len(rows) - 1, idx + step))
        self.listbox.select_row(rows[idx])
        rows[idx].grab_focus()

    def _on_key(self, _w: Gtk.Widget, ev: Gdk.EventKey) -> bool:
        key = ev.keyval
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        in_search = self.search.has_focus()

        if key == Gdk.KEY_Escape:
            self.close_popup()
            return True
        if ctrl and key in (Gdk.KEY_Page_Down, Gdk.KEY_Page_Up, Gdk.KEY_Tab) \
                and self.notebook is not None:
            self.notebook.set_current_page(1 - self.notebook.get_current_page())
            return True
        if self._on_emoji_tab():
            if key in (Gdk.KEY_Down, Gdk.KEY_Up) and in_search:
                self.emoji_page.focus_first()  # type: ignore[union-attr]
                return True
            if in_search or key in (Gdk.KEY_Down, Gdk.KEY_Up, Gdk.KEY_Left,
                                    Gdk.KEY_Right, Gdk.KEY_Return, Gdk.KEY_KP_Enter,
                                    Gdk.KEY_space, Gdk.KEY_Tab):
                return False
            return self.search.handle_event(ev) or self._refocus_search()

        row = self._selected()
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if row is not None:
                self.choose(row)
            return True
        if ctrl and key in (Gdk.KEY_p, Gdk.KEY_P):
            if row is not None:
                self.toggle_pin(row)
            return True

        if in_search:
            if key == Gdk.KEY_Down:
                # Move focus into the list, starting at the selected (top) row.
                self._move_selection(0)
                return True
            if key == Gdk.KEY_Delete and row is not None and \
                    self.search.get_position() >= len(self.search.get_text()):
                self.delete(row)
                return True
            return False

        # Focus is in the list.
        if key == Gdk.KEY_Up and row is not None and row.get_index() == 0:
            self.search.grab_focus_without_selecting()
            return True
        if key in (Gdk.KEY_Up, Gdk.KEY_Down):
            self._move_selection(-1 if key == Gdk.KEY_Up else +1)
            return True
        if key == Gdk.KEY_Delete and row is not None:
            self.delete(row)
            return True
        if key in (Gdk.KEY_p, Gdk.KEY_P) and not ctrl and row is not None:
            self.toggle_pin(row)
            return True
        # Any other typing goes to the search box.
        if (ev.string and ev.string.isprintable()) or key == Gdk.KEY_BackSpace:
            self._refocus_search()
            return self.search.handle_event(ev) or True
        return False

    def _refocus_search(self) -> bool:
        self.search.grab_focus_without_selecting()
        return False

    # -------------------------------------------------------- placement --
    def place(self) -> None:
        """X11: open near the mouse. Wayland: let the compositor center it."""
        w, h = self.cfg["popup_width"], self.cfg["popup_height"]
        display = Gdk.Display.get_default()
        if clipboard.session_type() == "x11" and display is not None:
            seat = display.get_default_seat()
            pointer = seat.get_pointer() if seat else None
            if pointer is not None:
                _screen, x, y = pointer.get_position()
                monitor = display.get_monitor_at_point(x, y)
                area = monitor.get_workarea()
                nx = max(area.x, min(x - 20, area.x + area.width - w))
                ny = max(area.y, min(y - 20, area.y + area.height - h))
                self.move(nx, ny)
                return
        # Wayland clients cannot read the global pointer position or choose
        # their own position: ask for "center" and the compositor places it
        # (GNOME centers it with org.gnome.mutter center-new-windows = true).
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)


class PopupApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: Popup | None = None
        self.store: Storage | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self) -> None:
        # Second "clipstack show" while open -> close (toggle).
        if self.window is not None:
            self.window.close_popup()
            return
        try:
            self.store = Storage()
        except StorageError as exc:
            paste.notify("ClipStack", str(exc))
            print(f"clipstack: {exc}", file=sys.stderr)
            self.quit()
            return
        self.window = Popup(self)
        self.window.place()
        self.window.show_all()
        self.window.present()
        self.window.search.grab_focus()

    def do_shutdown(self) -> None:
        if self.store is not None:
            self.store.close()
        Gtk.Application.do_shutdown(self)


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="clipstack: %(message)s")
    if Gdk.Display.get_default() is None:
        print("clipstack: no graphical display found", file=sys.stderr)
        return 1
    app = PopupApp()
    return app.run([sys.argv[0]])
