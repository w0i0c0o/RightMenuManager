"""贯穿全流程的安全不变式：

1. 任何代码路径都不删除注册表键；
2. 只增删值，不动菜单项自身的注册信息；
3. 权限不足时整体中止，不留部分改动。
"""

import unittest

from rightmenu.__main__ import to_dict
from rightmenu.actions import disable, enable, plan, apply
from rightmenu.fake_registry import FakeRegistry
from rightmenu.journal import Journal
from rightmenu.model import Kind, Scope
from rightmenu.registry import REG_SZ
from rightmenu.scanner import blocked_key_path, scan

CLASSES = r"HKCU\Software\Classes"
HKLM_CLASSES = r"HKLM\SOFTWARE\Classes"
BLOCKED_USER = blocked_key_path(Scope.USER)
OTHER_GUID = "{99999999-9999-9999-9999-999999999999}"
GUID = "{11111111-1111-1111-1111-111111111111}"


def build_registry(readonly: tuple[str, ...] = ()) -> FakeRegistry:
    return FakeRegistry(
        initial={
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ), "Icon": ("demo.exe,0", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
            CLASSES + r"\*\shellex\ContextMenuHandlers\DemoShell": {"": (GUID, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID + r"\InprocServer32": {"": (r"C:\demo.dll", REG_SZ)},
            BLOCKED_USER: {OTHER_GUID: ("", REG_SZ)},
            HKLM_CLASSES + r"\*\shell\MachineApp": {"": ("机器项", REG_SZ)},
            HKLM_CLASSES + r"\*\shell\MachineApp\command": {"": ("machine.exe", REG_SZ)},
        },
        readonly_prefixes=readonly,
    )


def item_named(reg, name, scope=Scope.MACHINE):
    for item in scan(reg, scope):
        if item.key_name == name:
            return item
    raise AssertionError(f"未找到菜单项: {name}")


class TestNeverDeletesKeys(unittest.TestCase):
    def test_full_pipeline_never_deletes_keys(self):
        import tempfile
        from pathlib import Path

        reg = build_registry()
        with tempfile.TemporaryDirectory() as tmp:
            journal = Journal(Path(tmp) / "journal.json")
            scan(reg, Scope.MACHINE)
            disable(reg, [item_named(reg, "DemoApp")], journal)
            disable(reg, [item_named(reg, "DemoShell")], journal)
            enable(reg, [item_named(reg, "DemoApp")], journal)
            journal.restore_all(reg)
            self.assertEqual(reg.delete_key_calls, 0)

    def test_disable_only_adds_keys_never_removes(self):
        reg = build_registry()
        before = reg.keys()
        disable(reg, [item_named(reg, "DemoApp")])
        self.assertTrue(before.issubset(reg.keys()))


class TestForeignRegistrationsUntouched(unittest.TestCase):
    def test_verb_key_values_are_preserved(self):
        reg = build_registry()
        item = item_named(reg, "DemoApp")
        before = {name: reg.read_value(item.key_path, name) for name in ("", "Icon", "MUIVerb")}

        disable(reg, [item])

        after = {name: reg.read_value(item.key_path, name) for name in ("", "Icon", "MUIVerb")}
        self.assertEqual(after, before)

    def test_shellex_registration_is_preserved(self):
        reg = build_registry()
        item = item_named(reg, "DemoShell")
        disable(reg, [item])
        self.assertEqual(reg.read_value(item.key_path, None), (GUID, REG_SZ))

    def test_other_blocked_entries_are_preserved(self):
        reg = build_registry()
        disable(reg, [item_named(reg, "DemoShell")])
        self.assertEqual(reg.read_value(BLOCKED_USER, OTHER_GUID), ("", REG_SZ))


class TestPermissionAtomicity(unittest.TestCase):
    def test_machine_scope_without_permission_writes_nothing(self):
        reg = build_registry(readonly=(r"HKLM",))
        before = reg.snapshot()
        changes = plan([item_named(reg, "MachineApp")], True).changes
        with self.assertRaises(PermissionError):
            apply(reg, changes)
        self.assertEqual(reg.snapshot(), before)

    def test_mixed_batch_aborts_entirely_when_one_target_unwritable(self):
        reg = build_registry(readonly=(r"HKLM",))
        before = reg.snapshot()
        items = [item_named(reg, "DemoApp"), item_named(reg, "MachineApp")]
        changes = plan(items, True).changes
        self.assertEqual(len(changes), 2)

        with self.assertRaises(PermissionError):
            apply(reg, changes)
        self.assertEqual(reg.snapshot(), before)


class TestCliSerialization(unittest.TestCase):
    def test_to_dict_serializes_enums_and_derived_fields(self):
        reg = build_registry()
        item = item_named(reg, "DemoShell")
        data = to_dict(item)

        self.assertEqual(data["kind"], Kind.SHELLEX.value)
        self.assertEqual(data["scope"], Scope.USER.value)
        self.assertEqual(data["clsid"], GUID)
        self.assertFalse(data["needs_admin"])
        self.assertEqual(data["id"], item.id)

    def test_to_dict_is_json_friendly(self):
        import json

        reg = build_registry()
        payload = [to_dict(i) for i in scan(reg, Scope.MACHINE)]
        self.assertEqual(len(json.loads(json.dumps(payload, ensure_ascii=False))), len(payload))


if __name__ == "__main__":
    unittest.main()