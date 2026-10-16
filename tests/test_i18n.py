"""多语言机制测试。

覆盖：LANGID 映射、词条回退链、两套内置目录 key 对齐、外部语言包叠加与容错、
settings 读写与优先级。测试一律通过 ``i18n.configure()`` 注入临时目录，
不读写真实的 ``%APPDATA%``。
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rightmenu import i18n


class I18nTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.settings = self.root / "settings.json"
        self.lang_dir = self.root / "lang"

    def configure(self, **kwargs) -> str:
        kwargs.setdefault("lang_dir", self.lang_dir)
        kwargs.setdefault("settings_path", self.settings)
        return i18n.configure(**kwargs)

    def write_pack(self, code: str, payload) -> None:
        self.lang_dir.mkdir(parents=True, exist_ok=True)
        (self.lang_dir / f"{code}.json").write_text(
            payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


class TestDetectLanguage(I18nTestCase):
    def detect(self, langid):
        with mock.patch.object(i18n, "_user_default_language_id", return_value=langid):
            return i18n.detect_language()

    def test_chinese_variants_map_to_zh_cn(self):
        for langid in (0x0804, 0x0404, 0x0C04, 0x1004, 0x1404):
            self.assertEqual(self.detect(langid), "zh_CN", hex(langid))

    def test_other_langids_map_to_en(self):
        self.assertEqual(self.detect(0x0409), "en")  # en-US
        self.assertEqual(self.detect(0x0411), "en")  # ja-JP

    def test_falls_back_to_env_when_ctypes_unavailable(self):
        with mock.patch.object(i18n, "_user_default_language_id", return_value=None):
            with mock.patch.dict(os.environ, {"LANG": "zh_CN.UTF-8"}, clear=False):
                self.assertEqual(i18n.detect_language(), "zh_CN")

    def test_final_fallback_is_en(self):
        env = {k: "" for k in ("LC_ALL", "LC_MESSAGES", "LANG")}
        with mock.patch.object(i18n, "_user_default_language_id", return_value=None):
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(i18n.detect_language(), "en")


class TestCatalogIntegrity(I18nTestCase):
    def test_builtin_catalogs_cover_the_same_keys(self):
        zh = {k for k, v in i18n.CATALOG.items() if "zh_CN" in v}
        en = {k for k, v in i18n.CATALOG.items() if "en" in v}
        self.assertEqual(zh, en)

    def test_no_empty_translation(self):
        for key, entry in i18n.CATALOG.items():
            for lang, text in entry.items():
                self.assertTrue(text, f"{key}[{lang}] 为空")

    def test_every_key_resolves_in_both_builtin_languages(self):
        for lang in i18n.BUILTIN_LANGUAGES:
            self.configure(language=lang)
            for key in i18n.CATALOG:
                self.assertEqual(i18n.t(key), i18n.CATALOG[key][lang], key)


class TestLookupFallback(I18nTestCase):
    def test_returns_key_when_missing(self):
        self.configure(language="zh_CN")
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")

    def test_unknown_language_falls_back_to_english(self):
        self.configure(language="ja")
        self.assertEqual(i18n.t("btn.refresh"), i18n.CATALOG["btn.refresh"]["en"])

    def test_placeholders_are_substituted(self):
        self.configure(language="zh_CN")
        self.assertEqual(i18n.t("group.items_count", n=3), "3 项")

    def test_unknown_placeholder_is_left_intact(self):
        self.configure(language="zh_CN")
        self.assertIn("{child}", i18n.t("loc.extension", child="{child}"))

    def test_stray_braces_in_value_do_not_break_substitution(self):
        self.configure(language="zh_CN")
        text = i18n.t("preview.change_line", description="屏蔽 {AB-CD} 项")
        self.assertIn("屏蔽 {AB-CD} 项", text)


class TestExternalPacks(I18nTestCase):
    def test_external_pack_overrides_builtin(self):
        self.write_pack("zh_CN", {"app.title": "覆盖后的标题"})
        self.configure(language="zh_CN")
        self.assertEqual(i18n.t("app.title"), "覆盖后的标题")

    def test_partial_new_language_falls_back_to_english(self):
        self.write_pack("ja", {"app.title": "タイトル"})
        self.configure(language="ja")
        self.assertEqual(i18n.t("app.title"), "タイトル")
        self.assertEqual(i18n.t("btn.refresh"), i18n.CATALOG["btn.refresh"]["en"])

    def test_missing_lang_dir_is_fine(self):
        self.configure(language="zh_CN", lang_dir=self.root / "does-not-exist")
        self.assertEqual(i18n.t("btn.refresh"), i18n.CATALOG["btn.refresh"]["zh_CN"])

    def test_corrupt_pack_is_ignored(self):
        self.write_pack("zh_CN", "{ this is not json")
        self.configure(language="zh_CN")
        self.assertEqual(i18n.t("app.title"), i18n.CATALOG["app.title"]["zh_CN"])

    def test_non_object_pack_is_ignored(self):
        self.write_pack("xx", [1, 2, 3])
        self.configure(language="xx")
        self.assertNotIn("xx", i18n.available_languages())
        self.assertEqual(i18n.t("app.title"), i18n.CATALOG["app.title"]["en"])

    def test_non_string_values_are_ignored(self):
        self.write_pack("zh_CN", {"app.title": 123, "btn.refresh": "刷新!"})
        self.configure(language="zh_CN")
        self.assertEqual(i18n.t("btn.refresh"), "刷新!")
        self.assertEqual(i18n.t("app.title"), i18n.CATALOG["app.title"]["zh_CN"])

    def test_bom_prefixed_pack_is_read(self):
        # 记事本另存为「UTF-8 带 BOM」是翻译者的常见操作，不应因此失效。
        self.lang_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"app.title": "带 BOM 的标题"}, ensure_ascii=False)
        (self.lang_dir / "fr.json").write_text(payload, encoding="utf-8-sig")
        self.configure(language="fr")
        self.assertIn("fr", i18n.available_languages())
        self.assertEqual(i18n.t("app.title"), "带 BOM 的标题")


class TestAvailableLanguages(I18nTestCase):
    def test_lists_builtin_languages(self):
        self.configure()
        self.assertEqual(i18n.available_languages()[:2], ["zh_CN", "en"])

    def test_includes_external_extras(self):
        self.write_pack("ja", {"app.title": "タイトル"})
        self.configure()
        self.assertIn("ja", i18n.available_languages())

    def test_language_label_uses_catalog(self):
        self.configure(language="zh_CN")
        self.assertEqual(i18n.language_label("zh_CN"), "简体中文")

    def test_language_label_falls_back_to_code(self):
        self.write_pack("xx", {"app.title": "X"})
        self.configure(language="zh_CN")
        self.assertEqual(i18n.language_label("xx"), "xx")


class TestSettingsPersistence(I18nTestCase):
    def test_set_language_persists(self):
        self.configure(language="en")
        i18n.set_language("zh_CN")
        self.assertEqual(json.loads(self.settings.read_text("utf-8")), {"language": "zh_CN"})

    def test_saved_language_is_reloaded(self):
        self.configure(language="en")
        i18n.set_language("zh_CN")
        self.assertEqual(self.configure(), "zh_CN")

    def test_saved_language_wins_over_detection(self):
        self.configure(language="zh_CN")
        i18n.set_language("en")
        with mock.patch.object(i18n, "_user_default_language_id", return_value=0x0804):
            self.assertEqual(self.configure(), "en")

    def test_explicit_language_argument_wins_over_saved(self):
        self.configure(language="zh_CN")
        i18n.set_language("en")
        self.assertEqual(self.configure(language="zh_CN"), "zh_CN")

    def test_corrupt_settings_file_falls_back_to_detection(self):
        self.settings.write_text("not json", encoding="utf-8")
        with mock.patch.object(i18n, "_user_default_language_id", return_value=0x0804):
            self.assertEqual(self.configure(), "zh_CN")

    def test_bom_prefixed_settings_is_read(self):
        self.settings.write_text('{"language": "en"}', encoding="utf-8-sig")
        with mock.patch.object(i18n, "_user_default_language_id", return_value=0x0804):
            self.assertEqual(self.configure(), "en")

    def test_set_language_without_persist_does_not_write(self):
        self.configure(language="en")
        i18n.set_language("zh_CN", persist=False)
        self.assertEqual(i18n.get_language(), "zh_CN")
        self.assertFalse(self.settings.exists())


class TestShippedLanguagePacks(unittest.TestCase):
    """发行版随附的 lang/*.json 必须与内置目录逐条一致，杜绝两处漂移。"""

    def test_shipped_packs_match_builtin(self):
        lang_dir = i18n.default_lang_dir()
        for code in i18n.BUILTIN_LANGUAGES:
            path = lang_dir / f"{code}.json"
            self.assertTrue(path.exists(), f"缺少语言包: {path}")
            table = json.loads(path.read_text(encoding="utf-8"))
            expected = {k: v[code] for k, v in i18n.CATALOG.items() if code in v}
            self.assertEqual(table, expected, f"{code} 语言包与内置目录不一致")


if __name__ == "__main__":
    unittest.main()