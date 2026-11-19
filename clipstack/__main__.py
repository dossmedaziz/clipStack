"""Command line: ``clipstack daemon | show | clear | setup-shortcut | remove-shortcut``."""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _cmd_daemon(args: argparse.Namespace) -> int:
    from . import daemon
    return daemon.run(verbose=args.verbose)


def _cmd_show(args: argparse.Namespace) -> int:
    from . import popup
    return popup.run()


def _cmd_clear(args: argparse.Namespace) -> int:
    from .storage import Storage, StorageError
    try:
        with Storage() as store:
            n = store.clear()
    except StorageError as exc:
        print(f"clipstack: {exc}", file=sys.stderr)
        return 1
    print(f"Cleared {n} item(s). Pinned items were kept.")
    return 0


def _cmd_setup_shortcut(args: argparse.Namespace) -> int:
    from . import config, shortcut
    try:
        ok, message = shortcut.setup()
    except shortcut.ShortcutError as exc:
        print(f"clipstack: {exc}", file=sys.stderr)
        return 1
    print(message)
    config.update(shortcut_configured=True)
    return 0 if ok else 2


def _cmd_remove_shortcut(args: argparse.Namespace) -> int:
    from . import config, shortcut
    try:
        _removed, message = shortcut.remove()
    except shortcut.ShortcutError as exc:
        print(f"clipstack: {exc}", file=sys.stderr)
        return 1
    print(message)
    # Remember the choice so the daemon does not add it back at next login.
    config.update(shortcut_configured=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipstack",
        description="Clipboard history for Ubuntu (like Win + V). "
                    "Press Super + B to open the history.")
    p.add_argument("--version", action="version", version=f"clipstack {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    d = sub.add_parser("daemon", help="watch the clipboard and record history "
                                      "(started automatically at login)")
    d.add_argument("-v", "--verbose", action="store_true", help="print debug messages")
    d.set_defaults(func=_cmd_daemon)

    sub.add_parser("show", help="open the history popup (or close it if open)"
                   ).set_defaults(func=_cmd_show)
    sub.add_parser("clear", help="delete all history except pinned items"
                   ).set_defaults(func=_cmd_clear)
    sub.add_parser("setup-shortcut", help="add the Super + B keyboard shortcut"
                   ).set_defaults(func=_cmd_setup_shortcut)
    sub.add_parser("remove-shortcut", help="remove ClipStack's keyboard shortcut"
                   ).set_defaults(func=_cmd_remove_shortcut)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
