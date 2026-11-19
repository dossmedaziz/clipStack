"""Unit tests for clipstack.storage."""

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from clipstack.storage import Storage, is_link, make_preview, png_size


def tiny_png(w: int = 2, h: int = 3, seed: int = 0) -> bytes:
    """Build a minimal valid PNG of size w x h."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\0" + bytes([seed % 256]) * (w * 3) for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.images = base / "images"
        self.store = Storage(base / "history.db", self.images)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def texts(self) -> list[str]:
        return [i.content for i in self.store.list()]

    def test_add_and_list_newest_first(self) -> None:
        for t in ("one", "two", "three"):
            self.store.add_text(t)
        self.assertEqual(self.texts(), ["three", "two", "one"])

    def test_blank_text_ignored(self) -> None:
        self.assertIsNone(self.store.add_text(""))
        self.assertIsNone(self.store.add_text("  \n\t "))
        self.assertEqual(self.store.count(), 0)

    def test_duplicate_moves_to_top(self) -> None:
        a = self.store.add_text("a")
        self.store.add_text("b")
        again = self.store.add_text("a")
        self.assertEqual(a, again)
        self.assertEqual(self.texts(), ["a", "b"])
        self.assertEqual(self.store.count(), 2)

    def test_trim_keeps_max_items(self) -> None:
        for i in range(30):
            self.store.add_text(f"item {i}", max_items=25)
        items = self.store.list()
        self.assertEqual(len(items), 25)
        self.assertEqual(items[0].content, "item 29")
        self.assertEqual(items[-1].content, "item 5")

    def test_pinned_not_counted_and_kept(self) -> None:
        pinned = self.store.add_text("keep me")
        self.store.set_pinned(pinned, True)
        for i in range(5):
            self.store.add_text(f"x{i}", max_items=3)
        items = self.store.list()
        self.assertEqual(items[0].content, "keep me")
        self.assertTrue(items[0].pinned)
        self.assertEqual(len(items), 4)  # 1 pinned + 3 unpinned

    def test_pinned_always_on_top(self) -> None:
        old = self.store.add_text("old")
        self.store.add_text("new")
        self.store.set_pinned(old, True)
        self.assertEqual(self.texts(), ["old", "new"])

    def test_toggle_pin(self) -> None:
        i = self.store.add_text("t")
        self.assertTrue(self.store.toggle_pin(i))
        self.assertTrue(self.store.get(i).pinned)
        self.assertFalse(self.store.toggle_pin(i))
        self.assertFalse(self.store.get(i).pinned)

    def test_delete(self) -> None:
        i = self.store.add_text("bye")
        self.assertTrue(self.store.delete(i))
        self.assertFalse(self.store.delete(i))
        self.assertIsNone(self.store.get(i))

    def test_clear_keeps_pinned(self) -> None:
        p = self.store.add_text("pinned")
        self.store.set_pinned(p, True)
        self.store.add_text("a")
        self.store.add_text("b")
        self.assertEqual(self.store.clear(), 2)
        self.assertEqual(self.texts(), ["pinned"])

    def test_search_case_insensitive(self) -> None:
        self.store.add_text("Hello World")
        self.store.add_text("something else")
        self.store.add_text("ÉCOLE française")
        self.assertEqual([i.content for i in self.store.search("hello")], ["Hello World"])
        self.assertEqual([i.content for i in self.store.search("WORLD")], ["Hello World"])
        self.assertEqual([i.content for i in self.store.search("école")], ["ÉCOLE française"])
        self.assertEqual(len(self.store.search("")), 3)
        self.assertEqual(self.store.search("zzz"), [])

    def test_search_wildcards_are_literal(self) -> None:
        self.store.add_text("100% sure")
        self.store.add_text("plain")
        self.assertEqual([i.content for i in self.store.search("%")], ["100% sure"])
        self.assertEqual(self.store.search("_"), [])

    def test_touch_moves_to_top(self) -> None:
        a = self.store.add_text("a")
        self.store.add_text("b")
        self.store.touch(a)
        self.assertEqual(self.texts(), ["a", "b"])

    def test_links_detected(self) -> None:
        i = self.store.add_text("https://example.com/page?q=1")
        self.assertEqual(self.store.get(i).kind, "link")
        j = self.store.add_text("see https://example.com")
        self.assertEqual(self.store.get(j).kind, "text")

    def test_preview(self) -> None:
        i = self.store.add_text("\n\n   first   line  \nsecond")
        self.assertEqual(self.store.get(i).preview, "first line")
        long = "x" * 200
        self.assertEqual(len(make_preview(long)), 80)
        self.assertTrue(make_preview(long).endswith("…"))

    def test_add_image_saves_file_and_dedupes(self) -> None:
        png = tiny_png(4, 5)
        i = self.store.add_image(png, "image/png")
        item = self.store.get(i)
        self.assertEqual(item.kind, "image")
        self.assertEqual(item.preview, "Image 4×5")
        path = Path(item.content)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent, self.images)
        self.assertEqual(path.read_bytes(), png)
        self.store.add_text("text after")
        self.assertEqual(self.store.add_image(png, "image/png"), i)
        self.assertEqual(self.store.list()[0].id, i)
        self.assertEqual(len(list(self.images.iterdir())), 1)

    def test_image_files_removed_on_delete_clear_trim(self) -> None:
        a = self.store.add_image(tiny_png(seed=1))
        path_a = Path(self.store.get(a).content)
        self.store.delete(a)
        self.assertFalse(path_a.exists())

        b = self.store.add_image(tiny_png(seed=2))
        path_b = Path(self.store.get(b).content)
        self.store.clear()
        self.assertFalse(path_b.exists())

        c = self.store.add_image(tiny_png(seed=3))
        path_c = Path(self.store.get(c).content)
        self.store.add_text("newer", max_items=1)
        self.assertFalse(path_c.exists())

    def test_pinned_image_survives_clear(self) -> None:
        a = self.store.add_image(tiny_png(seed=9))
        self.store.set_pinned(a, True)
        self.store.clear()
        self.assertTrue(Path(self.store.get(a).content).exists())

    def test_search_matches_images_by_label(self) -> None:
        self.store.add_image(tiny_png())
        self.store.add_text("text")
        self.assertEqual([i.kind for i in self.store.search("image")], ["image"])

    def test_persistence_across_connections(self) -> None:
        p = self.store.add_text("persist")
        self.store.set_pinned(p, True)
        self.store.close()
        self.store = Storage(Path(self.tmp.name) / "history.db", self.images)
        self.assertTrue(self.store.get(p).pinned)

    def test_helpers(self) -> None:
        self.assertTrue(is_link("www.example.com"))
        self.assertFalse(is_link("hello"))
        self.assertEqual(png_size(tiny_png(7, 9)), (7, 9))
        self.assertIsNone(png_size(b"GIF89a"))


if __name__ == "__main__":
    unittest.main()
