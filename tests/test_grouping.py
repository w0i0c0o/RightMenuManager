import unittest

from rightmenu.grouping import group_items, group_key
from rightmenu.model import ContextMenuItem, Kind, Scope


def make(display, location="所有文件", key_name=None, path=None, **overrides):
    key_name = key_name or display
    path = path or rf"HKCU\Software\Classes\*\shell\{key_name}"
    base = dict(
        scope=Scope.USER,
        kind=Kind.STATIC,
        location=location,
        key_path=path,
        display_name=display,
        key_name=key_name,
    )
    base.update(overrides)
    return ContextMenuItem(**base)


class TestGroupKey(unittest.TestCase):
    def test_ignores_case_and_whitespace(self):
        self.assertEqual(group_key(make("  上传到百度网盘 ")), group_key(make("上传到百度网盘")))

    def test_differs_for_different_text(self):
        self.assertNotEqual(group_key(make("A")), group_key(make("B")))


class TestGroupItems(unittest.TestCase):
    def test_merges_same_text_across_locations(self):
        items = [
            make("上传到百度网盘", "所有文件", "BaiduAll", r"HKCU\Software\Classes\*\shell\BaiduAll"),
            make("上传到百度网盘", ".docx 文件", "BaiduDocx", r"HKCU\Software\Classes\.docx\shell\BaiduDocx"),
        ]
        groups = group_items(items)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.total, 2)
        self.assertEqual(group.label, "上传到百度网盘")
        self.assertEqual(len(group.locations), 2)

    def test_keeps_distinct_texts_separate(self):
        groups = group_items([make("A"), make("B")])
        self.assertEqual(len(groups), 2)

    def test_sorted_by_instance_count_descending(self):
        items = [make("少", "所有文件", "One"), make("多", "所有文件", "Two")]
        items += [make("多", "目录", "TwoB", r"HKCU\Software\Classes\Directory\shell\TwoB")]
        labels = [g.label for g in group_items(items)]
        self.assertEqual(labels[0], "多")


class TestGroupState(unittest.TestCase):
    def test_enabled_when_none_disabled(self):
        group = group_items([make("A"), make("A", "目录", "A2", r"HKCU\Software\Classes\Directory\shell\A2")])[0]
        self.assertEqual(group.state, "enabled")
        self.assertEqual(group.disabled_count, 0)

    def test_disabled_when_all_disabled(self):
        group = group_items([make("A", disabled=True)])[0]
        self.assertEqual(group.state, "disabled")

    def test_partial_when_some_disabled(self):
        items = [
            make("A", disabled=True),
            make("A", "目录", "A2", r"HKCU\Software\Classes\Directory\shell\A2"),
        ]
        self.assertEqual(group_items(items)[0].state, "partial")


class TestAliasLabel(unittest.TestCase):
    def test_alias_overrides_label_but_not_key(self):
        items = [make("baidunetdisk")]
        key = group_key(items[0])
        group = group_items(items, {key: "上传到百度网盘"})[0]
        self.assertEqual(group.label, "上传到百度网盘")
        self.assertEqual(group.raw_name, "baidunetdisk")
        self.assertEqual(group.key, key)
        self.assertTrue(group.has_alias)

    def test_no_alias_means_label_equals_raw_name(self):
        group = group_items([make("上传到百度网盘")])[0]
        self.assertFalse(group.has_alias)
        self.assertEqual(group.label, group.raw_name)


class TestNeedsAlias(unittest.TestCase):
    def test_true_when_all_names_are_fallbacks(self):
        group = group_items([make("baidunetdisk", name_is_fallback=True)])[0]
        self.assertTrue(group.needs_alias)

    def test_false_when_name_was_resolved(self):
        group = group_items([make("上传到百度网盘", name_is_fallback=False)])[0]
        self.assertFalse(group.needs_alias)

    def test_false_when_alias_set(self):
        key = group_key(make("baidunetdisk", name_is_fallback=True))
        group = group_items([make("baidunetdisk", name_is_fallback=True)], {key: "百度网盘"})[0]
        self.assertFalse(group.needs_alias)


class TestDetailSummary(unittest.TestCase):
    def test_dll_paths_are_unique_and_sorted(self):
        items = [
            make("A", dll_path=r"C:\b.dll", kind=Kind.SHELLEX),
            make("A", "目录", "A2", r"HKCU\Software\Classes\Directory\shellex\ContextMenuHandlers\A2",
                 dll_path=r"C:\a.dll", kind=Kind.SHELLEX),
            make("A", "文件夹", "A3", r"HKCU\Software\Classes\Folder\shellex\ContextMenuHandlers\A3",
                 dll_path=r"C:\a.dll", kind=Kind.SHELLEX),
        ]
        group = group_items(items)[0]
        self.assertEqual(group.dll_paths, (r"C:\a.dll", r"C:\b.dll"))

    def test_sample_detail_prefers_dll_then_command(self):
        self.assertEqual(
            group_items([make("A", dll_path=r"C:\x.dll", command="x.exe")])[0].sample_detail,
            r"C:\x.dll",
        )
        self.assertEqual(group_items([make("A", command="x.exe")])[0].sample_detail, "x.exe")
        self.assertEqual(group_items([make("A")])[0].sample_detail, "")


if __name__ == "__main__":
    unittest.main()