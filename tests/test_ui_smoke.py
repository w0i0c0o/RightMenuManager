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


if __name__ == "__main__":
    unittest.main()