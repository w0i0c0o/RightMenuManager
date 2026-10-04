"""启动脚本的编码不变式。

Windows PowerShell 5.1 读取无 BOM 的 .ps1 时按系统 ANSI 代码页解析：
若文件含非 ASCII 字符（如中文）就会变乱码，甚至破坏字符串引号导致整个脚本解析失败 —— 
表现为双击 run.cmd 后「没有任何窗口」。本测试锁住这个陷阱。
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTF8_BOM = b"\xef\xbb\xbf"


class TestLauncherEncoding(unittest.TestCase):
    def test_run_ps1_is_bom_or_ascii(self):
        data = (ROOT / "run.ps1").read_bytes()
        if data.startswith(UTF8_BOM):
            return
        self.assertTrue(
            all(byte < 128 for byte in data),
            "run.ps1 既无 UTF-8 BOM 又含非 ASCII 字符：PowerShell 5.1 会按 ANSI 解析并失败",
        )

    def test_run_cmd_is_ascii(self):
        data = (ROOT / "run.cmd").read_bytes()
        self.assertTrue(
            all(byte < 128 for byte in data),
            "run.cmd 含非 ASCII 字符：cmd 按 ANSI 读取，可能乱码",
        )


if __name__ == "__main__":
    unittest.main()