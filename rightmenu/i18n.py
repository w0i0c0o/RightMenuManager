"""多语言（i18n）：内置基准 + 外部语言包叠加。

设计取舍见 ``docs/decisions/2026-10-12-i18n-mechanism.md``：

- 内置 ``CATALOG`` 保底 —— ``lang/`` 丢失也能跑，且是翻译的权威来源；
- 外部 ``lang/<code>.json``（扁平 ``key -> 文本``）启动时扫描并叠加，
  因此「新增一门语言 = 丢一个文件」，不动一行代码；
- 取值链：外部包[lang][key] → 内置[lang][key] → 内置["en"][key] → key 本身；
- 缺词、目录缺失、语言包损坏都不抛异常 —— 界面绝不因翻译缺失而崩。

枚举值（scope/kind/method）是机器可读 token，恒为英文，不经本模块。
"""

from __future__ import annotations

import ctypes
import json
import os
import re
from pathlib import Path

#: 兜底语言：任何 key 在目标语言缺失时最终落到这里。
FALLBACK_LANGUAGE = "en"

#: 内置随附的语言（顺序即界面下拉框顺序）。
BUILTIN_LANGUAGES: tuple[str, ...] = ("zh_CN", "en")

#: GetUserDefaultUILanguage() 返回的中文各变体 LANGID（简/繁/港/新/澳）。
_CHINESE_LANGIDS = frozenset({0x0804, 0x0404, 0x0C04, 0x1004, 0x1404})

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

