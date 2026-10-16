> English | [简体中文](2026-10-12-i18n-mechanism.zh_CN.md)

# Internationalization (i18n) mechanism selection

date: 2026-10-12
status: accepted

## Background

The program needs to be bilingual in Chinese and English, and it explicitly requires that "adding more languages later be convenient". Three hard constraints hold at the same time:

1. **Zero pip dependencies, double-click to use** —— standard library only, no build/compile step;
2. **The UI must never crash** —— missing words, a damaged language pack, or the entire `lang/` directory being lost must not prevent the program from starting;
3. **The cost of adding a language must be low** —— adding a language should not require changing Python code.

## Alternatives

| Option | Adding a language | Zero dependencies | Fault tolerance | Conclusion |
|---|---|---|---|---|
| gettext (`.po` / `.mo`) | Add a `.po`, must be compiled to `.mo` | ✗ The standard library has no `.mo` compiler, needs `msgfmt`/pip | Fair | Rejected |
| All translations written in Python (pure built-in dict) | Must change code and repackage | ✓ | A translator's wrong quote breaks the whole program | Rejected |
| External JSON language pack (purely external) | Drop in a `lang/xx.json` | ✓ | Damage to a single file affects only that language | Adopted (but needs a fallback) |
| **Built-in baseline + external language pack overlay** | Drop in a `lang/xx.json` | ✓ | A lost directory falls back to built-in, a damaged file is ignored | **Adopted** |

## Decision

Adopt **built-in baseline + external language pack overlay**:

```
Built-in CATALOG (rightmenu/i18n.py)  : {"ui.title": {"zh_CN": "…", "en": "…"}, …}   # fallback + authoritative source
External language pack (lang/<code>.json)      : {"ui.title": "…", …}                        # scanned and overlaid at startup
Lookup chain                             : external pack[lang][key] → built-in[lang][key] → built-in["en"][key] → the key itself
```

Rationale:

- **Adding a language = dropping in a file**. An external pack uses the file name as the language code (`lang/fr.json` → `fr`), is scanned automatically at startup,
  and a new entry automatically appears in the UI's language dropdown —— without touching a single line of Python.
- **The built-in fallback makes "zero dependencies, double-click to use" hold**. `lang/` is an optional enhancement; delete it and the program still runs, just without add-on languages.
  The built-in `CATALOG` is also the authoritative source, and tests assert that the key sets of `zh_CN` and `en` are exactly identical, preventing missed translations.
- **Fault tolerance is in place**. `_load_packs` ignores damaged JSON, non-objects, and non-string values entry by entry; `t()` returns the key itself when a word is missing,
  and never throws an exception; a failed `settings.json` write only affects "remembering the choice on next startup" and does not affect the current session.
  Both language packs and settings are read with `utf-8-sig` —— a translator saving as "UTF-8 with BOM" in Notepad can use it directly.
- **Overlay rather than overwrite**. An external pack may translate only part of the keys, and uncovered ones automatically fall back to the built-in translation,
  so a "half-finished" language pack also works (`test_partial_new_language_falls_back_to_english`).

## Alignment with other constraints

- **Enum values are not translated**: `scope` / `kind` / `method` are machine-readable tokens, always in English,
  and automation (the JSON of `--scan`) is not affected by the UI language; only `location` is display text and changes with the language.
- **Dynamic location names**: the `SCAN_TARGETS` constant in `locations.py` was changed to a `scan_targets()` function;
  location names are generated via `t()` at call time, and after switching languages `controller.refresh()` re-scans to refresh them.
- **History records keep their original form**: the `description` in the `journal` is fixed in language when written, so after switching languages old records remain in their original text;
  the restore/undo prefixes are translated at display time.

## Impact

- New files: `rightmenu/i18n.py`, `lang/zh_CN.json`, `lang/en.json`, `tests/test_i18n.py`.
- All user-facing text now goes through `i18n.t()`; code comments and docstrings remain in Chinese (an existing project convention).
- Distribution packaging must include the `lang/` directory (`package_portable.ps1` already does).
- The language choice is persisted to `%APPDATA%\RightMenuManager\settings.json` (`{"language": "zh_CN"}`).

## Related

- Spec: the "Internationalization (i18n)" section of `docs/tech-spec.md`
- Implementation: `rightmenu/i18n.py`
- Tests: `tests/test_i18n.py` (language detection LANGID mapping, fallback chain, alignment of the two catalogs' keys, external pack overlay and fault tolerance, settings read/write)