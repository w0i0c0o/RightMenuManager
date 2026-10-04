"""判定一条右键菜单项是否由 Windows 自带。

判定只依据「该项引用的模块落在哪里」，不去猜厂商：

- 只要能取到绝对路径，就以路径为准 —— 落在 Windows 目录（或 ``Program Files``
  下的 ``Windows`` / ``Windows xxx`` 系统组件目录，如 Windows Defender、
  Windows Photo Viewer）即为自带；只要有一个绝对路径落在别处，就判为第三方
  （如 ``rundll32.exe "C:\\Program Files\\App\\x.dll"`` 这种借系统宿主加载
  自己 DLL 的写法）。
- 取不到绝对路径时，退回裸模块名白名单：``shell32.dll``、``rundll32.exe`` 这类
  不带目录名的引用说明取自系统目录 / PATH。
- 一点线索都没有（如 ``ArmouryCrate`` 这类只写了个显示名的项）判为「非系统」：
  宁可多显示几项，也不误藏用户自己装的项。

注意：注册表里的路径常常**不带引号且含空格**（``InprocServer32`` 就是如此），
所以按空白切词会把 ``C:\\Program Files\\Windows Defender\\x.dll`` 截断成
``C:\\Program``，因此这里用正则直接抽取路径，而不是切词。
"""

from __future__ import annotations

import os
import re
from typing import Iterable

_MODULE_EXTENSIONS = r"dll|exe|cpl|msc|ocx"
#: 绝对路径除了模块，也可能是脚本/数据载荷（如 ``powershell.exe -File E:\x\y.ps1``）。
_PAYLOAD_EXTENSIONS = rf"{_MODULE_EXTENSIONS}|ps1|bat|cmd|vbs|js|py|jar|lnk|reg|msi"

#: 绝对路径形式的模块引用（盘符或 UNC）；允许路径中含空格与逗号。
_ABS_MODULE_RE = re.compile(
    rf"(?:[A-Za-z]:\\|\\\\)[^\"<>|?*\r\n]*?\.(?:{_PAYLOAD_EXTENSIONS})", re.IGNORECASE
)
#: 不带目录名的模块引用（``@shell32.dll,-51601``、``cmd.exe /s /k ...``）。
#: 前视断言排除紧跟在 ``\`` 之后的片段，避免把绝对路径的 basename 重复算一遍。
_BARE_MODULE_RE = re.compile(
    rf"(?<![\w:\\])([A-Za-z0-9_\-]+\.(?:{_MODULE_EXTENSIONS}))", re.IGNORECASE
)

#: 裸模块名白名单：不带目录名即取自系统目录 / PATH，第三方动词几乎都写完整路径。
_SYSTEM_MODULES = frozenset(
    {
        "shell32.dll",
        "windows.storage.dll",
        "efscore.dll",
        "imageres.dll",
        "themecpl.dll",
        "display.dll",
        "shimgvw.dll",
        "cscui.dll",
        "workfolderscontrol.dll",
        "printdialogs3d.dll",
        "unregmp2.exe",
        "rundll32.exe",
        "explorer.exe",
        "notepad.exe",
        "cmd.exe",
        "powershell.exe",
        "mshta.exe",
        "control.exe",
        "regedit.exe",
        "mmc.exe",
        "write.exe",
        "wordpad.exe",
        "mspaint.exe",
        "charmap.exe",
        "cleanmgr.exe",
        "dfrgui.exe",
        "sndvol.exe",
        "wscript.exe",
        "cscript.exe",
        "zipfldr.dll",
        "stobject.dll",
        "ntshrui.dll",
        "dlnashext.dll",
        "sendmail.dll",
        "printui.dll",
        "gameux.dll",
        "syncui.dll",
        "ieframe.dll",
        "shdocvw.dll",
        "urlmon.dll",
        "twinui.dll",
        "twinui.pcshell.dll",
        "devicepairingwizard.exe",
    }
)


def windows_dir() -> str:
    return os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"


def _relative_to(path: str, root: str) -> str | None:
    """``path`` 在 ``root`` 之下则返回相对部分，否则 None（大小写不敏感）。"""
    normalized = os.path.normpath(path)
    base = os.path.normpath(root).rstrip("\\/")
    if not base:
        return None
    if normalized.lower() == base.lower():
        return ""
    if normalized.lower().startswith(base.lower() + "\\"):
        return normalized[len(base) + 1 :]
    return None


def _program_files_dirs() -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramW6432"),
        )
        if value
    )


def _is_system_path(path: str, win_dir: str) -> bool:
    relative = _relative_to(path, win_dir)
    if relative is not None:
        # DriverStore 存放的是驱动包（显卡等厂商驱动），属第三方组件，不算系统自带。
        if "driverstore" in [part.lower() for part in relative.split("\\")]:
            return False
        return True
    for program_files in _program_files_dirs():
        relative = _relative_to(path, program_files)
        if not relative:
            continue
        # 只认 "Windows" 或 "Windows xxx"（Windows Defender / Windows Photo Viewer 等）；
        # "WindowsApps"（Store 应用）不算系统组件。
        segment = relative.split("\\")[0].lower()
        if segment == "windows" or segment.startswith("windows "):
            return True
    return False


def classify(evidence: Iterable[str], win_dir: str | None = None) -> bool:
    """给定一条菜单项的原始字符串（默认值 / MUIVerb / 命令 / Icon / DLL 等），判断是否 Windows 自带。"""
    win = win_dir or windows_dir()
    absolutes: list[str] = []
    bare: list[str] = []
    for text in evidence:
        if not text:
            continue
        expanded = os.path.expandvars(str(text))
        absolutes.extend(_ABS_MODULE_RE.findall(expanded))
        bare.extend(name.lower() for name in _BARE_MODULE_RE.findall(expanded))
    if absolutes:
        # 存在任何落在别处的绝对路径即判为第三方，避免被裸模块名误导。
        return all(_is_system_path(path, win) for path in absolutes)
    return any(name in _SYSTEM_MODULES for name in bare)