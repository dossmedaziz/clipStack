"""Unit tests for clipstack.config."""

import json
import tempfile
import unittest
from pathlib import Path

from clipstack import config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_gives_defaults(self) -> None:
        cfg = config.load(self.path)
        self.assertEqual(cfg, config.DEFAULTS)
        self.assertEqual(cfg["max_items"], 25)
        self.assertTrue(cfg["auto_paste"])

    def test_defaults_are_not_shared(self) -> None:
        cfg = config.load(self.path)
        cfg["ignore_apps"].append("x")
        self.assertEqual(config.DEFAULTS["ignore_apps"], [])

    def test_save_and_load_roundtrip(self) -> None:
        cfg = config.load(self.path)
        cfg["max_items"] = 50
        cfg["auto_paste"] = False
        config.save(cfg, self.path)
        self.assertTrue(self.path.exists())
        again = config.load(self.path)
        self.assertEqual(again["max_items"], 50)
        self.assertFalse(again["auto_paste"])

    def test_partial_file_merges_defaults(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"max_items": 10}))
        cfg = config.load(self.path)
        self.assertEqual(cfg["max_items"], 10)
        self.assertEqual(cfg["max_item_bytes"], 5 * 1024 * 1024)

    def test_invalid_types_fall_back(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"max_items": "lots", "auto_paste": 1,
                                         "ignore_apps": "keepassxc",
                                         "paste_delay_ms": -5}))
        with _quiet():
            cfg = config.load(self.path)
        self.assertEqual(cfg["max_items"], 25)
        self.assertTrue(cfg["auto_paste"])
        self.assertEqual(cfg["ignore_apps"], [])
        self.assertEqual(cfg["paste_delay_ms"], 200)

    def test_max_items_at_least_one(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"max_items": 0}))
        self.assertEqual(config.load(self.path)["max_items"], 1)

    def test_corrupt_json_gives_defaults(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        with _quiet():
            cfg = config.load(self.path)
        self.assertEqual(cfg, config.DEFAULTS)
        # The broken file is left for the user to inspect.
        self.assertEqual(self.path.read_text(), "{not json")

    def test_non_object_json_gives_defaults(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[1, 2]")
        with _quiet():
            self.assertEqual(config.load(self.path), config.DEFAULTS)

    def test_unknown_keys_are_kept(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"future_option": "yes"}))
        cfg = config.load(self.path)
        self.assertEqual(cfg["future_option"], "yes")
        config.save(cfg, self.path)
        self.assertIn("future_option", json.loads(self.path.read_text()))

    def test_update(self) -> None:
        config.update(self.path, shortcut_configured=True)
        self.assertTrue(config.load(self.path)["shortcut_configured"])

    def test_xdg_paths(self) -> None:
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/c", "XDG_DATA_HOME": "/d"}):
            self.assertEqual(config.config_path(), Path("/c/clipstack/config.json"))
            self.assertEqual(config.data_dir(), Path("/d/clipstack"))


class _quiet:
    """Silence warnings printed to stderr during a test."""

    def __enter__(self):
        import contextlib, io
        self._cm = contextlib.redirect_stderr(io.StringIO())
        return self._cm.__enter__()

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)


if __name__ == "__main__":
    unittest.main()
