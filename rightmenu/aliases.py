"""功能别名：给注册表里没有可读文字的菜单项起一个人能认出的名字。

有些菜单项（如百度网盘的「上传到百度网盘」）文字由 DLL 在运行时生成，
注册表里只有 ``baidunetdisk``，无法自动还原。用户可为其设置别名，
别名按归并键持久化到本地，之后即可按该名字搜索、归并与一键开关。

``path=None`` 时仅在内存中保存，不落盘（供测试使用）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def default_alias_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "RightMenuManager" / "aliases.json"


class AliasStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._data: dict[str, str] = self._load() if self.path is not None else {}

    def _load(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items() if str(v).strip()}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def as_dict(self) -> dict[str, str]:
        return dict(self._data)

    def set(self, key: str, label: str) -> None:
        """设置别名；``label`` 为空白则删除该别名。"""
        label = label.strip()
        if label:
            self._data[key] = label
        else:
            self._data.pop(key, None)
        self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )