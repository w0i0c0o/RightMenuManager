"""注册表访问抽象。

生产实现基于 winreg；测试用 FakeRegistry 提供内存实现。

注意：后端接口刻意不提供删除键的方法 —— 本工具只增删「值」，永不删「键」。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
import winreg

REG_SZ = winreg.REG_SZ
REG_EXPAND_SZ = winreg.REG_EXPAND_SZ
REG_DWORD = winreg.REG_DWORD

ROOT_HIVES: dict[str, int] = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
    "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
    "HKU": winreg.HKEY_USERS,
    "HKEY_USERS": winreg.HKEY_USERS,
    "HKCC": winreg.HKEY_CURRENT_CONFIG,
    "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
}


def split_root(path: str) -> tuple[int, str]:
    """把 ``HKCU\\Software\\...`` 拆成 (hive 句柄, 子键路径)。"""
    root, _, sub = path.partition("\\")
    hive = ROOT_HIVES.get(root.strip().upper())
    if hive is None:
        raise ValueError(f"不支持的注册表根键: {root}")
    return hive, sub


@runtime_checkable
class RegistryBackend(Protocol):
    """注册表读写接口。

    ``name`` 为 None 或 "" 表示默认值。
    """

    def key_exists(self, path: str) -> bool: ...

    def list_subkeys(self, path: str) -> list[str]: ...

    def read_value(self, path: str, name: str | None) -> tuple[object, int] | None: ...

    def write_value(self, path: str, name: str | None, value: object, vtype: int) -> None: ...

    def delete_value(self, path: str, name: str | None) -> None: ...

    def ensure_writable(self, path: str) -> None: ...


class Win32Registry:
    """基于 winreg 的真实实现。

    读取失败（键不存在、无权限）一律静默跳过，保证扫描不会因个别坏键中断；
    写入失败则显式抛出，由上层决定如何提示。
    """

    def key_exists(self, path: str) -> bool:
        hive, sub = split_root(path)
        try:
            with winreg.OpenKey(hive, sub):
                return True
        except OSError:
            return False

    def list_subkeys(self, path: str) -> list[str]:
        hive, sub = split_root(path)
        names: list[str] = []
        try:
            with winreg.OpenKey(hive, sub) as key:
                index = 0
                while True:
                    try:
                        names.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
        except OSError:
            return []
        return names

    def read_value(self, path: str, name: str | None) -> tuple[object, int] | None:
        hive, sub = split_root(path)
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, vtype = winreg.QueryValueEx(key, name or "")
        except OSError:
            return None
        return value, vtype

    def write_value(self, path: str, name: str | None, value: object, vtype: int) -> None:
        hive, sub = split_root(path)
        with winreg.CreateKeyEx(hive, sub, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name or "", 0, vtype, value)

    def delete_value(self, path: str, name: str | None) -> None:
        hive, sub = split_root(path)
        try:
            with winreg.OpenKey(hive, sub, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name or "")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"值不存在: {path} :: {name or '(默认)'}") from exc

    def ensure_writable(self, path: str) -> None:
        """确认对 path 有写权限；不产生任何改动。

        键已存在则要求 KEY_SET_VALUE，否则向上找到最近的存在祖先并要求 KEY_CREATE_SUB_KEY。
        """
        hive, sub = split_root(path)
        try:
            with winreg.OpenKey(hive, sub, 0, winreg.KEY_SET_VALUE):
                return
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise PermissionError(f"无权限写入 {path}") from exc

        parts = sub.split("\\")
        while parts:
            parts.pop()
            candidate = "\\".join(parts)
            try:
                with winreg.OpenKey(hive, candidate, 0, winreg.KEY_CREATE_SUB_KEY):
                    return
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise PermissionError(f"无权限创建 {path}") from exc
        raise PermissionError(f"无权限创建 {path}")