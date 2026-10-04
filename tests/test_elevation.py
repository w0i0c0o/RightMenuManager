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

        def fake_spawn(executable, params, workdir=None):
            captured["exe"] = executable
            captured["params"] = params
            captured["workdir"] = workdir
            return 33

        with mock.patch.object(elevation, "is_admin", return_value=False), mock.patch.object(
            elevation, "_shell_execute_runas", fake_spawn
        ):
            ok = elevation.relaunch_as_admin(["--scan", "--scope", "machine"])

        self.assertTrue(ok)
        self.assertEqual(captured["exe"], sys.executable)
        self.assertIn("--scan", captured["params"])
        self.assertIn("machine", captured["params"])

    def test_relaunch_restores_module_invocation(self):
        """重启必须带 `-m rightmenu`，否则提权后只会拉起一个空解释器。"""
        captured = {}

        def fake_spawn(executable, params, workdir=None):
            captured["params"] = params
            captured["workdir"] = workdir
            return 33

        with mock.patch.object(elevation, "is_admin", return_value=False), mock.patch.object(
            elevation, "_shell_execute_runas", fake_spawn
        ):
            elevation.relaunch_as_admin([])

        self.assertIn("-m rightmenu", captured["params"])
        self.assertEqual(captured["workdir"], elevation._PROJECT_ROOT)

    def test_relaunch_uses_no_extra_args_by_default(self):
        with mock.patch.object(elevation, "is_admin", return_value=False), mock.patch.object(
            elevation, "sys"
        ) as fake_sys, mock.patch.object(elevation, "_shell_execute_runas", return_value=33):
            fake_sys.argv = ["rightmenu"]
            elevation.relaunch_as_admin()
            params = elevation._shell_execute_runas.call_args[0][1]

        self.assertEqual(params.strip(), "-m rightmenu")

    def test_reports_failure_when_uac_declined(self):
        with mock.patch.object(elevation, "is_admin", return_value=False), mock.patch.object(
            elevation, "_shell_execute_runas", return_value=5
        ):
            self.assertFalse(elevation.relaunch_as_admin(["--scan"]))


if __name__ == "__main__":
    unittest.main()