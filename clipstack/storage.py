"""Clipboard history storage (SQLite).

Database: ``~/.local/share/clipstack/history.db``
Images:   ``~/.local/share/clipstack/images/<sha256>.<ext>`` (path kept in the DB)

Ordering: pinned items first, then most recently copied/used first. A
monotonic ``seq`` counter (not wall-clock time) decides "recent", so copying
the same thing again reliably moves it to the top.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from . import config

PREVIEW_CHARS = 80
_LINK_RE = re.compile(r"(?:https?|ftp|file)://\S+|www\.[^\s.]+\.\S+|mailto:\S+",
                      re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL CHECK (kind IN ('text', 'link', 'image')),
    content    TEXT    NOT NULL,          -- the text, or the image file path
    hash       TEXT    NOT NULL UNIQUE,   -- sha256 of kind + bytes (dedupe)
    preview    TEXT    NOT NULL,
    mime       TEXT,                      -- image MIME type (images only)
    size       INTEGER NOT NULL,          -- size in bytes
    pinned     INTEGER NOT NULL DEFAULT 0,
    created_at REAL    NOT NULL,
    seq        INTEGER NOT NULL           -- higher = more recent
);
CREATE INDEX IF NOT EXISTS items_order ON items (pinned DESC, seq DESC);
"""


class StorageError(Exception):
    """A clear, user-facing storage error (locked DB, disk full, ...)."""


@dataclass(frozen=True)
class Item:
    id: int
    kind: str           # 'text', 'link' or 'image'
    content: str        # text, or absolute path of the image file
    preview: str
    mime: str | None
    size: int
    pinned: bool
    created_at: float

    @property
    def is_image(self) -> bool:
        return self.kind == "image"


def make_preview(text: str, limit: int = PREVIEW_CHARS) -> str:
    """First non-empty line, whitespace-collapsed, at most ``limit`` chars."""
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            break
    else:
        line = " ".join(text.split())
    if len(line) > limit:
        line = line[: limit - 1].rstrip() + "…"
    return line


def is_link(text: str) -> bool:
    """True if the whole (stripped) text is a single URL."""
    return bool(_LINK_RE.fullmatch(text.strip()))


def png_size(data: bytes) -> tuple[int, int] | None:
    """Width/height from a PNG header, or None if not a PNG."""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None


_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
        "image/bmp": "bmp", "image/webp": "webp", "image/tiff": "tiff",
        "image/svg+xml": "svg"}


def _casefold_contains(haystack: str | None, needle: str | None) -> int:
    """SQL helper: Unicode-aware, case-insensitive substring test."""
    if not needle:
        return 1
    return int(needle.casefold() in (haystack or "").casefold())


