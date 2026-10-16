"""扫描位置表。

描述「去哪里找右键菜单项」。``subpath`` 与 ``location`` 中的 ``{child}``
占位符在扫描时由枚举出的子键名替换。

位置名是**展示文案**，经 :func:`rightmenu.i18n.t` 取词，因此用 ``scan_targets()``
函数在调用时生成 —— 切换语言后重扫即可刷新。
"""

from __future__ import annotations

from dataclasses import dataclass

from rightmenu.i18n import t
from rightmenu.model import Kind


@dataclass(frozen=True)
class ScanTarget:
    kind: Kind
    location: str
    subpath: str
    enumerate_parent: str | None = None
    child_prefix: str = ""


def scan_targets() -> tuple[ScanTarget, ...]:
    """按当前语言生成扫描位置表。"""
    return (
        ScanTarget(Kind.STATIC, t("loc.all_files"), r"*\shell"),
        ScanTarget(Kind.SHELLEX, t("loc.all_files"), r"*\shellex\ContextMenuHandlers"),
        ScanTarget(Kind.STATIC, t("loc.all_filesystem_objects"), r"AllFilesystemObjects\shell"),
        ScanTarget(
            Kind.SHELLEX,
            t("loc.all_filesystem_objects"),
            r"AllFilesystemObjects\shellex\ContextMenuHandlers",
        ),
        ScanTarget(Kind.STATIC, t("loc.directory"), r"Directory\shell"),
        ScanTarget(Kind.SHELLEX, t("loc.directory"), r"Directory\shellex\ContextMenuHandlers"),
        ScanTarget(Kind.STATIC, t("loc.directory_background"), r"Directory\Background\shell"),
        ScanTarget(
            Kind.SHELLEX,
            t("loc.directory_background"),
            r"Directory\Background\shellex\ContextMenuHandlers",
        ),
        ScanTarget(Kind.STATIC, t("loc.folder"), r"Folder\shell"),
        ScanTarget(Kind.SHELLEX, t("loc.folder"), r"Folder\shellex\ContextMenuHandlers"),
        ScanTarget(Kind.STATIC, t("loc.drive"), r"Drive\shell"),
        ScanTarget(Kind.SHELLEX, t("loc.drive"), r"Drive\shellex\ContextMenuHandlers"),
        ScanTarget(Kind.STATIC, t("loc.library_folder"), r"LibraryFolder\shell"),
        ScanTarget(Kind.SHELLEX, t("loc.library_folder"), r"LibraryFolder\shellex\ContextMenuHandlers"),
        ScanTarget(Kind.STATIC, t("loc.desktop_background"), r"DesktopBackground\shell"),
        ScanTarget(
            Kind.SHELLEX,
            t("loc.desktop_background"),
            r"DesktopBackground\shellex\ContextMenuHandlers",
        ),
        ScanTarget(
            Kind.STATIC,
            t("loc.file_type", child="{child}"),
            r"SystemFileAssociations\{child}\shell",
            enumerate_parent=r"SystemFileAssociations",
        ),
        ScanTarget(
            Kind.SHELLEX,
            t("loc.file_type", child="{child}"),
            r"SystemFileAssociations\{child}\shellex\ContextMenuHandlers",
            enumerate_parent=r"SystemFileAssociations",
        ),
        ScanTarget(
            Kind.STATIC,
            t("loc.extension", child="{child}"),
            r"{child}\shell",
            enumerate_parent="",
            child_prefix=".",
        ),
        ScanTarget(
            Kind.SHELLEX,
            t("loc.extension", child="{child}"),
            r"{child}\shellex\ContextMenuHandlers",
            enumerate_parent="",
            child_prefix=".",
        ),
    )