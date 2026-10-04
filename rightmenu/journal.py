"""变更日志：记录本工具做过的每一次改动，并提供一键恢复。

恢复只回放日志里记录过的值 —— 不触碰其他软件或用户自己设置的屏蔽项。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from rightmenu.actions import Action, ApplyResult, Change
from rightmenu.model import Scope
from rightmenu.registry import RegistryBackend


def default_journal_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / "RightMenuManager" / "journal.json"
    return Path.home() / ".rightmenu_manager" / "journal.json"


@dataclass
class JournalEntry:
    ts: str
    action: str
    scope: str
    key_path: str
    value_name: str | None
    item_id: str
    description: str
    had_previous: bool = False
    previous_value: object | None = None
    previous_type: int | None = None


class Journal:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_journal_path()
        self._entries: list[JournalEntry] = self._load()

    # ---- 读写 ----

    def _load(self) -> list[JournalEntry]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [JournalEntry(**item) for item in raw.get("entries", [])]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": [asdict(e) for e in self._entries]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    @property
    def entries(self) -> list[JournalEntry]:
        return list(self._entries)

    def record(self, change: Change, previous: tuple[object, int] | None) -> None:
        self._entries.append(
            JournalEntry(
                ts=datetime.now().isoformat(timespec="seconds"),
                action=change.action.value,
                scope=change.scope.value,
                key_path=change.key_path,
                value_name=change.value_name,
                item_id=change.item_id,
                description=change.description,
                had_previous=previous is not None,
                previous_value=previous[0] if previous is not None else None,
                previous_type=previous[1] if previous is not None else None,
            )
        )
        self._save()

    def clear(self) -> None:
        self._entries.clear()
        self._save()

    def export(self, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.path, destination)
        return destination

    # ---- 恢复 ----

    def restore_all(self, backend: RegistryBackend) -> ApplyResult:
        """按日志逆序回放，把注册表还原到本工具改动之前的状态。

        任何目标不可写则整体中止，日志保留以便重试。
        """
        if not self._entries:
            return ApplyResult()

        for key_path in {entry.key_path for entry in self._entries}:
            backend.ensure_writable(key_path)

        result = ApplyResult()
        for entry in reversed(self._entries):
            change = self._as_change(entry)
            try:
                if entry.had_previous:
                    backend.write_value(
                        entry.key_path, entry.value_name, entry.previous_value, entry.previous_type
                    )
                else:
                    backend.delete_value(entry.key_path, entry.value_name)
            except FileNotFoundError:
                result.applied.append(change)
                continue
            except OSError as exc:
                result.failed.append((change, str(exc)))
                continue
            result.applied.append(change)

        if result.ok:
            self.clear()
        return result

    @staticmethod
    def _as_change(entry: JournalEntry) -> Change:
        if entry.had_previous:
            return Change(
                Action.WRITE,
                entry.key_path,
                entry.value_name,
                entry.previous_value,
                entry.previous_type,
                entry.item_id,
                Scope(entry.scope),
                f"恢复：{entry.description}",
            )
        return Change(
            Action.DELETE,
            entry.key_path,
            entry.value_name,
            None,
            None,
            entry.item_id,
            Scope(entry.scope),
            f"撤销：{entry.description}",
        )