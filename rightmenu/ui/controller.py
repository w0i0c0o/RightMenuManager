"""展示逻辑，不依赖 tkinter —— 便于无界面测试。

视图（ui/app.py）只负责把这里的返回值画出来。
"""

from __future__ import annotations

from rightmenu import actions
from rightmenu.actions import ApplyResult, PlanResult
from rightmenu.aliases import AliasStore
from rightmenu.elevation import is_admin
from rightmenu.grouping import MenuGroup, group_items
from rightmenu.journal import Journal
from rightmenu.model import ContextMenuItem, Scope
from rightmenu.registry import RegistryBackend
from rightmenu.scanner import scan


class Controller:
    def __init__(
        self,
        backend: RegistryBackend,
        journal: Journal | None = None,
        scope: Scope = Scope.USER,
        admin: bool | None = None,
        aliases: AliasStore | None = None,
    ) -> None:
        self.backend = backend
        self.journal = journal
        self.aliases = aliases if aliases is not None else AliasStore()
        self._scope = scope
        self._admin = is_admin() if admin is None else admin
        self._items: list[ContextMenuItem] = []
        self.refresh()

    # ---- 状态 ----

    @property
    def scope(self) -> Scope:
        return self._scope

    @property
    def admin(self) -> bool:
        return self._admin

    @property
    def items(self) -> list[ContextMenuItem]:
        return list(self._items)

    def refresh(self) -> list[ContextMenuItem]:
        self._items = scan(self.backend, self._scope)
        return self.items

    def set_scope(self, scope: Scope) -> None:
        self._scope = scope
        self.refresh()

    def can_write(self) -> bool:
        """当前范围是否允许写入：机器范围需要管理员权限。"""
        return self._scope is Scope.USER or self._admin

    def disabled_count(self) -> int:
        return sum(1 for item in self._items if item.disabled)

    def filter(self, query: str) -> list[ContextMenuItem]:
        needle = (query or "").strip().lower()
        if not needle:
            return self.items
        return [item for item in self._items if needle in _haystack(item)]

    def visible_items(self, query: str = "", hide_system: bool = False) -> list[ContextMenuItem]:
        """当前展示口径下的条目：可选的「只看非 Windows 自带」+ 关键词。"""
        items = self._base_items(hide_system)
        needle = (query or "").strip().lower()
        if not needle:
            return items
        return [item for item in items if needle in _haystack(item)]

    def hidden_system_count(self) -> int:
        return sum(1 for item in self._items if item.is_system)

    def _base_items(self, hide_system: bool) -> list[ContextMenuItem]:
        if not hide_system:
            return self.items
        return [item for item in self._items if not item.is_system]

    # ---- 分组（按功能归并，供粗粒度一键开关） ----

    def groups(self, hide_system: bool = False) -> list[MenuGroup]:
        return group_items(self._base_items(hide_system), self.aliases.as_dict())

    def filter_groups(self, query: str, hide_system: bool = False) -> list[MenuGroup]:
        """按关键词筛选功能组。

        命中组名（含别名）时保留该功能全部实例；仅命中某个实例的属性时，
        只保留命中的实例 —— 便于回答「要关掉这个功能，涉及哪几条」。
        ``hide_system`` 为真时先剔除 Windows 自带的条目再归并。
        """
        needle = (query or "").strip().lower()
        groups = self.groups(hide_system)
        if not needle:
            return groups
        matched: list[MenuGroup] = []
        for group in groups:
            if needle in group.label.lower():
                matched.append(group)
                continue
            members = [item for item in group.items if needle in _haystack(item)]
            if members:
                matched.append(
                    MenuGroup(
                        key=group.key,
                        label=group.label,
                        raw_name=group.raw_name,
                        items=tuple(members),
                    )
                )
        return matched

    def set_alias(self, key: str, label: str) -> None:
        """为功能组设置别名（按归并键持久化）；``label`` 为空则清除。"""
        self.aliases.set(key, label)

    def clear_alias(self, key: str) -> None:
        self.aliases.set(key, "")

    # ---- 变更 ----

    def plan_disable(self, items: list[ContextMenuItem]) -> PlanResult:
        return actions.plan(items, target_disabled=True)

    def plan_enable(self, items: list[ContextMenuItem]) -> PlanResult:
        return actions.plan(items, target_disabled=False)

    def commit(self, changes) -> ApplyResult:
        """执行变更。权限不足时抛 PermissionError，且不会有任何写入。"""
        result = actions.apply(self.backend, list(changes), self.journal)
        self.refresh()
        return result

    def disable(self, items: list[ContextMenuItem]) -> ApplyResult:
        return self.commit(self.plan_disable(items).changes)

    def enable(self, items: list[ContextMenuItem]) -> ApplyResult:
        return self.commit(self.plan_enable(items).changes)

    def restore_all(self) -> ApplyResult:
        if self.journal is None:
            return ApplyResult()
        result = self.journal.restore_all(self.backend)
        self.refresh()
        return result


def _haystack(item: ContextMenuItem) -> str:
    parts = [
        item.display_name,
        item.location,
        item.key_name,
        item.key_path,
        item.command or "",
        item.dll_path or "",
        item.clsid or "",
    ]
    return "\n".join(parts).lower()


def build_preview_text(result: PlanResult) -> str:
    """把 dry-run 结果渲染成用户可读的预览文本。"""
    lines = ["即将修改以下注册表值（只增删值，不删键）：", ""]
    if not result.changes:
        lines.append("（没有需要变更的项）")
    for change in result.changes:
        verb = "写入" if change.action is actions.Action.WRITE else "删除"
        lines.append(f"· {change.description}")
        lines.append(f"    操作: {verb}    值名: {change.value_name or '(默认)'}")
        lines.append(f"    路径: {change.key_path}")
    if result.skipped:
        lines.append("")
        lines.append("以下项已跳过（不会修改注册表）：")
        for item, reason in result.skipped:
            lines.append(f"· {item.display_name}：{reason}")
    return "\n".join(lines)