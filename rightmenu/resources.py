"""资源引用解析：把 ``@dll,-id`` 形式的间接字符串还原成实际显示文本。

Windows 把本地化的菜单文字放在 DLL 资源段里，注册表中只存一个间接引用，
例如 ``@%SystemRoot%\\system32\\shell32.dll,-8506``。若不解析，用户在列表里
只能看到一串 ``@dll,-id``，完全认不出对应哪个菜单。
"""

from __future__ import annotations

import ctypes
from typing import Callable

#: 解析器：给定间接字符串返回实际文本，无法解析时返回 None。
Loader = Callable[[str], "str | None"]

_INDIRECT_PREFIX = "@"
_BUFFER_SIZE = 1024

_shlwapi_cache: object | None = None


def strip_accelerator(text: str) -> str:
    """去掉快捷键标记 ``&``：``打开(&O)`` → ``打开(O)``。

    单个 ``&`` 是加速器标记（其后一个字符加下划线），应删除；
    ``&&`` 表示字面量 ``&``，保留一个。
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "&":
            if index + 1 < length and text[index + 1] == "&":
                out.append("&")
                index += 2
                continue
            index += 1  # 丢弃加速器标记本身，保留其后的字母
            continue
        out.append(char)
        index += 1
    return "".join(out)


def load_indirect_string(source: str) -> str | None:
    """调用 ``SHLoadIndirectString`` 解析间接字符串；失败返回 None。

    解析失败很常见：引用的 DLL 未安装、资源号不存在等，此时交由上层回退。
    """
    try:
        lib = _shlwapi()
    except (AttributeError, OSError):
        return None
    buffer = ctypes.create_unicode_buffer(_BUFFER_SIZE)
    try:
        result = lib.SHLoadIndirectString(source, buffer, _BUFFER_SIZE, None)
    except OSError:
        return None
    if result != 0:
        return None
    return buffer.value or None


def resolve_text(text: str | None, loader: Loader | None = None) -> str | None:
    """把注册表里的原始文字解析成可直接显示的文本。

    - ``None`` 或纯空白 → ``None``；
    - ``@dll,-id`` 形式交给 loader 解析，解析不出结果 → ``None``；
    - 普通文本原样返回；
    - 统一去掉快捷键标记。
    """
    if text is None:
        return None
    raw = text.strip()
    if not raw:
        return None
    if raw.startswith(_INDIRECT_PREFIX):
        resolved = (loader or load_indirect_string)(raw)
        if resolved is None:
            return None
        resolved = strip_accelerator(resolved).strip()
        return resolved or None
    resolved = strip_accelerator(raw).strip()
    return resolved or None


def _shlwapi():
    """惰性加载并缓存 shlwapi，避免在非 Windows 环境下导入即失败。"""
    global _shlwapi_cache
    if _shlwapi_cache is None:
        lib = ctypes.WinDLL("shlwapi", use_last_error=True)
        lib.SHLoadIndirectString.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_void_p,
        ]
        lib.SHLoadIndirectString.restype = ctypes.c_long
        _shlwapi_cache = lib
    return _shlwapi_cache