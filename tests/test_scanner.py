import os
import unittest
from unittest import mock

from rightmenu.fake_registry import FakeRegistry
from rightmenu.model import DisableMethod, Kind, Scope
from rightmenu.registry import REG_SZ
from rightmenu.resources import resolve_text
from rightmenu.scanner import blocked_key_path, scan

CLASSES = r"HKCU\Software\Classes"
HKLM_CLASSES = r"HKLM\SOFTWARE\Classes"
WOW64 = r"HKLM\SOFTWARE\Classes\Wow6432Node"
BLOCKED_USER = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked"

GUID = "{11111111-1111-1111-1111-111111111111}"
GUID2 = "{22222222-2222-2222-2222-222222222222}"
GUID3 = "{33333333-3333-3333-3333-333333333333}"
GUID4 = "{44444444-4444-4444-4444-444444444444}"

INDIRECT = r"@rightmenutest.dll,-1"


def build_registry() -> FakeRegistry:
    return FakeRegistry(
        initial={
            # --- 用户范围：静态动词 ---
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ), "Icon": ("demo.exe,0", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
            CLASSES + r"\*\shell\ShiftOnly": {"": ("仅Shift", REG_SZ), "Extended": ("", REG_SZ)},
            CLASSES + r"\*\shell\ShiftOnly\command": {"": ("shift.exe", REG_SZ)},
            CLASSES + r"\*\shell\Hidden": {"": ("已禁用项", REG_SZ), "LegacyDisable": ("", REG_SZ)},
            CLASSES + r"\*\shell\Hidden\command": {"": ("hidden.exe", REG_SZ)},
            CLASSES + r"\*\shell\Junk": {},
            CLASSES + r"\*\shell\MuivarbVerb": {"": ("默认文本", REG_SZ), "MUIVerb": ("MUIVerb 文本", REG_SZ)},
            CLASSES + r"\*\shell\MuivarbVerb\command": {"": ("muivarb.exe", REG_SZ)},
            CLASSES + r"\*\shell\IndirectVerb": {"": (INDIRECT, REG_SZ)},
            CLASSES + r"\*\shell\IndirectVerb\command": {"": ("cmd.exe", REG_SZ)},
            CLASSES + r"\Directory\Background\shell\Bg": {"": ("背景项", REG_SZ)},
            CLASSES + r"\Directory\Background\shell\Bg\command": {"": ("bg.exe", REG_SZ)},
            CLASSES + r"\SystemFileAssociations\.txt\shell\TxtVerb": {"": ("文本项", REG_SZ)},
            CLASSES + r"\SystemFileAssociations\.txt\shell\TxtVerb\command": {"": ("txt.exe", REG_SZ)},
            # --- 用户范围：外壳扩展 ---
            CLASSES + r"\*\shellex\ContextMenuHandlers\DemoShell": {"": (GUID, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID: {"": ("Demo 外壳扩展", REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID + r"\InprocServer32": {"": (r"%SystemRoot%\demo.dll", REG_SZ)},
            CLASSES + r"\*\shellex\ContextMenuHandlers\BlockedShell": {"": (GUID2, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID2 + r"\InprocServer32": {"": (r"%SystemRoot%\blocked.dll", REG_SZ)},
            CLASSES + r"\*\shellex\ContextMenuHandlers\IndirectShell": {"": (GUID4, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID4: {"": (INDIRECT, REG_SZ)},
            # GUID 命名、默认值为空的处理器：CLSID 只能从键名推断（系统组件常见形态）
            CLASSES + r"\*\shellex\ContextMenuHandlers" + "\\" + GUID3: {"": ("", REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID3: {"": ("压缩包菜单", REG_SZ)},
            # 少数处理器把可读名称直接写在默认值里
            CLASSES + r"\*\shellex\ContextMenuHandlers\PlainShell": {"": ("直接写入的名称", REG_SZ)},
            BLOCKED_USER: {GUID2: ("", REG_SZ)},
            # --- 机器范围 ---
            HKLM_CLASSES + r"\*\shell\MachineApp": {"": ("机器项", REG_SZ)},
            HKLM_CLASSES + r"\*\shell\MachineApp\command": {"": ("machine.exe", REG_SZ)},
            WOW64 + r"\*\shell\Legacy32": {"": ("32位项", REG_SZ)},
            WOW64 + r"\*\shell\Legacy32\command": {"": ("legacy.exe", REG_SZ)},
        }
    )


def find(items, key_name):
    for item in items:
        if item.key_name == key_name:
            return item
    raise AssertionError(f"未找到菜单项: {key_name}；现有: {[i.key_name for i in items]}")


class TestStaticVerbScan(unittest.TestCase):
    def setUp(self):
        self.reg = build_registry()
        self.items = scan(self.reg, Scope.USER)

    def test_fields(self):
        item = find(self.items, "DemoApp")
        self.assertEqual(item.kind, Kind.STATIC)
        self.assertEqual(item.scope, Scope.USER)
        self.assertEqual(item.display_name, "Demo 应用")
        self.assertEqual(item.command, r"C:\demo.exe %1")
        self.assertEqual(item.location, "所有文件")
        self.assertFalse(item.disabled)
        self.assertIsNone(item.method)
        self.assertFalse(item.extended)
        self.assertFalse(item.needs_admin)

    def test_extended_flag_detected(self):
        self.assertTrue(find(self.items, "ShiftOnly").extended)

    def test_legacy_disable_detected(self):
        item = find(self.items, "Hidden")
        self.assertTrue(item.disabled)
        self.assertEqual(item.method, DisableMethod.LEGACY_DISABLE)

    def test_junk_entry_without_visible_info_is_skipped(self):
        self.assertNotIn("Junk", [i.key_name for i in self.items])

    def test_other_values_on_verb_key_are_left_alone(self):
        item = find(self.items, "DemoApp")
        self.assertEqual(self.reg.read_value(item.key_path, "Icon"), ("demo.exe,0", REG_SZ))

    def test_location_labels(self):
        self.assertEqual(find(self.items, "Bg").location, "目录背景")
        self.assertIn(".txt", find(self.items, "TxtVerb").location)


class TestShellExScan(unittest.TestCase):
    def setUp(self):
        self.reg = build_registry()
        self.items = scan(self.reg, Scope.USER)

    def test_fields_and_clsid_resolution(self):
        item = find(self.items, "DemoShell")
        self.assertEqual(item.kind, Kind.SHELLEX)
        self.assertEqual(item.clsid, GUID)
        self.assertEqual(item.dll_path, os.path.expandvars(r"%SystemRoot%\demo.dll"))
        self.assertEqual(item.display_name, "Demo 外壳扩展")
        self.assertFalse(item.disabled)

    def test_blocked_list_detected(self):
        item = find(self.items, "BlockedShell")
        self.assertTrue(item.disabled)
        self.assertEqual(item.method, DisableMethod.BLOCKED)

    def test_unresolvable_display_name_falls_back_to_key_name(self):
        self.assertEqual(find(self.items, "BlockedShell").display_name, "BlockedShell")

    def test_blocked_key_path_by_scope(self):
        self.assertEqual(blocked_key_path(Scope.USER), BLOCKED_USER)
        self.assertIn(r"HKLM\SOFTWARE", blocked_key_path(Scope.MACHINE))


class TestScopeHandling(unittest.TestCase):
    def setUp(self):
        self.reg = build_registry()

    def test_user_scope_excludes_machine_items(self):
        names = [i.key_name for i in scan(self.reg, Scope.USER)]
        self.assertNotIn("MachineApp", names)
        self.assertNotIn("Legacy32", names)

    def test_machine_scope_includes_machine_and_wow64_items(self):
        items = scan(self.reg, Scope.MACHINE)
        machine = find(items, "MachineApp")
        self.assertEqual(machine.scope, Scope.MACHINE)
        self.assertTrue(machine.needs_admin)
        self.assertEqual(find(items, "Legacy32").scope, Scope.MACHINE)

    def test_machine_scope_still_includes_user_items(self):
        names = [i.key_name for i in scan(self.reg, Scope.MACHINE)]
        self.assertIn("DemoApp", names)


class TestDisplayNameResolution(unittest.TestCase):
    def setUp(self):
        self.reg = build_registry()

    def test_static_verb_muivarb_takes_priority_over_default(self):
        items = scan(self.reg, Scope.USER)
        self.assertEqual(find(items, "MuivarbVerb").display_name, "MUIVerb 文本")

    def test_static_verb_indirect_string_is_resolved(self):
        loader = lambda source: {INDIRECT: "在此处打开命令窗口(&W)"}.get(source)
        items = scan(self.reg, Scope.USER, loader=loader)
        self.assertEqual(find(items, "IndirectVerb").display_name, "在此处打开命令窗口(W)")

    def test_static_verb_unresolved_indirect_falls_back_to_key_name(self):
        items = scan(self.reg, Scope.USER, loader=lambda source: None)
        self.assertEqual(find(items, "IndirectVerb").display_name, "IndirectVerb")

    def test_shellex_guid_named_handler_derives_clsid_from_key_name(self):
        items = scan(self.reg, Scope.USER)
        item = find(items, GUID3)
        self.assertEqual(item.clsid, GUID3)
        self.assertEqual(item.display_name, "压缩包菜单")

    def test_shellex_handler_with_readable_default_value(self):
        items = scan(self.reg, Scope.USER)
        self.assertEqual(find(items, "PlainShell").display_name, "直接写入的名称")

    def test_shellex_clsid_indirect_string_is_resolved(self):
        loader = lambda source: {INDIRECT: "压缩包菜单"}.get(source)
        items = scan(self.reg, Scope.USER, loader=loader)
        self.assertEqual(find(items, "IndirectShell").display_name, "压缩包菜单")

    def test_shellex_clsid_indirect_string_unresolved_falls_back_to_key_name(self):
        items = scan(self.reg, Scope.USER, loader=lambda source: None)
        self.assertEqual(find(items, "IndirectShell").display_name, "IndirectShell")


class TestNameFallbackFlag(unittest.TestCase):
    """标记「名称只是回退到键名」的项，供界面提示用户设置别名。"""

    def setUp(self):
        self.reg = build_registry()

    def test_static_resolved_name_is_not_fallback(self):
        items = scan(self.reg, Scope.USER)
        self.assertFalse(find(items, "DemoApp").name_is_fallback)

    def test_static_unresolved_indirect_is_fallback(self):
        items = scan(self.reg, Scope.USER, loader=lambda source: None)
        self.assertTrue(find(items, "IndirectVerb").name_is_fallback)

    def test_shellex_with_friendly_name_is_not_fallback(self):
        items = scan(self.reg, Scope.USER)
        self.assertFalse(find(items, "DemoShell").name_is_fallback)

    def test_shellex_readable_default_is_not_fallback(self):
        items = scan(self.reg, Scope.USER)
        self.assertFalse(find(items, "PlainShell").name_is_fallback)

    def test_shellex_without_readable_name_is_fallback(self):
        items = scan(self.reg, Scope.USER)
        self.assertTrue(find(items, "BlockedShell").name_is_fallback)


class TestScanIsReadOnly(unittest.TestCase):
    def test_scan_does_not_mutate_registry(self):
        reg = build_registry()
        before = reg.snapshot()
        scan(reg, Scope.MACHINE)
        self.assertEqual(reg.snapshot(), before)

    def test_scan_never_deletes_keys(self):
        reg = build_registry()
        scan(reg, Scope.MACHINE)
        self.assertEqual(reg.delete_key_calls, 0)


if __name__ == "__main__":
    unittest.main()