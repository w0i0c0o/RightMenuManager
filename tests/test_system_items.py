import os
import unittest
from unittest import mock

from rightmenu import system_items

WIN = r"C:\Windows"


class TestPathEvidence(unittest.TestCase):
    def test_windows_directory_module_is_system(self):
        self.assertTrue(system_items.classify([r"C:\Windows\system32\shell32.dll"], WIN))

    def test_program_files_app_is_not_system(self):
        self.assertFalse(system_items.classify([r"C:\Program Files\7-Zip\7-zip.dll"], WIN))

    def test_user_appdata_module_is_not_system(self):
        self.assertFalse(
            system_items.classify([r"C:\Users\WW\AppData\Local\MeituApp\XiuXiu.exe"], WIN)
        )

    def test_drive_other_than_system_is_not_system(self):
        self.assertFalse(system_items.classify([r"D:\Tools\MediaInfo.exe"], WIN))

    def test_program_files_windows_component_is_system(self):
        with mock.patch.dict(os.environ, {"ProgramFiles": r"C:\Program Files"}, clear=False):
            self.assertTrue(
                system_items.classify(
                    [r"C:\Program Files\Windows Defender\shellext.dll"], WIN
                )
            )

    def test_program_files_windows_lookalike_prefix_does_not_leak(self):
        """``WindowsApps`` 不是系统组件目录（Store 应用），不应算自带。"""
        with mock.patch.dict(os.environ, {"ProgramFiles": r"C:\Program Files"}, clear=False):
            self.assertFalse(
                system_items.classify([r"C:\Program Files\WindowsApps\app.exe"], WIN)
            )

    def test_driverstore_component_is_not_system(self):
        """驱动包放在 DriverStore 里（如 NVIDIA），属厂商组件而非系统自带。"""
        self.assertFalse(
            system_items.classify(
                [
                    r"C:\Windows\System32\DriverStore\FileRepository\nv_dispig.inf_amd64_x\nvshext.dll"
                ],
                WIN,
            )
        )


class TestBareModuleEvidence(unittest.TestCase):
    def test_bare_system_module_is_system(self):
        self.assertTrue(system_items.classify(["@shell32.dll,-51601"], WIN))

    def test_bare_system_executable_is_system(self):
        self.assertTrue(system_items.classify(["cmd.exe /s /k pushd \"%V\""], WIN))

    def test_unknown_bare_name_is_not_system(self):
        self.assertFalse(system_items.classify(["baidunetdisk"], WIN))

    def test_display_text_only_is_not_system(self):
        self.assertFalse(system_items.classify(["ArmouryCrate", "g0;"], WIN))

    def test_no_evidence_is_not_system(self):
        self.assertFalse(system_items.classify([], WIN))
        self.assertFalse(system_items.classify(["", None], WIN))


class TestMixedEvidence(unittest.TestCase):
    def test_absolute_outside_path_overrides_bare_system_name(self):
        """借 rundll32.exe 加载第三方 DLL 时，以 DLL 的落点为准。"""
        self.assertFalse(
            system_items.classify(
                [
                    r'rundll32.exe "C:\Program Files\Vendor\vstoee.dll",Entry %1',
                ],
                WIN,
            )
        )

    def test_bare_host_with_windows_payload_is_system(self):
        self.assertTrue(
            system_items.classify(
                [r"rundll32.exe C:\Windows\system32\shimgvw.dll,ImageView_Fullscreen %1"],
                WIN,
            )
        )

    def test_any_outside_absolute_path_wins(self):
        self.assertFalse(
            system_items.classify(
                [r'"C:\Windows\system32\a.exe" "C:\Program Files\b.dll"'], WIN
            )
        )

    def test_system_host_loading_outside_script_is_not_system(self):
        """powershell.exe 是系统宿主，但脚本载荷在别处 —— 仍是第三方项。"""
        self.assertFalse(
            system_items.classify(
                [
                    r'"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" '
                    r'-NoProfile -File "E:\Tools\PathAdder\MenuPicker.ps1" -Target "%V"'
                ],
                WIN,
            )
        )

    def test_quoted_and_indirect_forms_are_both_parsed(self):
        self.assertTrue(
            system_items.classify(
                ['@C:\\Windows\\system32\\unregmp2.exe,-9801', r'"C:\Windows\notepad.exe" %1'],
                WIN,
            )
        )

    def test_icon_value_counts_as_evidence(self):
        self.assertTrue(system_items.classify([r"C:\Windows\system32\themecpl.dll,-1"], WIN))


if __name__ == "__main__":
    unittest.main()