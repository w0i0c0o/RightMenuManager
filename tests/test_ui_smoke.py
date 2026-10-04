"""界面冒烟测试：用 FakeRegistry 构造真实 tkinter 窗口并驱动一次完整流程。

不打开模态对话框 —— 直接调用 apply_changes / restore_all，
以覆盖 T9（构建与刷新）、T10（禁用→应用→恢复）、T11（权限提示）的验收点。
"""

import tempfile
import unittest
from pathlib import Path

from rightmenu.fake_registry import FakeRegistry
from rightmenu.journal import Journal
from rightmenu.model import Scope
from rightmenu.registry import REG_SZ

try:
    import tkinter as tk
    from rightmenu.ui.app import App
except ImportError:  # 默认解释器可能不带 tkinter；本模块整体跳过
    tk = None
    App = None

TKINTER_MISSING = tk is None

CLASSES = r"HKCU\Software\Classes"
HKLM_CLASSES = r"HKLM\SOFTWARE\Classes"
GUID = "{11111111-1111-1111-1111-111111111111}"


def build_registry() -> FakeRegistry:
    return FakeRegistry(
        initial={
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
            CLASSES + r"\*\shellex\ContextMenuHandlers\DemoShell": {"": (GUID, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID + r"\InprocServer32": {"": (r"C:\demo.dll", REG_SZ)},
            HKLM_CLASSES + r"\*\shell\MachineApp": {"": ("机器项", REG_SZ)},
        }
    )


def build_duplicate_registry() -> FakeRegistry:
    """同一功能「上传到百度网盘」在「所有文件」和「.docx 文件」各注册一份。"""
    return FakeRegistry(
        initial={
            CLASSES + r"\*\shell\BaiduAll": {"": ("上传到百度网盘", REG_SZ)},
            CLASSES + r"\*\shell\BaiduAll\command": {"": ("baidu.exe %1", REG_SZ)},
            CLASSES + r"\.docx\shell\BaiduDocx": {"": ("上传到百度网盘", REG_SZ)},
            CLASSES + r"\.docx\shell\BaiduDocx\command": {"": ("baidu.exe %1", REG_SZ)},
        }
    )


def build_mixed_registry() -> FakeRegistry:
    """一个 Windows 自带项（裸 shell32.dll 引用）+ 一个第三方项（完整路径）。"""
    return FakeRegistry(
        initial={
            CLASSES + r"\Folder\shell\pintohome": {"MUIVerb": ("@shell32.dll,-51601", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
        }
    )


def assert_no_residue(test, reg, before):
    after = reg.snapshot()
    for path, values in before.items():
        test.assertEqual(after.get(path), values, f"原有键未还原: {path}")
    for path, values in after.items():
        if path not in before:
            test.assertEqual(values, {}, f"恢复后残留了值: {path}")


class AppSmokeCase(unittest.TestCase):
    def setUp(self):
        if TKINTER_MISSING:
            self.skipTest("当前解释器没有 tkinter")
        self._tmp = tempfile.TemporaryDirectory()
        self.reg = build_registry()
        self.journal = Journal(Path(self._tmp.name) / "journal.json")
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # 无显示环境（如无头 CI）时跳过
            self.skipTest(f"无可用显示环境: {exc}")
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self._tmp.cleanup()

    def app(self, scope=Scope.USER, admin=False) -> App:
        app = App(self.reg, self.journal, scope=scope, admin=admin, root=self.root)
        self.root.update()
        return app

    def app_with(self, reg, scope=Scope.USER, admin=False) -> App:
        app = App(
            reg,
            Journal(Path(self._tmp.name) / "journal2.json"),
            scope=scope,
            admin=admin,
            root=self.root,
        )
        self.root.update()
        return app

    def item(self, app, name):
        for item in app.controller.items:
            if item.key_name == name:
                return item
        raise AssertionError(f"未找到菜单项: {name}")


class TestAppBuild(AppSmokeCase):
    def test_builds_and_refreshes_without_error(self):
        app = self.app()
        self.root.update()
        self.assertTrue(app.tree.get_children())

    def test_search_filters_rows(self):
        app = self.app()
        app._query.set("DemoApp")
        self.root.update()
        self.assertEqual(len(app.tree.get_children()), 1)


class TestAppDisableRestore(AppSmokeCase):
    def test_disable_then_restore_returns_to_initial(self):
        app = self.app()
        before = self.reg.snapshot()
        target = self.item(app, "DemoApp")

        plan = app.preview_disable([target])
        self.assertEqual(len(plan.changes), 1)
        result = app.apply_changes(plan.changes)
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertTrue(self.item(app, "DemoApp").disabled)

        restored = app.restore_all()
        self.assertIsNotNone(restored)
        self.assertTrue(restored.ok)
        assert_no_residue(self, self.reg, before)


class TestAppPermissionHint(AppSmokeCase):
    def test_machine_scope_without_admin_disables_writes_and_shows_hint(self):
        app = self.app(scope=Scope.MACHINE, admin=False)
        app.tree.selection_set(app.tree.get_children()[0])
        self.root.update()

        self.assertTrue(app._btn_disable.instate(["disabled"]))
        self.assertTrue(app._btn_enable.instate(["disabled"]))
        self.assertTrue(app._btn_restore.instate(["disabled"]))
        self.assertTrue(app._hint.cget("text"))
        self.assertEqual(app._btn_elevate.winfo_manager(), "pack")

    def test_user_scope_keeps_writes_enabled(self):
        app = self.app(scope=Scope.USER, admin=False)
        app.tree.selection_set(app.tree.get_children()[0])
        self.root.update()
        self.assertFalse(app._btn_disable.instate(["disabled"]))
        self.assertEqual(app._btn_elevate.winfo_manager(), "")


class TestAppGrouping(AppSmokeCase):
    def test_top_level_rows_are_function_groups(self):
        app = self.app_with(build_duplicate_registry())
        tops = app.tree.get_children()
        self.assertEqual(len(tops), 1)
        self.assertIn(tops[0], app._group_by_iid)

    def test_group_expands_to_per_entry_rows(self):
        app = self.app_with(build_duplicate_registry())
        group_iid = app.tree.get_children()[0]
        children = app.tree.get_children(group_iid)
        self.assertEqual(len(children), 2)
        self.assertTrue(all(c in app._item_by_iid for c in children))

    def test_selecting_group_disables_all_instances(self):
        app = self.app_with(build_duplicate_registry())
        app.tree.selection_set(app.tree.get_children()[0])
        self.root.update()
        items = app.selected_items()
        self.assertEqual(len(items), 2)

        plan = app.preview_disable(items)
        self.assertEqual(len(plan.changes), 2)
        result = app.apply_changes(plan.changes)
        self.assertTrue(result.ok)
        self.assertEqual(app.controller.disabled_count(), 2)
        self.assertEqual(app._group_by_iid[app.tree.get_children()[0]].state, "disabled")

    def test_search_filters_to_matching_group_and_expands_it(self):
        app = self.app_with(build_duplicate_registry())
        app._query.set("baidu.exe")
        self.root.update()
        tops = app.tree.get_children()
        self.assertEqual(len(tops), 1)
        self.assertTrue(app.tree.item(tops[0], "open"))

    def test_alias_button_enabled_only_for_single_group_row(self):
        app = self.app_with(build_duplicate_registry())
        group_iid = app.tree.get_children()[0]
        app.tree.selection_set(group_iid)
        self.root.update()
        self.assertFalse(app._btn_alias.instate(["disabled"]))

        child = app.tree.get_children(group_iid)[0]
        app.tree.selection_set(child)
        self.root.update()
        self.assertTrue(app._btn_alias.instate(["disabled"]))


class TestAppHideSystem(AppSmokeCase):
    def test_checkbox_hides_windows_items_and_reports_count(self):
        app = self.app_with(build_mixed_registry())
        self.assertEqual(len(app.tree.get_children()), 2)

        app._hide_system.set(True)
        app.reload()
        self.root.update()

        tops = app.tree.get_children()
        self.assertEqual(len(tops), 1)
        self.assertEqual(app._group_by_iid[tops[0]].label, "Demo 应用")
        self.assertIn("已隐藏 1 项", app._status.get())

    def test_unchecking_restores_all_rows(self):
        app = self.app_with(build_mixed_registry())
        app._hide_system.set(True)
        app.reload()
        app._hide_system.set(False)
        app.reload()
        self.root.update()
        self.assertEqual(len(app.tree.get_children()), 2)


if __name__ == "__main__":
    unittest.main()