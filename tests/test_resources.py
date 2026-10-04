import unittest

from rightmenu.resources import resolve_text, strip_accelerator


def fake_loader(mapping: dict[str, str]):
    """模拟 SHLoadIndirectString：只认识 mapping 里的引用。"""
    return lambda source: mapping.get(source)


class TestStripAccelerator(unittest.TestCase):
    def test_removes_marker_before_letter(self):
        self.assertEqual(strip_accelerator("打开(&O)"), "打开(O)")

    def test_double_ampersand_is_literal(self):
        self.assertEqual(strip_accelerator("A && B"), "A & B")

    def test_text_without_marker_unchanged(self):
        self.assertEqual(strip_accelerator("PATH 助手"), "PATH 助手")


class TestResolveText(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(resolve_text(None, fake_loader({})))

    def test_blank_returns_none(self):
        self.assertIsNone(resolve_text("   ", fake_loader({})))

    def test_plain_text_returned_as_is(self):
        self.assertEqual(resolve_text("PATH 助手", fake_loader({})), "PATH 助手")

    def test_indirect_string_is_resolved_and_accelerator_stripped(self):
        loader = fake_loader({r"@shell32.dll,-8506": "在此处打开命令窗口(&W)"})
        self.assertEqual(resolve_text(r"@shell32.dll,-8506", loader), "在此处打开命令窗口(W)")

    def test_indirect_string_resolved_without_accelerator(self):
        loader = fake_loader({r"@shell32.dll,-8506": "设置为桌面背景"})
        self.assertEqual(resolve_text(r"@shell32.dll,-8506", loader), "设置为桌面背景")

    def test_unresolvable_indirect_returns_none(self):
        self.assertIsNone(resolve_text(r"@missing.dll,-1", fake_loader({})))

    def test_empty_resolution_returns_none(self):
        self.assertIsNone(resolve_text(r"@empty.dll,-1", fake_loader({r"@empty.dll,-1": ""})))


if __name__ == "__main__":
    unittest.main()