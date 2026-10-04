"""扫描器：枚举右键菜单项，只读，不产生任何写入。"""

from __future__ import annotations

import os

from rightmenu.locations import SCAN_TARGETS, ScanTarget
from rightmenu.model import (
    LEGACY_DISABLE_VALUE,
    ContextMenuItem,
    DisableMethod,
    Kind,
    Scope,
)
from rightmenu.registry import RegistryBackend

CLASSES_USER = r"HKCU\Software\Classes"
CLASSES_MACHINE = r"HKLM\SOFTWARE\Classes"
CLASSES_MACHINE_WOW64 = r"HKLM\SOFTWARE\Classes\Wow6432Node"

BLOCKED_USER = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked"
BLOCKED_MACHINE = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked"


def classes_roots(scope: Scope) -> list[tuple[str, Scope]]:
    """返回 (Classes 根路径, 该项归属范围)。机器范围会同时包含用户项。"""
    roots = [(CLASSES_USER, Scope.USER)]
    if scope is Scope.MACHINE:
        roots.append((CLASSES_MACHINE, Scope.MACHINE))
        roots.append((CLASSES_MACHINE_WOW64, Scope.MACHINE))
    return roots


def blocked_key_path(scope: Scope) -> str:
    return BLOCKED_USER if scope is Scope.USER else BLOCKED_MACHINE


def scan(
    backend: RegistryBackend,
    scope: Scope = Scope.USER,
    targets: tuple[ScanTarget, ...] = SCAN_TARGETS,
) -> list[ContextMenuItem]:
    items: list[ContextMenuItem] = []
    for root, item_scope in classes_roots(scope):
        for target in targets:
            items.extend(_scan_target(backend, root, item_scope, target))
    items.sort(key=lambda i: (i.scope.value, i.location, i.display_name.lower(), i.key_path.upper()))
    return items


def _scan_target(
    backend: RegistryBackend,
    root: str,
    scope: Scope,
    target: ScanTarget,
) -> list[ContextMenuItem]:
    items: list[ContextMenuItem] = []
    for child in _children_for(backend, root, target):
        subpath = target.subpath.format(child=child)
        shell_key = f"{root}\\{subpath}"
        location = target.location.format(child=child)
        for name in backend.list_subkeys(shell_key):
            item = _build_item(backend, root, scope, target.kind, location, shell_key, name)
            if item is not None:
                items.append(item)
    return items


def _children_for(backend: RegistryBackend, root: str, target: ScanTarget) -> list[str | None]:
    if target.enumerate_parent is None:
        return [None]
    parent = f"{root}\\{target.enumerate_parent}" if target.enumerate_parent else root
    return [c for c in backend.list_subkeys(parent) if c.startswith(target.child_prefix)]


def _build_item(
    backend: RegistryBackend,
    root: str,
    scope: Scope,
    kind: Kind,
    location: str,
    shell_key: str,
    name: str,
) -> ContextMenuItem | None:
    item_key = f"{shell_key}\\{name}"
    if kind is Kind.STATIC:
        return _build_static(backend, scope, location, item_key, name)
    return _build_shellex(backend, root, scope, location, item_key, name)


def _build_static(
    backend: RegistryBackend,
    scope: Scope,
    location: str,
    item_key: str,
    name: str,
) -> ContextMenuItem | None:
    default = _text(backend.read_value(item_key, None))
    muiverb = _text(backend.read_value(item_key, "MUIVerb"))
    subcommands = _text(backend.read_value(item_key, "SubCommands"))
    command = _text(backend.read_value(f"{item_key}\\command", None))
    if not (default or muiverb or subcommands or command):
        return None

    disabled = backend.read_value(item_key, LEGACY_DISABLE_VALUE) is not None
    return ContextMenuItem(
        scope=scope,
        kind=Kind.STATIC,
        location=location,
        key_path=item_key,
        display_name=default or muiverb or name,
        key_name=name,
        command=command or None,
        extended=backend.read_value(item_key, "Extended") is not None,
        disabled=disabled,
        method=DisableMethod.LEGACY_DISABLE if disabled else None,
    )


def _build_shellex(
    backend: RegistryBackend,
    root: str,
    scope: Scope,
    location: str,
    item_key: str,
    name: str,
) -> ContextMenuItem | None:
    raw = _text(backend.read_value(item_key, None))
    clsid = raw if raw.startswith("{") else None

    display_name = name
    dll_path = None
    if clsid:
        friendly = _text(backend.read_value(f"{root}\\CLSID\\{clsid}", None))
        if friendly and not friendly.startswith("@"):
            display_name = friendly
        dll_raw = _text(backend.read_value(f"{root}\\CLSID\\{clsid}\\InprocServer32", None))
        if dll_raw:
            dll_path = os.path.expandvars(dll_raw)

    blocked = clsid is not None and backend.read_value(blocked_key_path(scope), clsid) is not None
    return ContextMenuItem(
        scope=scope,
        kind=Kind.SHELLEX,
        location=location,
        key_path=item_key,
        display_name=display_name,
        key_name=name,
        clsid=clsid,
        dll_path=dll_path,
        disabled=blocked,
        method=DisableMethod.BLOCKED if blocked else None,
    )


def _text(pair: tuple[object, int] | None) -> str:
    if pair is None:
        return ""
    value = pair[0]
    return value if isinstance(value, str) else str(value)