"""tkinter 视图。

只负责画界面与收集用户操作；所有判断逻辑都在 ui/controller.py。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from rightmenu.elevation import relaunch_as_admin
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
COLUMNS = (
    ("state", "状态", 80),
    ("name", "名称", 260),
    ("location", "位置", 160),
    ("kind", "类型", 100),
    ("detail", "命令 / DLL", 460),
)


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
        self.root.geometry("1120x660")
        self.root.minsize(900, 480)

        self._query = tk.StringVar()
        self._scope_var = tk.StringVar(value=self.controller.scope.value)
        self._status = tk.StringVar()
        self._by_id: dict[str, ContextMenuItem] = {}

        self._build()
        self.reload()

    # ---- 界面构建 ----

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(3, weight=1)

        ttk.Label(toolbar, text="范围：").grid(row=0, column=0, padx=(0, 4))
        for index, scope in enumerate((Scope.USER, Scope.MACHINE), start=1):
            ttk.Radiobutton(
                toolbar,
                text=SCOPE_LABELS[scope],
                value=scope.value,
                variable=self._scope_var,
                command=self._on_scope_change,
            ).grid(row=0, column=index, padx=(0, 12), sticky="w")

        search_box = ttk.Frame(toolbar)
        search_box.grid(row=0, column=3, sticky="e")
        ttk.Label(search_box, text="搜索：").pack(side="left")
        ttk.Entry(search_box, textvariable=self._query, width=26).pack(side="left")
        self._query.trace_add("write", lambda *_: self.reload())

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        actions.grid(row=2, column=0, sticky="ew")

        self._btn_disable = ttk.Button(actions, text="禁用选中项", command=self._run_disable)
        self._btn_disable.pack(side="left")
        self._btn_enable = ttk.Button(actions, text="恢复选中项", command=self._run_enable)
        self._btn_enable.pack(side="left", padx=6)
        self._btn_restore = ttk.Button(actions, text="一键恢复全部改动", command=self._run_restore)
        self._btn_restore.pack(side="left", padx=(18, 6))
        ttk.Button(actions, text="刷新", command=self.reload).pack(side="left")

        self._hint = ttk.Label(actions, text="", foreground="#b34700")
        self._hint.pack(side="left", padx=16)
        self._btn_elevate = ttk.Button(actions, text="以管理员身份重启", command=self.elevate)

        table = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        table.grid(row=1, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table, columns=[c[0] for c in COLUMNS], show="headings", selectmode="extended"
        )
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w", stretch=(key == "detail"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("disabled", foreground="#8a8a8a")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_action_state())
        self.tree.bind("<Double-1>", self._show_details)

        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        ttk.Label(self.root, textvariable=self._status, padding=(12, 4)).grid(
            row=3, column=0, sticky="ew"
        )

    # ---- 数据刷新 ----

    def reload(self) -> None:
        query = self._query.get()
        visible = self.controller.filter(query)
        self._by_id = {item.id: item for item in visible}

        self.tree.delete(*self.tree.get_children())
        for item in visible:
            self.tree.insert(
                "",
                "end",
                iid=item.id,
                values=(
                    "已禁用" if item.disabled else "启用中",
                    item.display_name,
                    item.location,
                    KIND_LABELS[item.kind],
                    item.command or item.dll_path or "",
                ),
                tags=("disabled",) if item.disabled else (),
            )
        self._update_action_state()
        self._update_status(query, len(visible))

    def _update_status(self, query: str, shown: int) -> None:
        total = len(self.controller.items)
        disabled = self.controller.disabled_count()
        scope_text = "仅当前用户" if self.controller.scope is Scope.USER else "全机器"
        parts = [f"范围：{scope_text}", f"共 {total} 项", f"已禁用 {disabled} 项"]
        parts.append(f"筛选出 {shown} 项" if query.strip() else f"显示 {shown} 项")
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

    # ---- 操作 ----

    def selected_items(self) -> list[ContextMenuItem]:
        return [self._by_id[iid] for iid in self.tree.selection() if iid in self._by_id]

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

    def _show_details(self, _event) -> None:
        items = self.selected_items()
        if not items:
            return
        item = items[0]
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
        self._info("\n".join(lines), title="菜单项详情")

    def _info(self, message: str, title: str = "提示") -> None:
        messagebox.showinfo(title, message, parent=self.root)

    def _error(self, message: str) -> None:
        messagebox.showerror("出错了", message, parent=self.root)

    # ---- 生命周期 ----

    def run(self) -> None:
        self.root.mainloop()