"""入口：默认启动图形界面，``--scan`` 走无界面模式输出 JSON。"""

from __future__ import annotations

import argparse
import json
import sys

from rightmenu import __version__, i18n
from rightmenu.i18n import t
from rightmenu.model import ContextMenuItem, Scope
from rightmenu.registry import Win32Registry
from rightmenu.scanner import scan


def to_dict(item: ContextMenuItem) -> dict:
    return {
        "id": item.id,
        "scope": item.scope.value,
        "kind": item.kind.value,
        "location": item.location,
        "key_path": item.key_path,
        "key_name": item.key_name,
        "display_name": item.display_name,
        "command": item.command,
        "clsid": item.clsid,
        "dll_path": item.dll_path,
        "extended": item.extended,
        "disabled": item.disabled,
        "method": item.method.value if item.method is not None else None,
        "needs_admin": item.needs_admin,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rightmenu",
        description=t("cli.description"),
    )
    parser.add_argument("--version", action="version", version=f"rightmenu {__version__}")
    parser.add_argument("--scan", action="store_true", help=t("cli.scan_help"))
    parser.add_argument(
        "--scope",
        choices=[Scope.USER.value, Scope.MACHINE.value],
        default=Scope.USER.value,
        help=t("cli.scope_help"),
    )
    parser.add_argument(
        "--lang",
        choices=i18n.available_languages(),
        default=None,
        help=t("cli.lang_help"),
    )
    return parser


def _prescan_language(argv: list[str]) -> str | None:
    """先于 argparse 取 --lang：帮助文本本身也要按所选语言生成。"""
    for index, arg in enumerate(argv):
        if arg == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    i18n.configure(language=_prescan_language(argv))
    args = build_parser().parse_args(argv)

    if args.scan:
        items = scan(Win32Registry(), Scope(args.scope))
        json.dump([to_dict(item) for item in items], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    from rightmenu.ui.app import App

    App().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())