import unittest

from rightmenu.model import ContextMenuItem, DisableMethod, Kind, Scope


def make_item(**overrides):
    base = dict(
        scope=Scope.USER,
        kind=Kind.STATIC,
        location="所有文件",
        key_path=r"HKCU\Software\Classes\*\shell\Demo",
        display_name="Demo",
        key_name="Demo",
    )
    base.update(overrides)
    return ContextMenuItem(**base)


class TestItemId(unittest.TestCase):
    def test_id_is_stable_for_same_scope_and_path(self):
        self.assertEqual(make_item().id, make_item(display_name="改过名字").id)

    def test_id_differs_by_key_path(self):
        a = make_item(key_path=r"HKCU\Software\Classes\*\shell\A")
        b = make_item(key_path=r"HKCU\Software\Classes\*\shell\B")
        self.assertNotEqual(a.id, b.id)

    def test_id_differs_by_scope(self):
        self.assertNotEqual(make_item(scope=Scope.USER).id, make_item(scope=Scope.MACHINE).id)


class TestNeedsAdmin(unittest.TestCase):
    def test_machine_scope_needs_admin(self):
        self.assertTrue(make_item(scope=Scope.MACHINE).needs_admin)

    def test_user_scope_does_not_need_admin(self):
        self.assertFalse(make_item(scope=Scope.USER).needs_admin)


class TestDefaults(unittest.TestCase):
    def test_defaults_are_inert(self):
        item = make_item()
        self.assertFalse(item.disabled)
        self.assertIsNone(item.method)
        self.assertIsNone(item.command)
        self.assertIsNone(item.clsid)
        self.assertIsNone(item.dll_path)
        self.assertFalse(item.extended)

    def test_is_immutable(self):
        with self.assertRaises(Exception):
            make_item().disabled = True


class TestEnums(unittest.TestCase):
    def test_disable_method_values(self):
        self.assertEqual(DisableMethod.BLOCKED.value, "blocked")
        self.assertEqual(DisableMethod.LEGACY_DISABLE.value, "legacy_disable")


if __name__ == "__main__":
    unittest.main()