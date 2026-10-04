"""按「功能」归并菜单项。

同一个右键功能（如「上传到百度网盘」）往往在多个文件类型与位置各注册一份。
用户关心的是「把这个功能关掉」，而不是逐个文件类型去点。本模块把显示文字
相同的项归并成 :class:`MenuGroup`，供粗粒度的一键禁用/恢复使用；
细粒度的逐项视图仍然保留。
"""

from __future__ import annotations

from dataclasses import dataclass

from rightmenu.model import ContextMenuItem, Kind, Scope


def group_key(item: ContextMenuItem) -> str:
    """归并键：菜单显示文字，忽略首尾空白与大小写。"""
    return item.display_name.strip().casefold()


@dataclass(frozen=True)
class MenuGroup:
    """一组显示文字相同的菜单项（同一功能的所有实例）。"""

    key: str
    label: str
    raw_name: str
    items: tuple[ContextMenuItem, ...]

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def disabled_count(self) -> int:
        return sum(1 for item in self.items if item.disabled)

    @property
    def state(self) -> str:
        """``enabled`` / ``disabled`` / ``partial``。"""
        disabled = self.disabled_count
        if disabled == 0:
            return "enabled"
        if disabled == self.total:
            return "disabled"
        return "partial"

    @property
    def has_alias(self) -> bool:
        return self.label != self.raw_name

    @property
    def needs_alias(self) -> bool:
        """组内所有项的名字都只是回退到键名 —— 用户多半认不出，建议设别名。"""
        if self.has_alias:
            return False
        return all(item.name_is_fallback for item in self.items)

    @property
    def locations(self) -> tuple[str, ...]:
        return tuple(sorted({item.location for item in self.items}))

    @property
    def scopes(self) -> tuple[Scope, ...]:
        seen: list[Scope] = []
        for item in self.items:
            if item.scope not in seen:
                seen.append(item.scope)
        return tuple(seen)

    @property
    def kinds(self) -> tuple[Kind, ...]:
        seen: list[Kind] = []
        for item in self.items:
            if item.kind not in seen:
                seen.append(item.kind)
        return tuple(seen)

    @property
    def dll_paths(self) -> tuple[str, ...]:
        return tuple(sorted({item.dll_path for item in self.items if item.dll_path}))

    @property
    def commands(self) -> tuple[str, ...]:
        return tuple(sorted({item.command for item in self.items if item.command}))

    @property
    def sample_detail(self) -> str:
        """列表「命令 / DLL」列的概要：优先 DLL，其次命令。"""
        if self.dll_paths:
            return self.dll_paths[0]
        if self.commands:
            return self.commands[0]
        return ""

    @property
    def needs_admin(self) -> bool:
        return any(item.needs_admin for item in self.items)


def group_items(
    items: list[ContextMenuItem],
    aliases: dict[str, str] | None = None,
) -> list[MenuGroup]:
    """把菜单项按显示文字归并；``aliases`` 用别名覆盖展示名（不改归并键）。

    排序：实例数多的功能在前（影响面大的先处理），同数量按名称排序。
    """
    buckets: dict[str, list[ContextMenuItem]] = {}
    for item in items:
        buckets.setdefault(group_key(item), []).append(item)

    alias_map = aliases or {}
    groups: list[MenuGroup] = []
    for key, members in buckets.items():
        raw_name = members[0].display_name.strip() or members[0].key_name
        groups.append(
            MenuGroup(
                key=key,
                label=alias_map.get(key, raw_name),
                raw_name=raw_name,
                items=tuple(members),
            )
        )
    groups.sort(key=lambda g: (-g.total, g.label.casefold()))
    return groups