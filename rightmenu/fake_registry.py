"""内存注册表实现，供测试与 dry-run 使用。

语义与 winreg 保持一致：路径与值名大小写不敏感；写入会自动创建缺失的键与祖先。
`delete_key` 被刻意实现为断言失败 —— 任何试图删除注册表键的代码路径都会在这里暴露。
"""

from __future__ import annotations


def _norm_path(path: str) -> str:
    return path.strip("\\").upper()


def _norm_name(name: str | None) -> str:
    return "" if name is None else name.upper()


class FakeRegistry:
    def __init__(
        self,
        initial: dict[str, dict[str, tuple[object, int]]] | None = None,
        readonly_prefixes: tuple[str, ...] = (),
    ) -> None:
        self._data: dict[str, dict[str, tuple[object, int]]] = {}
        self._orig: dict[str, str] = {}
        self._readonly = tuple(_norm_path(p) for p in readonly_prefixes)
        self.delete_key_calls = 0

        for path, values in (initial or {}).items():
            self._ensure_key(path)
            for name, pair in values.items():
                self._data[_norm_path(path)][_norm_name(name)] = pair

    # ---- 内部 ----

    def _ensure_key(self, path: str) -> str:
        original = path.strip("\\")
        norm = _norm_path(path)
        if norm in self._data:
            return norm
        self._data[norm] = {}
        self._orig[norm] = original
        if "\\" in original:
            self._ensure_key(original.rsplit("\\", 1)[0])
        return norm

    # ---- RegistryBackend ----

    def key_exists(self, path: str) -> bool:
        return _norm_path(path) in self._data

    def list_subkeys(self, path: str) -> list[str]:
        norm = _norm_path(path)
        if norm not in self._data:
            return []
        prefix = norm + "\\"
        children = []
        for key in self._data:
            if key.startswith(prefix):
                rest = key[len(prefix) :]
                if "\\" not in rest:
                    children.append(self._orig[key].rsplit("\\", 1)[-1])
        return children

    def read_value(self, path: str, name: str | None) -> tuple[object, int] | None:
        values = self._data.get(_norm_path(path))
        if values is None:
            return None
        return values.get(_norm_name(name))

    def write_value(self, path: str, name: str | None, value: object, vtype: int) -> None:
        norm = self._ensure_key(path)
        self._data[norm][_norm_name(name)] = (value, vtype)

    def delete_value(self, path: str, name: str | None) -> None:
        norm = _norm_path(path)
        values = self._data.get(norm)
        key = _norm_name(name)
        if values is None or key not in values:
            raise FileNotFoundError(f"值不存在: {path} :: {name or '(默认)'}")
        del values[key]

    def ensure_writable(self, path: str) -> None:
        norm = _norm_path(path)
        for prefix in self._readonly:
            if norm == prefix or norm.startswith(prefix + "\\"):
                raise PermissionError(f"无权限写入 {path}")

    # ---- 禁止删除键（测试陷阱） ----

    def delete_key(self, path: str) -> None:
        self.delete_key_calls += 1
        raise AssertionError(f"本工具禁止删除注册表键，收到: {path}")

    # ---- 测试辅助 ----

    def snapshot(self) -> dict[str, dict[str, tuple[object, int]]]:
        return {path: dict(values) for path, values in self._data.items()}

    def keys(self) -> set[str]:
        return set(self._data)