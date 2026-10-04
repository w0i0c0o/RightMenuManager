import unittest
import winreg

from rightmenu.fake_registry import FakeRegistry
from rightmenu.registry import REG_SZ, split_root


class TestSplitRoot(unittest.TestCase):
    def test_maps_known_hives(self):
        self.assertEqual(split_root(r"HKCU\Software")[0], winreg.HKEY_CURRENT_USER)
        self.assertEqual(split_root(r"HKLM\SOFTWARE")[0], winreg.HKEY_LOCAL_MACHINE)
        self.assertEqual(split_root(r"HKCR\*\shell")[0], winreg.HKEY_CLASSES_ROOT)
        self.assertEqual(split_root(r"HKU\S-1-5-21")[0], winreg.HKEY_USERS)

    def test_returns_subkey(self):
        self.assertEqual(split_root(r"HKCU\Software\Classes")[1], r"Software\Classes")

    def test_root_only_has_empty_subkey(self):
        self.assertEqual(split_root("HKCU")[1], "")

    def test_unknown_hive_raises(self):
        with self.assertRaises(ValueError):
            split_root(r"HKZZ\foo")


class TestFakeRegistryValues(unittest.TestCase):
    def setUp(self):
        self.reg = FakeRegistry()

    def test_missing_key_does_not_exist(self):
        self.assertFalse(self.reg.key_exists(r"HKCU\A"))

    def test_write_creates_key_and_value(self):
        self.reg.write_value(r"HKCU\A\B", "X", "v", REG_SZ)
        self.assertTrue(self.reg.key_exists(r"HKCU\A\B"))
        self.assertEqual(self.reg.read_value(r"HKCU\A\B", "X"), ("v", REG_SZ))

    def test_write_creates_ancestors(self):
        self.reg.write_value(r"HKCU\A\B\C", None, "v", REG_SZ)
        self.assertTrue(self.reg.key_exists(r"HKCU\A"))
        self.assertTrue(self.reg.key_exists(r"HKCU\A\B"))

    def test_none_and_empty_name_both_mean_default(self):
        self.reg.write_value(r"HKCU\A", None, "默认", REG_SZ)
        self.assertEqual(self.reg.read_value(r"HKCU\A", None), ("默认", REG_SZ))
        self.assertEqual(self.reg.read_value(r"HKCU\A", ""), ("默认", REG_SZ))

    def test_read_missing_returns_none(self):
        self.reg.write_value(r"HKCU\A", "X", "v", REG_SZ)
        self.assertIsNone(self.reg.read_value(r"HKCU\A", "Y"))
        self.assertIsNone(self.reg.read_value(r"HKCU\Nope", "X"))

    def test_path_and_value_name_are_case_insensitive(self):
        self.reg.write_value(r"HKCU\A\B", "X", "v", REG_SZ)
        self.assertEqual(self.reg.read_value(r"hkcu\a\b", "x"), ("v", REG_SZ))

    def test_list_subkeys_returns_direct_children_only(self):
        self.reg.write_value(r"HKCU\A\B", None, "", REG_SZ)
        self.reg.write_value(r"HKCU\A\C", None, "", REG_SZ)
        self.reg.write_value(r"HKCU\A\B\D", None, "", REG_SZ)
        self.assertEqual(sorted(self.reg.list_subkeys(r"HKCU\A")), ["B", "C"])

    def test_list_subkeys_missing_key_returns_empty(self):
        self.assertEqual(self.reg.list_subkeys(r"HKCU\Nope"), [])

    def test_delete_value(self):
        self.reg.write_value(r"HKCU\A", "X", "v", REG_SZ)
        self.reg.delete_value(r"HKCU\A", "X")
        self.assertIsNone(self.reg.read_value(r"HKCU\A", "X"))

    def test_delete_missing_value_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.reg.delete_value(r"HKCU\A", "X")


class TestFakeRegistrySafety(unittest.TestCase):
    def test_delete_key_is_forbidden(self):
        reg = FakeRegistry(initial={r"HKCU\A": {"X": ("v", REG_SZ)}})
        with self.assertRaises(AssertionError):
            reg.delete_key(r"HKCU\A")
        self.assertTrue(reg.key_exists(r"HKCU\A"))

    def test_ensure_writable_accepts_normal_path(self):
        FakeRegistry().ensure_writable(r"HKCU\A\B")

    def test_ensure_writable_rejects_readonly_prefix(self):
        reg = FakeRegistry(readonly_prefixes=(r"HKLM\SOFTWARE",))
        with self.assertRaises(PermissionError):
            reg.ensure_writable(r"HKLM\SOFTWARE\Classes\*\shell\X")
        reg.ensure_writable(r"HKCU\A")


class TestFakeRegistryTestHelpers(unittest.TestCase):
    def test_seed_initial(self):
        reg = FakeRegistry(initial={r"HKCU\A": {"X": ("v", REG_SZ)}})
        self.assertEqual(reg.read_value(r"HKCU\A", "X"), ("v", REG_SZ))

    def test_snapshot_is_a_copy(self):
        reg = FakeRegistry(initial={r"HKCU\A": {"X": ("v", REG_SZ)}})
        snap = reg.snapshot()
        reg.write_value(r"HKCU\A", "Y", "w", REG_SZ)
        self.assertNotIn("Y", snap[r"HKCU\A".upper()])

    def test_keys_are_normalized_and_ancestors_exist(self):
        reg = FakeRegistry(initial={r"HKCU\A\B": {}})
        self.assertIn(r"HKCU\A\B".upper(), reg.keys())
        self.assertIn(r"HKCU\A".upper(), reg.keys())


if __name__ == "__main__":
    unittest.main()