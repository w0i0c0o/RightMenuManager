"""入口：默认启动图形界面，``--scan`` 走无界面模式输出 JSON。"""

from __future__ import annotations

import argparse
import json
import sys

from rightmenu import __version__
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
        description="以非破坏、可逆的方式管理 Windows 右键菜单项。",
    )
    parser.add_argument("--version", action="version", version=f"rightmenu {__version__}")
    parser.add_argument("--scan", action="store_true", help="无界面模式：扫描并输出 JSON")
    parser.add_argument(
        "--scope",
        choices=[Scope.USER.value, Scope.MACHINE.value],
        default=Scope.USER.value,
        help="扫描范围（默认 user）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
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