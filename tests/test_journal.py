import json
import tempfile
import unittest
from pathlib import Path

from rightmenu.actions import Action, Change, disable, enable
from rightmenu.fake_registry import FakeRegistry
from rightmenu.journal import Journal, default_journal_path
from rightmenu.model import Scope
from rightmenu.registry import REG_SZ
from rightmenu.scanner import blocked_key_path, scan

CLASSES = r"HKCU\Software\Classes"
BLOCKED_USER = blocked_key_path(Scope.USER)
OTHER_GUID = "{99999999-9999-9999-9999-999999999999}"
GUID = "{11111111-1111-1111-1111-111111111111}"


def build_registry() -> FakeRegistry:
    return FakeRegistry(
        initial={
            CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ)},
            CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
            CLASSES + r"\*\shellex\ContextMenuHandlers\DemoShell": {"": (GUID, REG_SZ)},
            CLASSES + "\\CLSID\\" + GUID + r"\InprocServer32": {"": (r"C:\demo.dll", REG_SZ)},
            BLOCKED_USER: {OTHER_GUID: ("", REG_SZ)},
        }
    )


def item_named(reg, name):
    for item in scan(reg, Scope.USER):
        if item.key_name == name:
            return item
    raise AssertionError(f"未找到菜单项: {name}")


class JournalTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "journal.json"
        self.reg = build_registry()

    def tearDown(self):
        self._tmp.cleanup()

    def journal(self) -> Journal:
        return Journal(self.path)


class TestJournalPersistence(JournalTestCase):
    def test_record_persists_to_disk(self):
        journal = self.journal()
        disable(self.reg, [item_named(self.reg, "DemoApp")], journal)

        self.assertTrue(self.path.exists())
        reloaded = self.journal()
        self.assertEqual(len(reloaded.entries), 1)
        entry = reloaded.entries[0]
        self.assertEqual(entry.value_name, "LegacyDisable")
        self.assertEqual(entry.scope, Scope.USER.value)
        self.assertFalse(entry.had_previous)

    def test_records_previous_value(self):
        journal = self.journal()
        change = Change(Action.DELETE, BLOCKED_USER, GUID, None, None, "item-1", Scope.USER, "解除屏蔽")
        journal.record(change, ("", REG_SZ))

        entry = self.journal().entries[0]
        self.assertTrue(entry.had_previous)
        self.assertEqual(entry.previous_value, "")
        self.assertEqual(entry.previous_type, REG_SZ)

    def test_export_copies_backup_file(self):
        journal = self.journal()
        disable(self.reg, [item_named(self.reg, "DemoApp")], journal)
        dest = Path(self._tmp.name) / "backup.json"
        journal.export(dest)
        self.assertEqual(json.loads(dest.read_text("utf-8")), json.loads(self.path.read_text("utf-8")))

    def test_missing_file_loads_as_empty(self):
        self.assertEqual(self.journal().entries, [])

    def test_default_path_is_under_appdata(self):
        self.assertIn("RightMenuManager", str(default_journal_path()))


class TestRestore(JournalTestCase):
    def test_restore_removes_added_value(self):
        journal = self.journal()
        item = item_named(self.reg, "DemoApp")
        disable(self.reg, [item], journal)
        self.assertIsNotNone(self.reg.read_value(item.key_path, "LegacyDisable"))

        result = journal.restore_all(self.reg)
        self.assertTrue(result.ok)
        self.assertIsNone(self.reg.read_value(item.key_path, "LegacyDisable"))

    def test_restore_reinstates_previously_deleted_value(self):
        reg = FakeRegistry(
            initial={
                CLASSES + r"\*\shellex\ContextMenuHandlers\DemoShell": {"": (GUID, REG_SZ)},
                CLASSES + "\\CLSID\\" + GUID + r"\InprocServer32": {"": (r"C:\demo.dll", REG_SZ)},
                BLOCKED_USER: {GUID: ("", REG_SZ), OTHER_GUID: ("", REG_SZ)},
            }
        )
        journal = self.journal()
        enable(reg, [item_named(reg, "DemoShell")], journal)
        self.assertIsNone(reg.read_value(BLOCKED_USER, GUID))

        journal.restore_all(reg)
        self.assertEqual(reg.read_value(BLOCKED_USER, GUID), ("", REG_SZ))

    def test_restore_clears_journal_on_success(self):
        journal = self.journal()
        disable(self.reg, [item_named(self.reg, "DemoApp")], journal)
        journal.restore_all(self.reg)
        self.assertEqual(self.journal().entries, [])

    def test_restore_is_reverse_order_and_returns_to_original(self):
        journal = self.journal()
        before = self.reg.snapshot()
        disable(self.reg, [item_named(self.reg, "DemoApp")], journal)
        disable(self.reg, [item_named(self.reg, "DemoShell")], journal)
        self.assertNotEqual(self.reg.snapshot(), before)

        journal.restore_all(self.reg)
        self.assertEqual(self.reg.snapshot(), before)

    def test_restore_leaves_unrelated_values_alone(self):
        journal = self.journal()
        disable(self.reg, [item_named(self.reg, "DemoShell")], journal)
        journal.restore_all(self.reg)
        self.assertEqual(self.reg.read_value(BLOCKED_USER, OTHER_GUID), ("", REG_SZ))

    def test_restore_never_deletes_keys(self):
        journal = self.journal()
        disable(self.reg, [item_named(self.reg, "DemoApp")], journal)
        journal.restore_all(self.reg)
        self.assertEqual(self.reg.delete_key_calls, 0)

    def test_restore_keeps_journal_when_unwritable(self):
        journal = self.journal()
        disable(self.reg, [item_named(self.reg, "DemoApp")], journal)
        readonly = FakeRegistry(
            initial={
                CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ), "LegacyDisable": ("", REG_SZ)}
            },
            readonly_prefixes=(CLASSES + r"\*\shell\DemoApp",),
        )
        with self.assertRaises(PermissionError):
            journal.restore_all(readonly)
        self.assertEqual(len(journal.entries), 1)


if __name__ == "__main__":
    unittest.main()