class Storage:
    """Thin wrapper around the SQLite history database."""

    def __init__(self, db_path: Path | None = None, images_dir: Path | None = None,
                 timeout: float = 5.0) -> None:
        base = config.data_dir()
        self.db_path = Path(db_path) if db_path else base / "history.db"
        self.images_dir = Path(images_dir) if images_dir else base / "images"
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.images_dir.mkdir(parents=True, exist_ok=True)
            # timeout: wait up to N seconds if another process holds a lock.
            self.conn = sqlite3.connect(str(self.db_path), timeout=timeout)
            self.conn.row_factory = sqlite3.Row
            self.conn.create_function("cf_contains", 2, _casefold_contains,
                                      deterministic=True)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"cannot open history database {self.db_path}: {exc}") from exc

    # ------------------------------------------------------------ helpers --
    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _tx(self) -> "_Transaction":
        return _Transaction(self.conn)

    def _next_seq(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM items").fetchone()
        return int(row[0])

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> Item:
        return Item(id=row["id"], kind=row["kind"], content=row["content"],
                    preview=row["preview"], mime=row["mime"], size=row["size"],
                    pinned=bool(row["pinned"]), created_at=row["created_at"])

    def _bump_or_insert(self, kind: str, content: str, digest: str, preview: str,
                        mime: str | None, size: int) -> int:
        """Move an existing identical item to the top, or insert a new one."""
        seq = self._next_seq()
        row = self.conn.execute("SELECT id FROM items WHERE hash = ?", (digest,)).fetchone()
        if row:
            self.conn.execute("UPDATE items SET seq = ? WHERE id = ?", (seq, row["id"]))
            return int(row["id"])
        cur = self.conn.execute(
            "INSERT INTO items (kind, content, hash, preview, mime, size, pinned,"
            " created_at, seq) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (kind, content, digest, preview, mime, size, time.time(), seq))
        return int(cur.lastrowid)

    # ---------------------------------------------------------------- add --
    def add_text(self, text: str, max_items: int | None = None) -> int | None:
        """Store text; returns the item id, or None if the text is blank."""
        if not text or not text.strip():
            return None
        kind = "link" if is_link(text) else "text"
        raw = text.encode("utf-8", "surrogatepass")
        digest = hashlib.sha256(b"text\0" + raw).hexdigest()
        with self._tx():
            item_id = self._bump_or_insert(kind, text, digest, make_preview(text),
                                           None, len(raw))
            if max_items is not None:
                self._trim(max_items)
        return item_id

    def add_image(self, data: bytes, mime: str = "image/png",
                  max_items: int | None = None) -> int | None:
        """Store image bytes as a file; returns the item id (None if empty)."""
        if not data:
            return None
        digest = hashlib.sha256(b"image\0" + data).hexdigest()
        path = self.images_dir / f"{digest}.{_EXT.get(mime, 'img')}"
        dims = png_size(data)
        preview = f"Image {dims[0]}×{dims[1]}" if dims else "Image"
        try:
            if not path.exists():
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, path)
        except OSError as exc:
            raise StorageError(f"cannot save image to {path}: {exc}") from exc
        with self._tx():
            item_id = self._bump_or_insert("image", str(path), digest, preview,
                                           mime, len(data))
            if max_items is not None:
                self._trim(max_items)
        return item_id

    # --------------------------------------------------------------- read --
    def get(self, item_id: int) -> Item | None:
        row = self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return self._row_to_item(row) if row else None

    def list(self, limit: int | None = None) -> list[Item]:
        """All items: pinned first, then newest first."""
        return self.search("", limit)

    def search(self, query: str, limit: int | None = None) -> list[Item]:
        """Items whose text contains ``query`` (case-insensitive).

        Images match on their preview label (e.g. "image").
        """
        sql = ("SELECT * FROM items WHERE cf_contains("
               "CASE WHEN kind = 'image' THEN preview ELSE content END, ?)"
               " ORDER BY pinned DESC, seq DESC")
        params: list[object] = [query.strip()]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        try:
            return [self._row_to_item(r) for r in self.conn.execute(sql, params)]
        except sqlite3.Error as exc:
            raise StorageError(f"cannot read history: {exc}") from exc

    def count(self, pinned: bool | None = None) -> int:
        if pinned is None:
            row = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM items WHERE pinned = ?",
                                    (int(pinned),)).fetchone()
        return int(row[0])

    # ------------------------------------------------------------- change --
    def touch(self, item_id: int) -> None:
        """Move an item to the top (used when it is pasted from the popup)."""
        with self._tx():
            self.conn.execute("UPDATE items SET seq = ? WHERE id = ?",
                              (self._next_seq(), item_id))

    def set_pinned(self, item_id: int, pinned: bool) -> None:
        with self._tx():
            self.conn.execute("UPDATE items SET pinned = ? WHERE id = ?",
                              (int(pinned), item_id))

    def toggle_pin(self, item_id: int) -> bool:
        """Flip the pin state; returns the new state."""
        item = self.get(item_id)
        if item is None:
            return False
        self.set_pinned(item_id, not item.pinned)
        return not item.pinned

    def delete(self, item_id: int) -> bool:
        """Delete one item (pinned or not). Returns True if it existed."""
        with self._tx():
            rows = self.conn.execute("SELECT * FROM items WHERE id = ?",
                                     (item_id,)).fetchall()
            self.conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self._remove_files(rows)
        return bool(rows)

    def clear(self) -> int:
        """Delete every unpinned item. Returns how many were deleted."""
        with self._tx():
            rows = self.conn.execute("SELECT * FROM items WHERE pinned = 0").fetchall()
            self.conn.execute("DELETE FROM items WHERE pinned = 0")
        self._remove_files(rows)
        return len(rows)

    def trim(self, max_items: int) -> int:
        """Keep only the newest ``max_items`` unpinned items."""
        with self._tx():
            return self._trim(max_items)

    def _trim(self, max_items: int) -> int:
        rows = self.conn.execute(
            "SELECT * FROM items WHERE pinned = 0 ORDER BY seq DESC LIMIT -1 OFFSET ?",
            (max(0, max_items),)).fetchall()
        if rows:
            self.conn.executemany("DELETE FROM items WHERE id = ?",
                                  [(r["id"],) for r in rows])
            self._remove_files(rows)
        return len(rows)

    def _remove_files(self, rows: list[sqlite3.Row]) -> None:
        """Delete image files that belong to deleted rows (only inside images_dir)."""
        for r in rows:
            if r["kind"] != "image":
                continue
            path = Path(r["content"])
            if path.parent.resolve() != self.images_dir.resolve():
                continue  # never delete files outside our folder
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def iter_image_paths(self) -> Iterator[Path]:
        for r in self.conn.execute("SELECT content FROM items WHERE kind = 'image'"):
            yield Path(r["content"])


class _Transaction:
    """Context manager: commit on success, roll back and wrap errors on failure."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            try:
                self.conn.commit()
            except sqlite3.Error as err:
                self.conn.rollback()
                raise StorageError(_explain(err)) from err
            return False
        self.conn.rollback()
        if isinstance(exc, sqlite3.Error):
            raise StorageError(_explain(exc)) from exc
        return False


def _explain(err: sqlite3.Error) -> str:
    msg = str(err)
    if "locked" in msg or "busy" in msg:
        return ("the history database is locked by another process; "
                "try again in a moment")
    return f"database error: {msg}"
