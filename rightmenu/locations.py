"""扫描位置表。

纯数据：描述「去哪里找右键菜单项」。``subpath`` 与 ``location`` 中的 ``{child}``
占位符在扫描时由枚举出的子键名替换。
"""

from __future__ import annotations

from dataclasses import dataclass

from rightmenu.model import Kind


@dataclass(frozen=True)
class ScanTarget:
    kind: Kind
    location: str
    subpath: str
    enumerate_parent: str | None = None
    child_prefix: str = ""


SCAN_TARGETS: tuple[ScanTarget, ...] = (
    ScanTarget(Kind.STATIC, "所有文件", r"*\shell"),
    ScanTarget(Kind.SHELLEX, "所有文件", r"*\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "所有文件系统对象", r"AllFilesystemObjects\shell"),
    ScanTarget(Kind.SHELLEX, "所有文件系统对象", r"AllFilesystemObjects\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "目录", r"Directory\shell"),
    ScanTarget(Kind.SHELLEX, "目录", r"Directory\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "目录背景", r"Directory\Background\shell"),
    ScanTarget(Kind.SHELLEX, "目录背景", r"Directory\Background\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "文件夹", r"Folder\shell"),
    ScanTarget(Kind.SHELLEX, "文件夹", r"Folder\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "驱动器", r"Drive\shell"),
    ScanTarget(Kind.SHELLEX, "驱动器", r"Drive\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "库文件夹", r"LibraryFolder\shell"),
    ScanTarget(Kind.SHELLEX, "库文件夹", r"LibraryFolder\shellex\ContextMenuHandlers"),
    ScanTarget(Kind.STATIC, "桌面背景", r"DesktopBackground\shell"),
    ScanTarget(Kind.SHELLEX, "桌面背景", r"DesktopBackground\shellex\ContextMenuHandlers"),
    ScanTarget(
        Kind.STATIC,
        "{child} 文件",
        r"SystemFileAssociations\{child}\shell",
        enumerate_parent=r"SystemFileAssociations",
    ),
    ScanTarget(
        Kind.SHELLEX,
        "{child} 文件",
        r"SystemFileAssociations\{child}\shellex\ContextMenuHandlers",
        enumerate_parent=r"SystemFileAssociations",
    ),
    ScanTarget(Kind.STATIC, "扩展名 {child}", r"{child}\shell", enumerate_parent="", child_prefix="."),
    ScanTarget(
        Kind.SHELLEX,
        "扩展名 {child}",
        r"{child}\shellex\ContextMenuHandlers",
        enumerate_parent="",
        child_prefix=".",
    ),
)