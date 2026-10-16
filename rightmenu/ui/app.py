"""tkinter 视图。

只负责画界面与收集用户操作；所有判断逻辑都在 ui/controller.py。
界面文案一律经 :func:`rightmenu.i18n.t` 取词，切换语言时整窗重建。

列表按「功能」归并成两层：

- 顶层一行 = 一个右键功能（如「上传到百度网盘」），选中它即可一次性
  关闭/显示该功能在所有文件类型下的全部条目；
- 展开后是逐项明细，可精确定位到某个文件类型/位置单独开关。

这样既满足「跨文件类型的一键消除」，也保留了原来的分文件类型控制。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from rightmenu import i18n
from rightmenu.elevation import relaunch_as_admin
from rightmenu.grouping import MenuGroup
from rightmenu.i18n import t
from rightmenu.journal import Journal
from rightmenu.model import ContextMenuItem, Kind, Scope
from rightmenu.registry import Win32Registry
from rightmenu.ui.controller import Controller, build_preview_text

#: 列标识与固定宽度（标题随语言变化，宽度不变）。
COLUMNS = (
    ("state", 90),
    ("location", 160),
    ("kind", 110),
    ("detail", 400),
)
TREE_COLUMN = "#0"


def kind_label(kind: Kind) -> str:
    return t(f"kind.{kind.value}")


def state_label(state: str) -> str:
    return t(f"state.{state}")


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
        self.root.title(t("app.title"))
        self.root.geometry("1180x680")
        self.root.minsize(960, 500)

        self._query = tk.StringVar()
        self._scope_var = tk.StringVar(value=self.controller.scope.value)
        self._hide_system = tk.BooleanVar(value=False)
        self._status = tk.StringVar()
        self._lang_label = tk.StringVar()
        self._lang_labels: list[str] = []
        self._lang_code_by_label: dict[str, str] = {}
        self._group_by_iid: dict[str, MenuGroup] = {}
        self._item_by_iid: dict[str, ContextMenuItem] = {}

        self._build()
        # 只注册一次：_rebuild() 会重跑 _build()，在 _build 里注册会随每次切换语言累积回调。
        self._query.trace_add("write", lambda *_: self.reload())
        self.reload()

    # ---- 界面构建 ----

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(4, weight=1)

        ttk.Label(toolbar, text=t("toolbar.scope")).grid(row=0, column=0, padx=(0, 4))
        for index, scope in enumerate((Scope.USER, Scope.MACHINE), start=1):
            ttk.Radiobutton(
                toolbar,
                text=t(f"scope.{scope.value}"),
                value=scope.value,
                variable=self._scope_var,
                command=self._on_scope_change,
            ).grid(row=0, column=index, padx=(0, 12), sticky="w")

        ttk.Checkbutton(
            toolbar,
            text=t("toolbar.hide_system"),
            variable=self._hide_system,
            command=self.reload,
        ).grid(row=0, column=3, padx=(0, 16), sticky="w")

        search_box = ttk.Frame(toolbar)
        search_box.grid(row=0, column=4, sticky="e")
        ttk.Label(search_box, text=t("toolbar.search")).pack(side="left")
        ttk.Entry(search_box, textvariable=self._query, width=28).pack(side="left")

        self._build_language_box(toolbar)

        ttk.Label(
            self.root,
            text=t("banner.grouping"),
            padding=(12, 0, 12, 4),
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w")

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        actions.grid(row=3, column=0, sticky="ew")

        self._btn_disable = ttk.Button(actions, text=t("btn.disable"), command=self._run_disable)
        self._btn_disable.pack(side="left")
        self._btn_enable = ttk.Button(actions, text=t("btn.enable"), command=self._run_enable)
        self._btn_enable.pack(side="left", padx=6)
        self._btn_alias = ttk.Button(actions, text=t("btn.alias"), command=self._run_alias)
        self._btn_alias.pack(side="left", padx=(6, 0))
        self._btn_restore = ttk.Button(actions, text=t("btn.restore"), command=self._run_restore)
        self._btn_restore.pack(side="left", padx=(18, 6))
        ttk.Button(actions, text=t("btn.refresh"), command=self.reload).pack(side="left")
        ttk.Button(actions, text=t("btn.expand_all"), command=self.expand_all).pack(side="left", padx=6)
        ttk.Button(actions, text=t("btn.collapse_all"), command=self.collapse_all).pack(side="left")

        self._hint = ttk.Label(actions, text="", foreground="#b34700")
        self._hint.pack(side="left", padx=16)
        self._btn_elevate = ttk.Button(actions, text=t("btn.elevate"), command=self.elevate)

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
        self.tree.heading(TREE_COLUMN, text=t("col.group"))
        self.tree.column(TREE_COLUMN, width=340, anchor="w", stretch=False)
        for key, width in COLUMNS:
            self.tree.heading(key, text=t(f"col.{key}"))
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

    def _build_language_box(self, toolbar: ttk.Frame) -> None:
        box = ttk.Frame(toolbar)
        box.grid(row=0, column=5, sticky="e", padx=(12, 0))
        ttk.Label(box, text=t("toolbar.language")).pack(side="left")

        codes = i18n.available_languages()
        self._lang_labels = [i18n.language_label(code) for code in codes]
        self._lang_code_by_label = dict(zip(self._lang_labels, codes))
        self._lang_label.set(i18n.language_label(i18n.get_language()))

        combo = ttk.Combobox(
            box,
            state="readonly",
            width=16,
            values=self._lang_labels,
            textvariable=self._lang_label,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._on_language_change)

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
        suffix = t("group.needs_alias_suffix") if group.needs_alias else ""
        return f"{group.label}{suffix}"

    def _group_values(self, group: MenuGroup) -> tuple:
        return (
            state_label(group.state),
            t("group.locations_count", n=len(group.locations)),
            t("group.items_count", n=group.total),
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
            state_label("disabled") if item.disabled else state_label("enabled"),
            item.location,
            kind_label(item.kind),
            item.command or item.dll_path or "",
        )

    def _update_status(self, query: str, groups: list[MenuGroup], hide_system: bool) -> None:
        visible = self.controller.visible_items(query, hide_system)
        scope_key = "scope.user.short" if self.controller.scope is Scope.USER else "scope.machine.short"
        parts = [
            t("status.scope", scope=t(scope_key)),
            t("status.groups", n=len(groups)),
            t("status.items", n=len(visible)),
            t("status.disabled", n=sum(1 for item in visible if item.disabled)),
        ]
        if hide_system:
            parts.append(t("status.hidden_system", n=self.controller.hidden_system_count()))
        if not self.controller.admin:
            parts.append(t("status.not_admin"))
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
            self._hint.configure(text=t("hint.needs_admin"))
            self._btn_elevate.pack(side="left", padx=6)
        else:
            self._hint.configure(text="")
            self._btn_elevate.pack_forget()

    def _on_scope_change(self) -> None:
        self.controller.set_scope(Scope(self._scope_var.get()))
        self.reload()

    def _on_language_change(self, _event=None) -> None:
        code = self._lang_code_by_label.get(self._lang_label.get())
        if not code or code == i18n.get_language():
            return
        i18n.set_language(code)
        self._rebuild()

    def _rebuild(self) -> None:
        """切换语言后整窗重建：文案与位置名都要按新语言重新取词。"""
        for child in self.root.winfo_children():
            child.destroy()
        self._group_by_iid = {}
        self._item_by_iid = {}
        self.controller.refresh()
        self._build()
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
            self._error(t("err.permission", err=exc))
            return None
        self.reload()
        if result.failed:
            self._status.set(
                t("msg.applied_failed", n=len(result.applied), m=len(result.failed))
            )
        else:
            self._status.set(t("msg.applied", n=len(result.applied)))
        return result

    def restore_all(self):
        try:
            result = self.controller.restore_all()
        except PermissionError as exc:
            self._error(t("err.permission", err=exc))
            return None
        self.reload()
        self._status.set(t("msg.restored", n=len(result.applied)))
        return result

    def elevate(self) -> None:
        if relaunch_as_admin():
            self.root.destroy()
        else:
            self._error(t("err.elevate"))

    def _run_disable(self) -> None:
        self._apply_with_preview(self.preview_disable(self.selected_items()))

    def _run_enable(self) -> None:
        self._apply_with_preview(self.preview_enable(self.selected_items()))

    def _apply_with_preview(self, plan) -> None:
        if not plan.changes and not plan.skipped:
            self._info(t("msg.nothing_to_change"))
            return
        if not self.confirm_preview(plan):
            return
        self.apply_changes(plan.changes)

    def _run_restore(self) -> None:
        if not messagebox.askyesno(
            t("dialog.restore.title"), t("dialog.restore.message")
        ):
            return
        self.restore_all()

    def _run_alias(self) -> None:
        groups = self.selected_groups()
        if len(groups) != 1:
            self._info(t("msg.select_group_for_alias"))
            return
        group = groups[0]
        initial = "" if group.needs_alias else group.label
        label = simpledialog.askstring(
            t("dialog.alias.title"),
            t(
                "dialog.alias.prompt",
                name=group.raw_name,
                total=group.total,
                locations=len(group.locations),
            ),
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
        dialog.title(t("dialog.preview.title"))
        dialog.transient(self.root)
        dialog.geometry("760x460")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        ttk.Label(dialog, text=t("dialog.preview.heading"), padding=(12, 10, 12, 4)).grid(
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
        ttk.Button(buttons, text=t("dialog.preview.cancel"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=t("dialog.preview.confirm"), command=accept).pack(side="right", padx=6)

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
        scope = t("scope.user.short") if item.scope is Scope.USER else t("scope.machine.short")
        lines = [
            t("detail.name", v=item.display_name),
            t("detail.location", v=item.location),
            t("detail.kind", v=kind_label(item.kind)),
            t("detail.scope", v=scope),
            t("detail.state", v=state_label("disabled") if item.disabled else state_label("enabled")),
            t("detail.key_path", v=item.key_path),
        ]
        if item.command:
            lines.append(t("detail.command", v=item.command))
        if item.clsid:
            lines.append(t("detail.clsid", v=item.clsid))
        if item.dll_path:
            lines.append(t("detail.dll", v=item.dll_path))
        if item.extended:
            lines.append(t("detail.extended_only"))
        self._show_text(t("dialog.item_detail.title"), "\n".join(lines))

    def _show_group_details(self, group: MenuGroup) -> None:
        separator = t("list.separator")
        scopes = separator.join(
            t("scope.user.short") if s is Scope.USER else t("scope.machine.short") for s in group.scopes
        )
        kinds = separator.join(kind_label(k) for k in group.kinds)
        lines = [
            t("gdetail.name", v=group.label),
            t("gdetail.raw_name", v=group.raw_name),
            t("gdetail.state", v=state_label(group.state)),
            t("gdetail.items", n=group.total),
            t("gdetail.locations", v=separator.join(group.locations)),
            t("gdetail.kinds", v=kinds),
            t("gdetail.scopes", v=scopes),
        ]
        if group.dll_paths:
            lines.append(t("gdetail.dll_header"))
            lines.extend(f"  {path}" for path in group.dll_paths)
        if group.commands:
            lines.append(t("gdetail.command_header"))
            lines.extend(f"  {command}" for command in group.commands)
        lines.append("")
        lines.append(t("gdetail.will_handle", name=group.label, n=group.total))
        for item in group.items:
            lines.append(
                t(
                    "gdetail.item_line",
                    location=item.location,
                    kind=kind_label(item.kind),
                    key_name=item.key_name,
                )
            )
            lines.append(f"      {item.key_path}")
        if group.needs_alias:
            lines.append("")
            lines.append(t("gdetail.needs_alias_hint"))
        self._show_text(t("dialog.group_detail.title"), "\n".join(lines))

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

        ttk.Button(dialog, text=t("dialog.close"), command=dialog.destroy).grid(row=1, column=0, pady=(0, 10))
        dialog.grab_set()
        self.root.wait_window(dialog)

    def _info(self, message: str, title: str | None = None) -> None:
        messagebox.showinfo(title or t("dialog.info.title"), message, parent=self.root)

    def _error(self, message: str) -> None:
        messagebox.showerror(t("dialog.error.title"), message, parent=self.root)

    # ---- 生命周期 ----

    def run(self) -> None:
        self.root.mainloop()