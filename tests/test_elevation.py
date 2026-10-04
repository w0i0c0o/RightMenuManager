import sys
import unittest
from unittest import mock

from rightmenu import elevation


class TestIsAdmin(unittest.TestCase):
    def test_returns_bool_without_raising(self):
        self.assertIsInstance(elevation.is_admin(), bool)


class TestRelaunchAsAdmin(unittest.TestCase):
    def test_returns_false_when_already_admin(self):
        with mock.patch.object(elevation, "is_admin", return_value=True):
            self.assertFalse(elevation.relaunch_as_admin(["--scan"]))

    def test_does_not_spawn_when_already_admin(self):
        with mock.patch.object(elevation, "is_admin", return_value=True), mock.patch.object(
            elevation, "_shell_execute_runas"
        ) as spawn:
            elevation.relaunch_as_admin(["--scan"])
        spawn.assert_not_called()

    def test_invokes_runas_with_current_arguments(self):
        captured = {}

        def fake_spawn(executable, params):
            captured["exe"] = executable
            captured["params"] = params
            return 33

        with mock.patch.object(elevation, "is_admin", return_value=False), mock.patch.object(
            elevation, "_shell_execute_runas", fake_spawn
        ):
            ok = elevation.relaunch_as_admin(["--scan", "--scope", "machine"])

        self.assertTrue(ok)
        self.assertEqual(captured["exe"], sys.executable)
        self.assertIn("--scan", captured["params"])
        self.assertIn("machine", captured["params"])

    def test_reports_failure_when_uac_declined(self):
        with mock.patch.object(elevation, "is_admin", return_value=False), mock.patch.object(
            elevation, "_shell_execute_runas", return_value=5
        ):
            self.assertFalse(elevation.relaunch_as_admin(["--scan"]))


if __name__ == "__main__":
    unittest.main()