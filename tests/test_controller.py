import tempfile
import unittest
from pathlib import Path

from rightmenu.actions import PlanResult
from rightmenu.fake_registry import FakeRegistry
from rightmenu.journal import Journal
from rightmenu.model import Scope
from rightmenu.registry import REG_SZ
from rightmenu.ui.controller import Controller, build_preview_text

CLASSES = r"HKCU\Software\Classes"
HKLM_CLASSES = r"HKLM\SOFTWARE\Classes"
GUID = "{11111111-1111-1111-1111-111111111111}"


def build_registry(readonly: tuple[str, ...] = ()) -> FakeRegistry:
    return FakeRegistry(
        initial={
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
            CLASSES + r"\*\shell\MediaInfo": {"": ("MediaInfo", REG_SZ)},
            CLASSES + r"\*\shell\MediaInfo\command": {"": (r"D:\MediaInfo\MediaInfo.exe %1", REG_SZ)},
            CLASSES + r"\*\shellex\ContextMenuHandlers\DemoShell": {"": (GUID, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID + r"\InprocServer32": {"": (r"C:\demo.dll", REG_SZ)},
            HKLM_CLASSES + r"\*\shell\MachineApp": {"": ("机器项", REG_SZ)},
            HKLM_CLASSES + r"\*\shell\MachineApp\command": {"": ("machine.exe", REG_SZ)},
        },
        readonly_prefixes=readonly,
    )


def assert_no_residue(test, reg, before):
    """恢复后：原有键的值逐一还原；新增的键只允许是空键（本工具永不删键）。"""
    after = reg.snapshot()
    for path, values in before.items():
        test.assertEqual(after.get(path), values, f"原有键未还原: {path}")
    for path, values in after.items():
        if path not in before:
            test.assertEqual(values, {}, f"恢复后残留了值: {path}")


class ControllerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.reg = build_registry()
        self.journal = Journal(Path(self._tmp.name) / "journal.json")

    def tearDown(self):
        self._tmp.cleanup()

    def controller(self, scope=Scope.USER, admin=False) -> Controller:
        return Controller(self.reg, self.journal, scope=scope, admin=admin)

    def item(self, controller, name):
        for item in controller.items:
            if item.key_name == name:
                return item
        raise AssertionError(f"未找到菜单项: {name}")


class TestListing(ControllerTestCase):
    def test_refresh_loads_items(self):
        controller = self.controller()
        names = [i.key_name for i in controller.items]
        self.assertIn("DemoApp", names)
        self.assertIn("DemoShell", names)

    def test_items_is_a_copy(self):
        controller = self.controller()
        controller.items.clear()
        self.assertTrue(controller.items)

    def test_disabled_count(self):
        controller = self.controller()
        self.assertEqual(controller.disabled_count(), 0)
        controller.disable([self.item(controller, "DemoApp")])
        self.assertEqual(controller.disabled_count(), 1)


class TestScopeSwitching(ControllerTestCase):
    def test_user_scope_has_no_machine_items(self):
        controller = self.controller(Scope.USER)
        self.assertNotIn("MachineApp", [i.key_name for i in controller.items])

    def test_machine_scope_includes_machine_items(self):
        controller = self.controller(Scope.MACHINE, admin=True)
        self.assertIn("MachineApp", [i.key_name for i in controller.items])

    def test_set_scope_reloads_items(self):
        controller = self.controller(Scope.USER)
        controller.set_scope(Scope.MACHINE)
        self.assertEqual(controller.scope, Scope.MACHINE)
        self.assertIn("MachineApp", [i.key_name for i in controller.items])


class TestWritePermission(ControllerTestCase):
    def test_user_scope_is_always_writable(self):
        self.assertTrue(self.controller(Scope.USER, admin=False).can_write())

    def test_machine_scope_requires_admin(self):
        self.assertFalse(self.controller(Scope.MACHINE, admin=False).can_write())
        self.assertTrue(self.controller(Scope.MACHINE, admin=True).can_write())


class TestFiltering(ControllerTestCase):
    def setUp(self):
        super().setUp()
        self.controller_ = self.controller()

    def test_empty_query_returns_all(self):
        self.assertEqual(len(self.controller_.filter("")), len(self.controller_.items))

    def test_matches_display_name(self):
        found = [i.key_name for i in self.controller_.filter("Demo 应用")]
        self.assertEqual(found, ["DemoApp"])

    def test_matches_location(self):
        names = [i.key_name for i in self.controller_.filter("所有文件")]
        self.assertIn("MediaInfo", names)

    def test_matches_command(self):
        found = [i.key_name for i in self.controller_.filter("MediaInfo.exe")]
        self.assertEqual(found, ["MediaInfo"])

    def test_matches_dll_path(self):
        found = [i.key_name for i in self.controller_.filter("demo.dll")]
        self.assertEqual(found, ["DemoShell"])

    def test_is_case_insensitive(self):
        self.assertEqual(
            [i.key_name for i in self.controller_.filter("demoapp")],
            [i.key_name for i in self.controller_.filter("DEMOAPP")],
        )

    def test_no_match_returns_empty(self):
        self.assertEqual(self.controller_.filter("绝不存在的关键词"), [])


class TestDisableEnableFlow(ControllerTestCase):
    def test_plan_disable_produces_changes_without_touching_registry(self):
        controller = self.controller()
        before = self.reg.snapshot()
        result = controller.plan_disable([self.item(controller, "DemoApp")])
        self.assertEqual(len(result.changes), 1)
        self.assertEqual(self.reg.snapshot(), before)

    def test_commit_disable_then_enable_restores_state(self):
        controller = self.controller()
        before = self.reg.snapshot()
        item = self.item(controller, "DemoApp")

        controller.commit(controller.plan_disable([item]).changes)
        self.assertTrue(self.item(controller, "DemoApp").disabled)

        controller.commit(controller.plan_enable([self.item(controller, "DemoApp")]).changes)
        self.assertFalse(self.item(controller, "DemoApp").disabled)
        self.assertEqual(self.reg.snapshot(), before)

    def test_restore_all_returns_to_original_state(self):
        controller = self.controller()
        before = self.reg.snapshot()
        controller.disable([self.item(controller, "DemoApp"), self.item(controller, "DemoShell")])
        self.assertNotEqual(self.reg.snapshot(), before)

        result = controller.restore_all()
        self.assertTrue(result.ok)
        assert_no_residue(self, self.reg, before)

    def test_journal_is_used_for_restore(self):
        controller = self.controller()
        controller.disable([self.item(controller, "DemoApp")])
        self.assertEqual(len(self.journal.entries), 1)


class TestPreviewText(ControllerTestCase):
    def test_lists_change_path_and_value_name(self):
        controller = self.controller()
        item = self.item(controller, "DemoApp")
        text = build_preview_text(controller.plan_disable([item]))
        self.assertIn(item.key_path, text)
        self.assertIn("LegacyDisable", text)
        self.assertIn("写入", text)

    def test_says_keys_are_never_deleted(self):
        self.assertIn("不删键", build_preview_text(PlanResult()))

    def test_handles_empty_plan(self):
        self.assertIn("没有需要变更的项", build_preview_text(PlanResult()))

    def test_reports_skipped_items_with_reason(self):
        controller = self.controller()
        item = self.item(controller, "DemoApp")
        text = build_preview_text(PlanResult(skipped=[(item, "无法解析 CLSID")]))
        self.assertIn("无法解析 CLSID", text)
        self.assertIn("已跳过", text)


def build_duplicate_registry() -> FakeRegistry:
    """同一功能「上传到百度网盘」在两个位置各注册一份。"""
    return FakeRegistry(
        initial={
            CLASSES + r"\*\shell\BaiduAll": {"": ("上传到百度网盘", REG_SZ)},
            CLASSES + r"\*\shell\BaiduAll\command": {"": ("baidu.exe %1", REG_SZ)},
            CLASSES + r"\.docx\shell\BaiduDocx": {"": ("上传到百度网盘", REG_SZ)},
            CLASSES + r"\.docx\shell\BaiduDocx\command": {"": ("baidu.exe %1", REG_SZ)},
            CLASSES + r"\*\shell\Other": {"": ("其他功能", REG_SZ)},
            CLASSES + r"\*\shell\Other\command": {"": ("other.exe", REG_SZ)},
        }
    )


class TestGrouping(ControllerTestCase):
    def setUp(self):
        super().setUp()
        self.reg = build_duplicate_registry()
        self.controller_ = Controller(self.reg, self.journal, scope=Scope.USER, admin=False)

    def group(self, label):
        for group in self.controller_.groups():
            if group.label == label:
                return group
        raise AssertionError(f"未找到功能组: {label}")

    def test_merges_same_function_across_locations(self):
        baidu = self.group("上传到百度网盘")
        self.assertEqual(baidu.total, 2)
        self.assertEqual(len(self.controller_.groups()), 2)

    def test_disable_whole_group_disables_every_instance(self):
        baidu = self.group("上传到百度网盘")
        result = self.controller_.disable(list(baidu.items))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.applied), 2)
        self.assertEqual(self.group("上传到百度网盘").state, "disabled")

    def test_filter_groups_matches_member_only_keeps_matching_instances(self):
        groups = self.controller_.filter_groups(".docx")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].label, "上传到百度网盘")
        self.assertEqual(groups[0].total, 1)
        self.assertIn(".docx", groups[0].items[0].location)

    def test_filter_groups_matches_command_across_instances(self):
        groups = self.controller_.filter_groups("baidu.exe")
        self.assertEqual(groups[0].total, 2)

    def test_alias_changes_label_and_is_searchable(self):
        key = self.group("上传到百度网盘").key
        self.controller_.set_alias(key, "百度网盘上传")
        self.assertEqual(self.group("百度网盘上传").raw_name, "上传到百度网盘")
        self.assertEqual([g.label for g in self.controller_.filter_groups("百度网盘上传")], ["百度网盘上传"])

    def test_clear_alias_restores_raw_name(self):
        key = self.group("上传到百度网盘").key
        self.controller_.set_alias(key, "临时名")
        self.controller_.clear_alias(key)
        self.assertEqual(self.group("上传到百度网盘").label, "上传到百度网盘")


