"""Windows 右键菜单管理器。

以非破坏、可逆的方式管理资源管理器右键菜单项：
- Shell 扩展处理器：通过 Shell Extensions\\Blocked 屏蔽清单禁用
- 静态菜单项：通过 LegacyDisable 值禁用

本包不会删除任何注册表键，也不会修改其他软件自身的注册信息。
"""

__version__ = "0.1.0"