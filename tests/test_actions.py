import unittest

from rightmenu.actions import Action, apply, disable, enable, plan
from rightmenu.fake_registry import FakeRegistry
from rightmenu.model import Scope
from rightmenu.registry import REG_SZ
from rightmenu.scanner import LEGACY_DISABLE_VALUE, blocked_key_path, scan

CLASSES = r"HKCU\Software\Classes"
BLOCKED_USER = blocked_key_path(Scope.USER)
OTHER_GUID = "{99999999-9999-9999-9999-999999999999}"
GUID = "{11111111-1111-1111-1111-111111111111}"


class RecordingJournal:
    def __init__(self):
        self.entries = []

    def record(self, change, previous):
        self.entries.append((change, previous))


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


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.reg = build_registry()

    def test_disable_static_writes_legacy_disable(self):
        item = item_named(self.reg, "DemoApp")
        result = plan([item], target_disabled=True)
        self.assertEqual(len(result.changes), 1)
        change = result.changes[0]
        self.assertEqual(change.action, Action.WRITE)
        self.assertEqual(change.key_path, item.key_path)
        self.assertEqual(change.value_name, LEGACY_DISABLE_VALUE)
        self.assertEqual(change.value, "")
        self.assertEqual(change.vtype, REG_SZ)

    def test_enable_static_deletes_legacy_disable(self):
        reg = build_registry()
        disable(reg, [item_named(reg, "DemoApp")])
        item = item_named(reg, "DemoApp")
        result = plan([item], target_disabled=False)
        self.assertEqual(result.changes[0].action, Action.DELETE)
        self.assertEqual(result.changes[0].value_name, LEGACY_DISABLE_VALUE)

    def test_disable_shellex_writes_blocked_value_named_by_clsid(self):
        item = item_named(self.reg, "DemoShell")
        result = plan([item], target_disabled=True)
        change = result.changes[0]
        self.assertEqual(change.action, Action.WRITE)
        self.assertEqual(change.key_path, BLOCKED_USER)
        self.assertEqual(change.value_name, GUID)
        self.assertEqual(change.value, "")

    def test_enable_shellex_deletes_blocked_value(self):
        reg = build_registry()
        disable(reg, [item_named(reg, "DemoShell")])
        result = plan([item_named(reg, "DemoShell")], target_disabled=False)
        self.assertEqual(result.changes[0].action, Action.DELETE)
        self.assertEqual(result.changes[0].value_name, GUID)

    def test_item_already_in_target_state_yields_no_change(self):
        self.assertEqual(len(plan([item_named(self.reg, "DemoApp")], True).changes), 1)
        reg = build_registry()
        disable(reg, [item_named(reg, "DemoApp")])
        self.assertEqual(plan([item_named(reg, "DemoApp")], True).changes, [])

    def test_shellex_without_clsid_is_skipped_with_reason(self):
        reg = FakeRegistry(
            initial={CLASSES + r"\*\shellex\ContextMenuHandlers\Weird": {"": ("not-a-guid", REG_SZ)}}
        )
        result = plan([item_named(reg, "Weird")], True)
        self.assertEqual(result.changes, [])
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("CLSID", result.skipped[0][1])


class TestApply(unittest.TestCase):
    def setUp(self):
        self.reg = build_registry()
        self.journal = RecordingJournal()

    def test_apply_writes_and_reports(self):
        item = item_named(self.reg, "DemoApp")
        result = apply(self.reg, plan([item], True).changes, self.journal)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.applied), 1)
        self.assertIsNotNone(self.reg.read_value(item.key_path, LEGACY_DISABLE_VALUE))

    def test_apply_is_idempotent(self):
        item = item_named(self.reg, "DemoApp")
        changes = plan([item], True).changes
        apply(self.reg, changes, self.journal)
        after_first = self.reg.snapshot()
        apply(self.reg, changes, self.journal)
        self.assertEqual(self.reg.snapshot(), after_first)

    def test_apply_deletes_value(self):
        item = item_named(self.reg, "DemoApp")
        disable(self.reg, [item])
        result = enable(self.reg, [item_named(self.reg, "DemoApp")], self.journal)
        self.assertTrue(result.ok)
        self.assertIsNone(self.reg.read_value(item.key_path, LEGACY_DISABLE_VALUE))

    def test_apply_records_previous_value_in_journal(self):
        item = item_named(self.reg, "DemoApp")
        disable(self.reg, [item], self.journal)
        change, previous = self.journal.entries[-1]
        self.assertEqual(change.value_name, LEGACY_DISABLE_VALUE)
        self.assertIsNone(previous)

    def test_apply_records_existing_value_when_deleting(self):
        item = item_named(self.reg, "DemoShell")
        disable(self.reg, [item], self.journal)
        enable(self.reg, [item_named(self.reg, "DemoShell")], self.journal)
        change, previous = self.journal.entries[-1]
        self.assertEqual(change.value_name, GUID)
        self.assertEqual(previous, ("", REG_SZ))

    def test_no_op_changes_are_not_journaled(self):
        item = item_named(self.reg, "DemoApp")
        disable(self.reg, [item], self.journal)
        before = len(self.journal.entries)
        disable(self.reg, [item_named(self.reg, "DemoApp")], self.journal)
        self.assertEqual(len(self.journal.entries), before)

    def test_apply_never_deletes_keys(self):
        disable(self.reg, [item_named(self.reg, "DemoApp")])
        self.assertEqual(self.reg.delete_key_calls, 0)


class TestApplyPermissionSafety(unittest.TestCase):
    def test_aborts_without_partial_writes_when_target_not_writable(self):
        reg = FakeRegistry(
            initial={
                CLASSES + r"\*\shell\DemoApp": {"": ("Demo 应用", REG_SZ)},
                CLASSES + r"\*\shell\DemoApp\command": {"": (r"C:\demo.exe %1", REG_SZ)},
            },
            readonly_prefixes=(CLASSES + r"\*\shell\DemoApp",),
        )
        before = reg.snapshot()
        changes = plan([item_named(reg, "DemoApp")], True).changes
        with self.assertRaises(PermissionError):
            apply(reg, changes)
        self.assertEqual(reg.snapshot(), before)


class TestRoundTrip(unittest.TestCase):
    def test_disable_then_enable_restores_original_state(self):
        reg = build_registry()
        before = reg.snapshot()
        journal = RecordingJournal()

        disable(reg, [item_named(reg, "DemoApp")], journal)
        disable(reg, [item_named(reg, "DemoShell")], journal)
        self.assertNotEqual(reg.snapshot(), before)

        enable(reg, [item_named(reg, "DemoApp")], journal)
        enable(reg, [item_named(reg, "DemoShell")], journal)
        self.assertEqual(reg.snapshot(), before)


if __name__ == "__main__":
    unittest.main()