def build_mixed_registry() -> FakeRegistry:
    """一个 Windows 自带项（裸 shell32.dll 引用）+ 一个第三方项（完整路径）。"""
    return FakeRegistry(
        initial={
            CLASSES + r"\Folder\shell\pintohome": {"MUIVerb": ("@shell32.dll,-51601", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
        }
    )


class TestHideSystemFilter(ControllerTestCase):
    def setUp(self):
        super().setUp()
        self.reg = build_mixed_registry()
        self.controller_ = Controller(self.reg, self.journal, scope=Scope.USER, admin=False)

    def test_flags_only_the_windows_item(self):
        self.assertTrue(self.item(self.controller_, "pintohome").is_system)
        self.assertFalse(self.item(self.controller_, "DemoApp").is_system)

    def test_default_shows_both(self):
        self.assertEqual(len(self.controller_.filter_groups("")), 2)

    def test_hide_system_drops_windows_item(self):
        groups = self.controller_.filter_groups("", hide_system=True)
        self.assertEqual([g.label for g in groups], ["Demo 应用"])

    def test_hidden_system_count(self):
        self.assertEqual(self.controller_.hidden_system_count(), 1)

    def test_visible_items_respects_hide_system(self):
        self.assertEqual(len(self.controller_.visible_items(hide_system=True)), 1)

    def test_query_and_hide_system_combine(self):
        self.assertEqual(self.controller_.filter_groups("pintohome", hide_system=True), [])


if __name__ == "__main__":
    unittest.main()