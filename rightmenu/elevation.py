"""管理员权限检测与提权重启。

只负责"检测"和"重新拉起自身"，不改变当前进程权限。
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys

SW_SHOWNORMAL = 1
#: ShellExecuteW 返回值大于 32 表示成功（见 Win32 ShellExecute 文档）
_SHELL_EXECUTE_SUCCESS_THRESHOLD = 32

#: 通过 `python -m rightmenu` 启动时 sys.argv[0] 是 __main__.py 的路径，
#: argv 里不含 `-m rightmenu`，所以重启必须自己补回来，否则只会拉起一个空解释器。
_MODULE = "rightmenu"
#: 包目录的上一级作为工作目录，保证提权后 `-m rightmenu` 仍能被导入。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _shell_execute_runas(executable: str, params: str, workdir: str | None = None) -> int:
    return int(
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, workdir, SW_SHOWNORMAL
        )
    )


def relaunch_as_admin(argv: list[str] | None = None) -> bool:
    """以管理员身份重新启动本程序。

    ``argv`` 是模块参数（不含 ``-m rightmenu``，本函数会自动补上）。
    返回是否成功发起提权（已提权或用户取消 UAC 时返回 False）。
    调用方在返回 True 后应当退出当前实例。
    """
    if is_admin():
        return False
    extra = list(argv) if argv is not None else sys.argv[1:]
    params = subprocess.list2cmdline(["-m", _MODULE, *extra])
    try:
        return (
            _shell_execute_runas(sys.executable, params, _PROJECT_ROOT)
            > _SHELL_EXECUTE_SUCCESS_THRESHOLD
        )
    except OSError:
        return False