"""变更动作：把「禁用/启用」意图翻译成注册表值操作。

只增删注册表「值」，绝不删「键」；应用前先统一做权限预检，避免半途留下部分改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from rightmenu.model import LEGACY_DISABLE_VALUE, ContextMenuItem, Kind, Scope
from rightmenu.registry import REG_SZ, RegistryBackend
from rightmenu.scanner import blocked_key_path


class Action(str, Enum):
    WRITE = "write"
    DELETE = "delete"


class UnsupportedItem(Exception):
    """该项无法用非破坏机制安全处理。"""


@dataclass(frozen=True)
class Change:
    """一次待执行的注册表值操作。"""

    action: Action
    key_path: str
    value_name: str | None
    value: object | None
    vtype: int | None
    item_id: str
    scope: Scope
    description: str


@dataclass
class PlanResult:
    changes: list[Change] = field(default_factory=list)
    skipped: list[tuple[ContextMenuItem, str]] = field(default_factory=list)


@dataclass
class ApplyResult:
    applied: list[Change] = field(default_factory=list)
    failed: list[tuple[Change, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def plan(items: list[ContextMenuItem], target_disabled: bool) -> PlanResult:
    """生成 dry-run 变更清单，无任何副作用。

    已在目标状态的项被跳过，因此 apply 天然幂等。
    """
    result = PlanResult()
    for item in items:
        if item.disabled == target_disabled:
            continue
        try:
            result.changes.extend(_changes_for(item, target_disabled))
        except UnsupportedItem as exc:
            result.skipped.append((item, str(exc)))
    return result


def _changes_for(item: ContextMenuItem, disable: bool) -> list[Change]:
    if item.kind is Kind.SHELLEX:
        if not item.clsid:
            raise UnsupportedItem("无法解析 CLSID，不能用屏蔽清单安全地处理该项")
        blocked_path = blocked_key_path(item.scope)
        if disable:
            return [
                Change(
                    Action.WRITE,
                    blocked_path,
                    item.clsid,
                    "",
                    REG_SZ,
                    item.id,
                    item.scope,
                    f"屏蔽「{item.display_name}」",
                )
            ]
        return [
            Change(
                Action.DELETE,
                blocked_path,
                item.clsid,
                None,
                None,
                item.id,
                item.scope,
                f"解除屏蔽「{item.display_name}」",
            )
        ]

    if disable:
        return [
            Change(
                Action.WRITE,
                item.key_path,
                LEGACY_DISABLE_VALUE,
                "",
                REG_SZ,
                item.id,
                item.scope,
                f"禁用「{item.display_name}」",
            )
        ]
    return [
        Change(
            Action.DELETE,
            item.key_path,
            LEGACY_DISABLE_VALUE,
            None,
            None,
            item.id,
            item.scope,
            f"恢复「{item.display_name}」",
        )
    ]


def apply(backend: RegistryBackend, changes: list[Change], journal=None) -> ApplyResult:
    """执行变更。

    先对所有目标键做写权限预检：任何一处不可写就整体中止，不留部分改动。
    预检通过后逐条执行，个别失败单独记录，不影响其余项。
    """
    for key_path in {change.key_path for change in changes}:
        backend.ensure_writable(key_path)

    result = ApplyResult()
    for change in changes:
        previous = backend.read_value(change.key_path, change.value_name) if journal is not None else None
        try:
            if change.action is Action.WRITE:
                backend.write_value(change.key_path, change.value_name, change.value, change.vtype)
            else:
                backend.delete_value(change.key_path, change.value_name)
        except FileNotFoundError:
            # 目标值本就不存在 —— 结果与目标一致，视为成功
            result.applied.append(change)
            continue
        except OSError as exc:
            result.failed.append((change, str(exc)))
            continue

        result.applied.append(change)
        if journal is not None and _changed(change, previous):
            journal.record(change, previous)
    return result


def _changed(change: Change, previous: tuple[object, int] | None) -> bool:
    if change.action is Action.DELETE:
        return previous is not None
    return previous != (change.value, change.vtype)


def disable(backend: RegistryBackend, items: list[ContextMenuItem], journal=None) -> ApplyResult:
    return apply(backend, plan(items, target_disabled=True).changes, journal)


def enable(backend: RegistryBackend, items: list[ContextMenuItem], journal=None) -> ApplyResult:
    return apply(backend, plan(items, target_disabled=False).changes, journal)