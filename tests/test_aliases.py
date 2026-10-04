import json
import tempfile
import unittest
from pathlib import Path

from rightmenu.aliases import AliasStore


class TestInMemoryStore(unittest.TestCase):
    def test_set_and_get(self):
        store = AliasStore()
        store.set("baidunetdisk", "上传到百度网盘")
        self.assertEqual(store.get("baidunetdisk"), "上传到百度网盘")

    def test_blank_label_removes_alias(self):
        store = AliasStore()
        store.set("baidunetdisk", "上传到百度网盘")
        store.set("baidunetdisk", "   ")
        self.assertIsNone(store.get("baidunetdisk"))

    def test_unknown_key_returns_none(self):
        self.assertIsNone(AliasStore().get("不存在"))

    def test_as_dict_returns_copy(self):
        store = AliasStore()
        store.set("k", "v")
        snapshot = store.as_dict()
        snapshot["k"] = "changed"
        self.assertEqual(store.get("k"), "v")


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "aliases.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_survives_reload(self):
        AliasStore(self.path).set("baidunetdisk", "上传到百度网盘")
        self.assertEqual(AliasStore(self.path).get("baidunetdisk"), "上传到百度网盘")

    def test_written_as_utf8_json(self):
        AliasStore(self.path).set("k", "中文别名")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"k": "中文别名"})

    def test_corrupt_file_is_ignored(self):
        self.path.write_text("{ 不是 JSON", encoding="utf-8")
        self.assertEqual(AliasStore(self.path).as_dict(), {})

    def test_missing_file_is_empty(self):
        self.assertEqual(AliasStore(self.path).as_dict(), {})


if __name__ == "__main__":
    unittest.main()