#: key -> {语言代码: 文本}。zh_CN 与 en 必须覆盖完全相同的 key 集合。
CATALOG: dict[str, dict[str, str]] = {
    # ---- 窗口 ----
    "app.title": {"zh_CN": "Windows 右键菜单管理器", "en": "Windows Context Menu Manager"},
    # ---- 工具栏 ----
    "toolbar.scope": {"zh_CN": "范围：", "en": "Scope: "},
    "toolbar.hide_system": {"zh_CN": "只看非 Windows 自带", "en": "Hide Windows built-ins"},
    "toolbar.search": {"zh_CN": "搜索：", "en": "Search: "},
    "toolbar.language": {"zh_CN": "语言：", "en": "Language: "},
    # ---- 范围 ----
    "scope.user": {
        "zh_CN": "仅当前用户（无需管理员）",
        "en": "Current user only (no admin)",
    },
    "scope.machine": {
        "zh_CN": "当前用户 + 全机器（需要管理员）",
        "en": "Current user + all users (needs admin)",
    },
    "scope.user.short": {"zh_CN": "仅当前用户", "en": "Current user"},
    "scope.machine.short": {"zh_CN": "全机器", "en": "All users"},
    # ---- 提示条 ----
    "banner.grouping": {
        "zh_CN": "列表按「功能」归并：选中一行即可一次性关闭/显示该功能在所有文件类型下的全部条目；"
        "展开后可按文件类型逐项控制。",
        "en": "Rows are merged by function: selecting one row disables/restores that function "
        "across every file type at once; expand it to control each file type individually.",
    },
    # ---- 按钮 ----
    "btn.disable": {"zh_CN": "禁用选中项", "en": "Disable selected"},
    "btn.enable": {"zh_CN": "恢复选中项", "en": "Restore selected"},
    "btn.alias": {"zh_CN": "设置别名…", "en": "Set alias…"},
    "btn.restore": {"zh_CN": "一键恢复全部改动", "en": "Restore all changes"},
    "btn.refresh": {"zh_CN": "刷新", "en": "Refresh"},
    "btn.expand_all": {"zh_CN": "展开全部", "en": "Expand all"},
    "btn.collapse_all": {"zh_CN": "折叠全部", "en": "Collapse all"},
    "btn.elevate": {"zh_CN": "以管理员身份重启", "en": "Restart as administrator"},
    # ---- 权限提示 ----
    "hint.needs_admin": {
        "zh_CN": "全机器范围需要管理员权限才能修改",
        "en": "The all-users scope needs administrator rights to modify",
    },
    # ---- 列标题 ----
    "col.group": {"zh_CN": "功能 / 菜单项", "en": "Function / item"},
    "col.state": {"zh_CN": "状态", "en": "State"},
    "col.location": {"zh_CN": "位置", "en": "Location"},
    "col.kind": {"zh_CN": "类型 / 条目", "en": "Type / entries"},
    "col.detail": {"zh_CN": "命令 / DLL", "en": "Command / DLL"},
    # ---- 状态 ----
    "state.enabled": {"zh_CN": "启用中", "en": "Enabled"},
    "state.disabled": {"zh_CN": "已禁用", "en": "Disabled"},
    "state.partial": {"zh_CN": "部分禁用", "en": "Partial"},
    # ---- 类型 ----
    "kind.static": {"zh_CN": "菜单项", "en": "Menu item"},
    "kind.shellex": {"zh_CN": "扩展处理器", "en": "Shell extension"},
    # ---- 功能行 ----
    "group.needs_alias_suffix": {"zh_CN": "（注册表名）", "en": " (registry name)"},
    "group.locations_count": {"zh_CN": "{n} 处位置", "en": "{n} locations"},
    "group.items_count": {"zh_CN": "{n} 项", "en": "{n} entries"},
    # ---- 状态栏 ----
    "status.scope": {"zh_CN": "范围：{scope}", "en": "Scope: {scope}"},
    "status.groups": {"zh_CN": "功能 {n} 个", "en": "{n} functions"},
    "status.items": {"zh_CN": "条目 {n} 项", "en": "{n} entries"},
    "status.disabled": {"zh_CN": "已禁用 {n} 项", "en": "{n} disabled"},
    "status.hidden_system": {
        "zh_CN": "已隐藏 {n} 项 Windows 自带",
        "en": "{n} Windows built-ins hidden",
    },
    "status.not_admin": {"zh_CN": "当前未提权", "en": "Not elevated"},
    # ---- 消息 ----
    "msg.applied": {"zh_CN": "已应用 {n} 项变更", "en": "Applied {n} changes"},
    "msg.applied_failed": {
        "zh_CN": "已应用 {n} 项变更，{m} 项失败",
        "en": "Applied {n} changes, {m} failed",
    },
    "msg.restored": {"zh_CN": "已恢复 {n} 项改动", "en": "Restored {n} changes"},
    "msg.nothing_to_change": {"zh_CN": "没有需要变更的项。", "en": "Nothing to change."},
    "msg.select_group_for_alias": {
        "zh_CN": "请先选中一行「功能」再设置别名。",
        "en": "Select a function row first, then set an alias.",
    },
    "err.permission": {
        "zh_CN": "权限不足：{err}\n请点击「以管理员身份重启」后重试。",
        "en": "Permission denied: {err}\nClick “Restart as administrator” and try again.",
    },
    "err.elevate": {
        "zh_CN": "未能提权。可能被 UAC 拒绝，或当前已是管理员。",
        "en": "Elevation failed. It may have been declined by UAC, or you are already an administrator.",
    },
    # ---- 对话框 ----
    "dialog.restore.title": {"zh_CN": "确认恢复", "en": "Confirm restore"},
    "dialog.restore.message": {
        "zh_CN": "将按改动日志把所有被本工具修改的菜单项还原，是否继续？",
        "en": "Restore every menu item this tool has changed, using the change log. Continue?",
    },
    "dialog.alias.title": {"zh_CN": "设置别名", "en": "Set alias"},
    "dialog.alias.prompt": {
        "zh_CN": "给这个右键功能起一个你能认出的名字，之后即可按它搜索、归并与一键开关。\n\n"
        "当前名称：{name}\n涉及 {total} 条、{locations} 处位置\n\n留空并确定可清除别名。",
        "en": "Give this context-menu function a recognizable name; you can then search, group "
        "and toggle it by that name.\n\nCurrent name: {name}\n{total} entries across "
        "{locations} locations\n\nLeave blank and confirm to clear the alias.",
    },
    "dialog.preview.title": {"zh_CN": "变更预览", "en": "Change preview"},
    "dialog.preview.heading": {
        "zh_CN": "应用前请确认以下注册表改动：",
        "en": "Review the following registry changes before applying:",
    },
    "dialog.preview.cancel": {"zh_CN": "取消", "en": "Cancel"},
    "dialog.preview.confirm": {"zh_CN": "确认应用", "en": "Apply"},
    "dialog.close": {"zh_CN": "关闭", "en": "Close"},
    "dialog.item_detail.title": {"zh_CN": "菜单项详情", "en": "Item details"},
    "dialog.group_detail.title": {"zh_CN": "功能详情", "en": "Function details"},
    "dialog.info.title": {"zh_CN": "提示", "en": "Notice"},
    "dialog.error.title": {"zh_CN": "出错了", "en": "Error"},
    # ---- 详情（单条菜单项） ----
    "detail.name": {"zh_CN": "名称：{v}", "en": "Name: {v}"},
    "detail.location": {"zh_CN": "位置：{v}", "en": "Location: {v}"},
    "detail.kind": {"zh_CN": "类型：{v}", "en": "Type: {v}"},
    "detail.scope": {"zh_CN": "范围：{v}", "en": "Scope: {v}"},
    "detail.state": {"zh_CN": "状态：{v}", "en": "State: {v}"},
    "detail.key_path": {"zh_CN": "注册表键：{v}", "en": "Registry key: {v}"},
    "detail.command": {"zh_CN": "命令：{v}", "en": "Command: {v}"},
    "detail.clsid": {"zh_CN": "CLSID：{v}", "en": "CLSID: {v}"},
    "detail.dll": {"zh_CN": "DLL：{v}", "en": "DLL: {v}"},
    "detail.extended_only": {
        "zh_CN": "仅在按住 Shift 右键时显示",
        "en": "Shown only when right-clicking with Shift held",
    },
    # ---- 详情（功能组） ----
    "gdetail.name": {"zh_CN": "功能名称：{v}", "en": "Function name: {v}"},
    "gdetail.raw_name": {"zh_CN": "注册表名称：{v}", "en": "Registry name: {v}"},
    "gdetail.state": {"zh_CN": "状态：{v}", "en": "State: {v}"},
    "gdetail.items": {"zh_CN": "涉及条目：{n} 条", "en": "Entries: {n}"},
    "gdetail.locations": {"zh_CN": "涉及位置：{v}", "en": "Locations: {v}"},
    "gdetail.kinds": {"zh_CN": "类型：{v}", "en": "Types: {v}"},
    "gdetail.scopes": {"zh_CN": "范围：{v}", "en": "Scopes: {v}"},
    "gdetail.dll_header": {"zh_CN": "DLL：", "en": "DLL:"},
    "gdetail.command_header": {"zh_CN": "命令：", "en": "Command:"},
    "gdetail.will_handle": {
        "zh_CN": "要关闭「{name}」，本工具将处理以下 {n} 项：",
        "en": "To disable “{name}”, this tool will handle these {n} entries:",
    },
    "gdetail.item_line": {
        "zh_CN": "  · [{location}] {kind}  {key_name}",
        "en": "  · [{location}] {kind}  {key_name}",
    },
    "gdetail.needs_alias_hint": {
        "zh_CN": "提示：该名称取自注册表键名，可能与实际右键菜单文字不同"
        "（部分功能的文字由 DLL 运行时生成）。可点击「设置别名…」起一个能认出的名字。",
        "en": "Note: this name comes from the registry key and may differ from the actual "
        "context-menu text (some functions generate their text at runtime in a DLL). "
        "Click “Set alias…” to give it a recognizable name.",
    },
    # ---- 变更预览 ----
    "preview.heading": {
        "zh_CN": "即将修改以下注册表值（只增删值，不删键）：",
        "en": "The following registry values will be changed (values only; keys are never deleted):",
    },
    "preview.empty": {"zh_CN": "（没有需要变更的项）", "en": "(nothing to change)"},
    "preview.verb_write": {"zh_CN": "写入", "en": "write"},
    "preview.verb_delete": {"zh_CN": "删除", "en": "delete"},
    "preview.change_line": {"zh_CN": "· {description}", "en": "· {description}"},
    "preview.change_meta": {
        "zh_CN": "    操作: {verb}    值名: {value_name}",
        "en": "    action: {verb}    value: {value_name}",
    },
    "preview.change_path": {"zh_CN": "    路径: {path}", "en": "    path: {path}"},
    "preview.default_value": {"zh_CN": "(默认)", "en": "(default)"},
    "preview.skipped_heading": {
        "zh_CN": "以下项已跳过（不会修改注册表）：",
        "en": "The following items were skipped (the registry will not be touched):",
    },
    "preview.skipped_line": {"zh_CN": "· {name}：{reason}", "en": "· {name}: {reason}"},
    # ---- 扫描位置名称 ----
    "loc.all_files": {"zh_CN": "所有文件", "en": "All files"},
    "loc.all_filesystem_objects": {"zh_CN": "所有文件系统对象", "en": "All filesystem objects"},
    "loc.directory": {"zh_CN": "目录", "en": "Directory"},
    "loc.directory_background": {"zh_CN": "目录背景", "en": "Directory background"},
    "loc.folder": {"zh_CN": "文件夹", "en": "Folder"},
    "loc.drive": {"zh_CN": "驱动器", "en": "Drive"},
    "loc.library_folder": {"zh_CN": "库文件夹", "en": "Library folder"},
    "loc.desktop_background": {"zh_CN": "桌面背景", "en": "Desktop background"},
    "loc.file_type": {"zh_CN": "{child} 文件", "en": "{child} files"},
    "loc.extension": {"zh_CN": "扩展名 {child}", "en": "Extension {child}"},
    # ---- 变更描述 ----
    "action.block": {"zh_CN": "屏蔽「{name}」", "en": "Block “{name}”"},
    "action.unblock": {"zh_CN": "解除屏蔽「{name}」", "en": "Unblock “{name}”"},
    "action.disable": {"zh_CN": "禁用「{name}」", "en": "Disable “{name}”"},
    "action.enable": {"zh_CN": "恢复「{name}」", "en": "Restore “{name}”"},
    "action.unsupported_clsid": {
        "zh_CN": "无法解析 CLSID，不能用屏蔽清单安全地处理该项",
        "en": "Cannot resolve the CLSID; this item cannot be safely handled via the block list",
    },
    # ---- 变更日志 ----
    "journal.restore_prefix": {"zh_CN": "恢复：{v}", "en": "Restore: {v}"},
    "journal.undo_prefix": {"zh_CN": "撤销：{v}", "en": "Undo: {v}"},
    # ---- 语言名称 ----
    "lang_name.zh_CN": {"zh_CN": "简体中文", "en": "Simplified Chinese"},
    "lang_name.en": {"zh_CN": "English", "en": "English"},
    # ---- 通用 ----
    "list.separator": {"zh_CN": "、", "en": ", "},
    # ---- 命令行 ----
    "cli.description": {
        "zh_CN": "以非破坏、可逆的方式管理 Windows 右键菜单项。",
        "en": "Manage Windows context-menu items non-destructively and reversibly.",
    },
    "cli.scan_help": {"zh_CN": "无界面模式：扫描并输出 JSON", "en": "Headless mode: scan and print JSON"},
    "cli.scope_help": {"zh_CN": "扫描范围（默认 user）", "en": "Scan scope (default: user)"},
    "cli.lang_help": {
        "zh_CN": "界面语言（默认跟随系统）",
        "en": "UI language (default: follow the system)",
    },
}

