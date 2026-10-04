"""菜单项数据模型。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class Scope(str, Enum):
    """菜单项所属的注册表范围。"""

    USER = "user"
    MACHINE = "machine"


class Kind(str, Enum):
    """菜单项类型，决定禁用机制。"""

    STATIC = "static"
    SHELLEX = "shellex"


class DisableMethod(str, Enum):
    """当前生效的禁用方式。"""

    BLOCKED = "blocked"
    LEGACY_DISABLE = "legacy_disable"


#: 静态动词键下用于隐藏该项的值名（存在即隐藏，删除即恢复）。
LEGACY_DISABLE_VALUE = "LegacyDisable"


@dataclass(frozen=True)
class ContextMenuItem:
    """一条右键菜单项。

    只描述"现状"，不承载任何写入意图。
    """

    scope: Scope
    kind: Kind
    location: str
    key_path: str
    display_name: str
    key_name: str
    command: str | None = None
    clsid: str | None = None
    dll_path: str | None = None
    extended: bool = False
    disabled: bool = False
    method: DisableMethod | None = None

    @property
    def id(self) -> str:
        """跨会话稳定的标识，仅由范围与注册表路径决定。"""
        raw = f"{self.scope.value}|{self.key_path.upper()}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @property
    def needs_admin(self) -> bool:
        return self.scope is Scope.MACHINE