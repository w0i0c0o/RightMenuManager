"""tkinter 视图。

只负责画界面与收集用户操作；所有判断逻辑都在 ui/controller.py。

列表按「功能」归并成两层：

- 顶层一行 = 一个右键功能（如「上传到百度网盘」），选中它即可一次性
  关闭/显示该功能在所有文件类型下的全部条目；
- 展开后是逐项明细，可精确定位到某个文件类型/位置单独开关。

这样既满足「跨文件类型的一键消除」，也保留了原来的分文件类型控制。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from rightmenu.elevation import relaunch_as_admin
from rightmenu.grouping import MenuGroup
from rightmenu.journal import Journal
from rightmenu.model import ContextMenuItem, Kind, Scope
from rightmenu.registry import Win32Registry
from rightmenu.ui.controller import Controller, build_preview_text

SCOPE_LABELS = {
    Scope.USER: "仅当前用户（无需管理员）",
    Scope.MACHINE: "当前用户 + 全机器（需要管理员）",
}
KIND_LABELS = {
    Kind.STATIC: "菜单项",
    Kind.SHELLEX: "扩展处理器",
}
STATE_LABELS = {
    "enabled": "启用中",
    "disabled": "已禁用",
    "partial": "部分禁用",
}
COLUMNS = (
    ("state", "状态", 90),
    ("location", "位置", 160),
    ("kind", "类型 / 条目", 110),
    ("detail", "命令 / DLL", 400),
)
TREE_COLUMN = "#0"


class App:
    def __init__(
        self,
        backend=None,
        journal: Journal | None = None,
        scope: Scope = Scope.USER,
        admin: bool | None = None,
        root: tk.Misc | None = None,
    ) -> None:
        self.controller = Controller(
            backend if backend is not None else Win32Registry(),
            journal if journal is not None else Journal(),
            scope=scope,
            admin=admin,
        )
        self.root = root if root is not None else tk.Tk()
        self.root.title("Windows 右键菜单管理器")
        self.root.geometry("1180x680")
        self.root.minsize(960, 500)

        self._query = tk.StringVar()
        self._scope_var = tk.StringVar(value=self.controller.scope.value)
        self._hide_system = tk.BooleanVar(value=False)
        self._status = tk.StringVar()
        self._group_by_iid: dict[str, MenuGroup] = {}
        self._item_by_iid: dict[str, ContextMenuItem] = {}

        self._build()
        self.reload()

    # ---- 界面构建 ----

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(4, weight=1)

        ttk.Label(toolbar, text="范围：").grid(row=0, column=0, padx=(0, 4))
        for index, scope in enumerate((Scope.USER, Scope.MACHINE), start=1):
            ttk.Radiobutton(
                toolbar,
                text=SCOPE_LABELS[scope],
                value=scope.value,
                variable=self._scope_var,
                command=self._on_scope_change,
            ).grid(row=0, column=index, padx=(0, 12), sticky="w")

        ttk.Checkbutton(
            toolbar,
            text="只看非 Windows 自带",
            variable=self._hide_system,
            command=self.reload,
        ).grid(row=0, column=3, padx=(0, 16), sticky="w")

        search_box = ttk.Frame(toolbar)
        search_box.grid(row=0, column=4, sticky="e")
        ttk.Label(search_box, text="搜索：").pack(side="left")
        ttk.Entry(search_box, textvariable=self._query, width=28).pack(side="left")
        self._query.trace_add("write", lambda *_: self.reload())

        ttk.Label(
            self.root,
            text="列表按「功能」归并：选中一行即可一次性关闭/显示该功能在所有文件类型下的全部条目；"
            "展开后可按文件类型逐项控制。",
            padding=(12, 0, 12, 4),
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w")

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        actions.grid(row=3, column=0, sticky="ew")

        self._btn_disable = ttk.Button(actions, text="禁用选中项", command=self._run_disable)
        self._btn_disable.pack(side="left")
        self._btn_enable = ttk.Button(actions, text="恢复选中项", command=self._run_enable)
        self._btn_enable.pack(side="left", padx=6)
        self._btn_alias = ttk.Button(actions, text="设置别名…", command=self._run_alias)
        self._btn_alias.pack(side="left", padx=(6, 0))
        self._btn_restore = ttk.Button(actions, text="一键恢复全部改动", command=self._run_restore)
        self._btn_restore.pack(side="left", padx=(18, 6))
        ttk.Button(actions, text="刷新", command=self.reload).pack(side="left")
        ttk.Button(actions, text="展开全部", command=self.expand_all).pack(side="left", padx=6)
        ttk.Button(actions, text="折叠全部", command=self.collapse_all).pack(side="left")

        self._hint = ttk.Label(actions, text="", foreground="#b34700")
        self._hint.pack(side="left", padx=16)
        self._btn_elevate = ttk.Button(actions, text="以管理员身份重启", command=self.elevate)

        table = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table,
            columns=[c[0] for c in COLUMNS],
            show="tree headings",
            selectmode="extended",
        )
        self.tree.heading(TREE_COLUMN, text="功能 / 菜单项")
        self.tree.column(TREE_COLUMN, width=340, anchor="w", stretch=False)
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w", stretch=(key == "detail"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("disabled", foreground="#8a8a8a")
        self.tree.tag_configure("partial", foreground="#b34700")
        self.tree.tag_configure("unreadable", foreground="#8a5a00")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_action_state())
        self.tree.bind("<Double-1>", self._show_details)

        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(self.root, textvariable=self._status, padding=(12, 4)).grid(
            row=4, column=0, sticky="ew"
        )

    # ---- 数据刷新 ----

    def reload(self) -> None:
        query = self._query.get()
        hide_system = self._hide_system.get()
        groups = self.controller.filter_groups(query, hide_system)
        self._group_by_iid = {}
        self._item_by_iid = {}

        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        auto_open = bool(query.strip())
        for group in groups:
            group_iid = self._group_iid(group)
            self._group_by_iid[group_iid] = group
            self.tree.insert(
                "",
                "end",
                iid=group_iid,
                text=self._group_text(group),
                values=self._group_values(group),
                tags=self._group_tags(group),
                open=auto_open,
            )
            for item in group.items:
                child_iid = self._item_iid(item)
                self._item_by_iid[child_iid] = item
                self.tree.insert(
                    group_iid,
                    "end",
                    iid=child_iid,
                    text=f"· {item.key_name}",
                    values=self._item_values(item),
                    tags=("disabled",) if item.disabled else (),
                )
        self._update_action_state()
        self._update_status(query, groups, hide_system)

    def _group_iid(self, group: MenuGroup) -> str:
        return f"g::{group.key}"

    def _item_iid(self, item: ContextMenuItem) -> str:
        return f"i::{item.id}"

    def _group_text(self, group: MenuGroup) -> str:
        suffix = "（注册表名）" if group.needs_alias else ""
        return f"{group.label}{suffix}"

    def _group_values(self, group: MenuGroup) -> tuple:
        return (
            STATE_LABELS[group.state],
            f"{len(group.locations)} 处位置",
            f"{group.total} 项",
            group.sample_detail,
        )

    def _group_tags(self, group: MenuGroup) -> tuple[str, ...]:
        if group.state == "disabled":
            return ("disabled",)
        if group.state == "partial":
            return ("partial",)
        if group.needs_alias:
            return ("unreadable",)
        return ()

    def _item_values(self, item: ContextMenuItem) -> tuple:
        return (
            "已禁用" if item.disabled else "启用中",
            item.location,
            KIND_LABELS[item.kind],
            item.command or item.dll_path or "",
        )

    def _update_status(self, query: str, groups: list[MenuGroup], hide_system: bool) -> None:
        visible = self.controller.visible_items(query, hide_system)
        scope_text = "仅当前用户" if self.controller.scope is Scope.USER else "全机器"
        parts = [
            f"范围：{scope_text}",
            f"功能 {len(groups)} 个",
            f"条目 {len(visible)} 项",
            f"已禁用 {sum(1 for item in visible if item.disabled)} 项",
        ]
        if hide_system:
            parts.append(f"已隐藏 {self.controller.hidden_system_count()} 项 Windows 自带")
        if not self.controller.admin:
            parts.append("当前未提权")
        self._status.set("    ".join(parts))

    # ---- 权限状态 ----

    def _update_action_state(self) -> None:
        writable = self.controller.can_write()
        has_selection = bool(self.tree.selection())
        self._btn_disable.configure(state="normal" if writable and has_selection else "disabled")
        self._btn_enable.configure(state="normal" if writable and has_selection else "disabled")
        self._btn_restore.configure(state="normal" if writable else "disabled")
        single_group = len(self.selected_groups()) == 1
        self._btn_alias.configure(state="normal" if single_group else "disabled")

        needs_elevation = self.controller.scope is Scope.MACHINE and not self.controller.admin
        if needs_elevation:
            self._hint.configure(text="全机器范围需要管理员权限才能修改")
            self._btn_elevate.pack(side="left", padx=6)
        else:
            self._hint.configure(text="")
            self._btn_elevate.pack_forget()

    def _on_scope_change(self) -> None:
        self.controller.set_scope(Scope(self._scope_var.get()))
        self.reload()

    # ---- 展开 / 折叠 ----

    def expand_all(self) -> None:
        for iid in self._group_by_iid:
            self.tree.item(iid, open=True)

    def collapse_all(self) -> None:
        for iid in self._group_by_iid:
            self.tree.item(iid, open=False)

    # ---- 选择解析 ----

    def selected_groups(self) -> list[MenuGroup]:
        return [self._group_by_iid[iid] for iid in self.tree.selection() if iid in self._group_by_iid]

    def selected_items(self) -> list[ContextMenuItem]:
        """选中的功能组展开为组内全部条目；选中的明细行只取该条。"""
        items: list[ContextMenuItem] = []
        seen: set[str] = set()
        for iid in self.tree.selection():
            if iid in self._group_by_iid:
                candidates = self._group_by_iid[iid].items
            elif iid in self._item_by_iid:
                candidates = (self._item_by_iid[iid],)
            else:
                continue
            for item in candidates:
                if item.id not in seen:
                    seen.add(item.id)
                    items.append(item)
        return items

    # ---- 操作 ----

    def preview_disable(self, items: list[ContextMenuItem]):
        return self.controller.plan_disable(items)

    def preview_enable(self, items: list[ContextMenuItem]):
        return self.controller.plan_enable(items)

    def apply_changes(self, changes):
        """执行变更并刷新列表。权限不足时提示后返回 None。"""
        try:
            result = self.controller.commit(changes)
        except PermissionError as exc:
            self._error(f"权限不足：{exc}\n请点击「以管理员身份重启」后重试。")
            return None
        self.reload()
        failed = f"，{len(result.failed)} 项失败" if result.failed else ""
        self._status.set(f"已应用 {len(result.applied)} 项变更{failed}")
        return result

    def restore_all(self):
        try:
            result = self.controller.restore_all()
        except PermissionError as exc:
            self._error(f"权限不足：{exc}\n请点击「以管理员身份重启」后重试。")
            return None
        self.reload()
        self._status.set(f"已恢复 {len(result.applied)} 项改动")
        return result

    def elevate(self) -> None:
        if relaunch_as_admin():
            self.root.destroy()
        else:
            self._error("未能提权。可能被 UAC 拒绝，或当前已是管理员。")

    def _run_disable(self) -> None:
        self._apply_with_preview(self.preview_disable(self.selected_items()))

    def _run_enable(self) -> None:
        self._apply_with_preview(self.preview_enable(self.selected_items()))

    def _apply_with_preview(self, plan) -> None:
        if not plan.changes and not plan.skipped:
            self._info("没有需要变更的项。")
            return
        if not self.confirm_preview(plan):
            return
        self.apply_changes(plan.changes)

    def _run_restore(self) -> None:
        if not messagebox.askyesno(
            "确认恢复", "将按改动日志把所有被本工具修改的菜单项还原，是否继续？"
        ):
            return
        self.restore_all()

    def _run_alias(self) -> None:
        groups = self.selected_groups()
        if len(groups) != 1:
            self._info("请先选中一行「功能」再设置别名。")
            return
        group = groups[0]
        initial = "" if group.needs_alias else group.label
        label = simpledialog.askstring(
            "设置别名",
            f"给这个右键功能起一个你能认出的名字，之后即可按它搜索、归并与一键开关。\n\n"
            f"当前名称：{group.raw_name}\n"
            f"涉及 {group.total} 条、{len(group.locations)} 处位置\n\n"
            "留空并确定可清除别名。",
            initialvalue=initial,
            parent=self.root,
        )
        if label is None:
            return
        self.controller.set_alias(group.key, label)
        self.reload()

    # ---- 对话框 ----

    def confirm_preview(self, plan) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("变更预览")
        dialog.transient(self.root)
        dialog.geometry("760x460")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(dialog, text="应用前请确认以下注册表改动：", padding=(12, 10, 12, 4)).grid(
            row=0, column=0, sticky="w"
        )
        text = tk.Text(dialog, wrap="word", font=("Consolas", 9))
        text.insert("1.0", build_preview_text(plan))
        text.configure(state="disabled")
        text.grid(row=1, column=0, sticky="nsew", padx=12)

        confirmed = {"value": False}

        def accept() -> None:
            confirmed["value"] = True
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=(12, 8))
        buttons.grid(row=2, column=0, sticky="e")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="确认应用", command=accept).pack(side="right", padx=6)

        dialog.grab_set()
        self.root.wait_window(dialog)
        return confirmed["value"]

    def _show_details(self, event=None) -> None:
        iid = self.tree.identify_row(event.y) if event is not None else ""
        if iid in self._group_by_iid:
            self._show_group_details(self._group_by_iid[iid])
            return
        if iid in self._item_by_iid:
            self._show_item_details(self._item_by_iid[iid])
            return
        groups = self.selected_groups()
        if groups:
            self._show_group_details(groups[0])
            return
        items = self.selected_items()
        if items:
            self._show_item_details(items[0])

    def _show_item_details(self, item: ContextMenuItem) -> None:
        lines = [
            f"名称：{item.display_name}",
            f"位置：{item.location}",
            f"类型：{KIND_LABELS[item.kind]}",
            f"范围：{'仅当前用户' if item.scope is Scope.USER else '全机器'}",
            f"状态：{'已禁用' if item.disabled else '启用中'}",
            f"注册表键：{item.key_path}",
        ]
        if item.command:
            lines.append(f"命令：{item.command}")
        if item.clsid:
            lines.append(f"CLSID：{item.clsid}")
        if item.dll_path:
            lines.append(f"DLL：{item.dll_path}")
        if item.extended:
            lines.append("仅在按住 Shift 右键时显示")
        self._show_text("菜单项详情", "\n".join(lines))

    def _show_group_details(self, group: MenuGroup) -> None:
        scopes = "、".join("仅当前用户" if s is Scope.USER else "全机器" for s in group.scopes)
        kinds = "、".join(KIND_LABELS[k] for k in group.kinds)
        lines = [
            f"功能名称：{group.label}",
            f"注册表名称：{group.raw_name}",
            f"状态：{STATE_LABELS[group.state]}",
            f"涉及条目：{group.total} 条",
            f"涉及位置：{'、'.join(group.locations)}",
            f"类型：{kinds}",
            f"范围：{scopes}",
        ]
        if group.dll_paths:
            lines.append("DLL：")
            lines.extend(f"  {path}" for path in group.dll_paths)
        if group.commands:
            lines.append("命令：")
            lines.extend(f"  {command}" for command in group.commands)
        lines.append("")
        lines.append(f"要关闭「{group.label}」，本工具将处理以下 {group.total} 项：")
        for item in group.items:
            lines.append(f"  · [{item.location}] {KIND_LABELS[item.kind]}  {item.key_name}")
            lines.append(f"      {item.key_path}")
        if group.needs_alias:
            lines.append("")
            lines.append(
                "提示：该名称取自注册表键名，可能与实际右键菜单文字不同（部分功能的文字由 DLL 运行时生成）。"
                "可点击「设置别名…」起一个能认出的名字。"
            )
        self._show_text("功能详情", "\n".join(lines))

    def _show_text(self, title: str, content: str) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.geometry("720x480")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        frame = ttk.Frame(dialog, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(frame, wrap="word", font=("Consolas", 9))
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        ttk.Button(dialog, text="关闭", command=dialog.destroy).grid(row=1, column=0, pady=(0, 10))
        dialog.grab_set()
        self.root.wait_window(dialog)

    def _info(self, message: str, title: str = "提示") -> None:
        messagebox.showinfo(title, message, parent=self.root)

    def _error(self, message: str) -> None:
        messagebox.showerror("出错了", message, parent=self.root)

    # ---- 生命周期 ----

    def run(self) -> None:
        self.root.mainloop()