#: 运行期状态。首次取词时惰性初始化（见 _ensure_initialized）。
_initialized = False
_language = FALLBACK_LANGUAGE
_lang_dir: Path | None = None
_settings_path: Path | None = None
_external: dict[str, dict[str, str]] = {}


# ---- 路径 ----


def default_lang_dir() -> Path:
    """外部语言包目录：项目/发行根目录下的 ``lang/``。"""
    return Path(__file__).resolve().parent.parent / "lang"


def default_settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "RightMenuManager" / "settings.json"


# ---- 语言检测 ----


def _user_default_language_id() -> int | None:
    """Windows 用户界面语言的 LANGID；非 Windows 或调用失败返回 None。"""
    try:
        return int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except (AttributeError, OSError, ValueError):
        return None


def _language_from_env() -> str:
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name)
        if value and value.lower().startswith("zh"):
            return "zh_CN"
    return FALLBACK_LANGUAGE


def detect_language() -> str:
    """按系统语言决定界面语言：中文各变体 → zh_CN，其余 → en。"""
    langid = _user_default_language_id()
    if langid is None:
        return _language_from_env()
    return "zh_CN" if langid in _CHINESE_LANGIDS else FALLBACK_LANGUAGE


# ---- 外部语言包 ----


def _load_packs(lang_dir: Path) -> dict[str, dict[str, str]]:
    """扫描 ``lang/*.json``（文件名即语言代码），损坏或非对象的文件忽略。

    以 ``utf-8-sig`` 读取：翻译者用记事本等工具另存为「UTF-8 带 BOM」也能直接用。
    """
    packs: dict[str, dict[str, str]] = {}
    if not lang_dir.is_dir():
        return packs
    for path in sorted(lang_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        packs[path.stem] = {str(k): v for k, v in raw.items() if isinstance(v, str)}
    return packs


# ---- settings ----


def _load_saved_language(path: Path) -> str | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    language = raw.get("language")
    return language if isinstance(language, str) and language.strip() else None


def _save_language(language: str, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"language": language}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # 设置写不进去不该影响使用 —— 只是下次启动回退到系统检测。
        pass


# ---- 初始化与切换 ----


def configure(
    language: str | None = None,
    lang_dir: Path | str | None = None,
    settings_path: Path | str | None = None,
) -> str:
    """初始化/重载：加载外部语言包并决定当前语言，返回实际生效的语言代码。

    ``language=None`` 时按「保存值 → 系统检测」决定；``lang_dir``/``settings_path``
    仅供测试注入，省略即用默认位置。
    """
    global _initialized, _language, _lang_dir, _settings_path, _external
    _initialized = True
    _lang_dir = Path(lang_dir) if lang_dir is not None else default_lang_dir()
    _settings_path = (
        Path(settings_path) if settings_path is not None else default_settings_path()
    )
    _external = _load_packs(_lang_dir)
    if language is None:
        language = _load_saved_language(_settings_path) or detect_language()
    _language = language
    return _language


def _ensure_initialized() -> None:
    if not _initialized:
        configure()


def get_language() -> str:
    _ensure_initialized()
    return _language


def set_language(language: str, persist: bool = True) -> str:
    """切换语言；``persist`` 为真时写入 settings.json。"""
    global _language
    _ensure_initialized()
    _language = language or FALLBACK_LANGUAGE
    if persist and _settings_path is not None:
        _save_language(_language, _settings_path)
    return _language


def available_languages() -> list[str]:
    """可选语言：内置两种在前，外部新增的按名称排序在后。"""
    _ensure_initialized()
    extras = sorted(set(_external) - set(BUILTIN_LANGUAGES))
    return list(BUILTIN_LANGUAGES) + extras


def language_label(code: str) -> str:
    """语言的显示名（如「简体中文」）；无对应词条时回退为代码本身。"""
    key = f"lang_name.{code}"
    if key in CATALOG or key in _external.get(code, {}):
        return t(key)
    return code


# ---- 取词 ----


def _lookup(language: str, key: str) -> str | None:
    table = _external.get(language)
    if table is not None and key in table:
        return table[key]
    entry = CATALOG.get(key)
    if entry is None:
        return None
    if language in entry:
        return entry[language]
    return entry.get(FALLBACK_LANGUAGE)


def _fill(text: str, mapping: dict[str, object]) -> str:
    """只替换映射里出现过的 ``{占位符}``；值里的花括号不再二次解析。"""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(mapping[name]) if name in mapping else match.group(0)

    return _PLACEHOLDER.sub(replace, text)


def t(key: str, **kwargs: object) -> str:
    """取词并做占位符替换；缺词时返回 key 本身，绝不抛异常。"""
    _ensure_initialized()
    text = _lookup(_language, key)
    if text is None:
        text = key
    if kwargs:
        text = _fill(text, kwargs)
    return text