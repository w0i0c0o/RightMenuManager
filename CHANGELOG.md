> English | [简体中文](CHANGELOG.zh_CN.md)

# Changelog

This file records all notable changes. Format based on Keep a Changelog.

## [0.2.0] - 2026-10-17

### Added
- Internationalization (i18n): added `rightmenu/i18n.py` and `tests/test_i18n.py`; UI text, location names, change descriptions,
  preview text, and CLI help all obtain their wording via `i18n.t(key)`. Built-in **Simplified Chinese** and **English**, defaulting to following the system language
  (Chinese variants of `GetUserDefaultUILanguage()` → `zh_CN`, everything else → `en`); the toolbar "Language:" dropdown can
  switch at any time and records to `%APPDATA%\RightMenuManager\settings.json`; the command line adds `--lang`
- The i18n mechanism is "**built-in baseline + external language pack overlay**": the built-in `CATALOG` serves as a fallback (it still runs even if `lang\` is lost),
  and external `lang\<code>.json` files are scanned and overlaid at startup. The lookup chain is external pack → built-in[target language] → built-in[en] → the key itself;
  adding a language only requires dropping in a JSON file, without touching the code, and a half-finished language pack automatically falls back to English. Fault tolerance: a missing word returns the key itself,
  a damaged/non-object/non-string value in a language pack is ignored entry by entry, a missing `lang\` does not affect startup, and a BOM prefix can also be read
- Dynamic location names: the `SCAN_TARGETS` constant in `locations.py` was changed to a `scan_targets()` function; location names are
  generated via `t()` at call time, so re-scanning after switching languages refreshes them; the `scan(..., targets=...)` injection point is unchanged
- Documentation is now bilingual: **English is the default** (`README.md`, `CHANGELOG.md`, `docs/tech-spec.md`, `docs/ROADMAP.md`,
  `docs/decisions/*.md`), and each file has a Chinese twin (`X.zh_CN.md`) with a language-switch link on the first line;
  every future change must update both. `package_portable.ps1` now ships both `README.md` and `README.zh_CN.md`
- License: adopts **GPL-3.0**, adds the official full text `LICENSE`, and README adds a Chinese license explanation and copyright notice
- Decision record: `docs/decisions/2026-10-12-i18n-mechanism.md` (gettext / pure built-in dict / external JSON comparison and selection)

## [0.1.0] - 2026-10-04

### Added
- Project scaffolding: package structure, test directory, run script and task script
- Data model `ContextMenuItem`: stable id, scope/kind/method enums and derived fields
- Registry backend abstraction `RegistryBackend`, providing `Win32Registry` (real) and `FakeRegistry` (in-memory)
- Scanner: enumerates static menu items and Shell extension handlers by location table, computing disabled and location
- Disable/enable actions: shellex goes through `Shell Extensions\Blocked`, static goes through `LegacyDisable`; `apply` is idempotent and performs a unified permission pre-check before writing
- Change journal and "restore all in one click": only replays values recorded by this tool, and clears the journal after a successful restore
- tkinter GUI: scope switching, search filtering, multi-select disable/restore, change preview dialog, item details
- Administrator elevation: `is_admin()` detection and elevation restart via `ShellExecuteW(runas)`; when the machine-wide scope is not elevated, write operations are greyed out with a prompt
- Machine-wide scope scanning: `HKLM\SOFTWARE\Classes` and the 32-bit `Wow6432Node`
- Safety invariant tests: assert throughout the whole flow that registry keys are not deleted and other software's registry information is not touched
- UI smoke tests: build the window, disable → apply → restore back to the initial state, permission prompt state
- Startup script encoding regression test: `run.ps1` must have a UTF-8 BOM or be pure ASCII
- Feature grouping (`grouping.py`): groups entries of the same feature registered across multiple file types/locations by their context-menu display text
  into a `MenuGroup`; one top-level row in the UI = one feature, selecting it disables/restores in one click all
  entries of that feature under **all file types**, and after expanding they can still be controlled item by item by file type
- Feature aliases (`aliases.py`): sets aliases for features whose names cannot be resolved automatically (e.g. Baidu Netdisk, which only appears as `baidunetdisk` in the registry),
  persisted by grouping key to `%APPDATA%\RightMenuManager\aliases.json`, after which they can be searched, grouped, and toggled in one click by alias
- UI: added "Set alias…", "Expand all", "Collapse all" buttons; the feature row details list the
  exact registry paths for "which entries must be handled to turn it off"; when a search hits a feature name, all instances are kept, and when only a detail entry is hit, only that entry is kept
- Model adds `name_is_fallback`: marks that the name is merely a fallback to the key name, based on which the UI prompts "(unrecognized, an alias can be set)"
- Tests: added `test_grouping.py`, `test_aliases.py`, and expanded controller / scanner / UI smoke cases (131 → 170 items)
- "Show only non-Windows built-in" checkbox: added `system_items.py` and `ContextMenuItem.is_system`,
  determined by "where the referenced module resides" (Windows directory / `Program Files\Windows*` / bare system module names count as built-in;
  `DriverStore`, ordinary `Program Files` directories, `AppData` count as third-party; when there is no clue, it is not hidden).
  Filtering takes effect on entries before grouping, and the status bar shows the number hidden this time. Measured: of 411 items in the machine scope, 191 were judged built-in
- Tests: added `test_system_items.py`, and expanded controller / UI smoke cases (170 → 198 items)
- Portable packaging: added `package_portable.ps1`, which in one click picks out the files required to run (`run.cmd` / `run.ps1` /
  `.py` under `rightmenu\` / `.json` under `lang\` / `README.md`) into the distribution directory `release\`, automatically generates
  `VERSION.txt` (version number, packaging time, run requirements), with an optional `-Zip`; README adds a "Migrating to other machines" section,
  clarifying which files to bring and which not to

### Fixed
- Starting from a desktop shortcut or another working directory reported `No module named rightmenu`: `run.ps1` did not switch the working directory,
  while `python -m rightmenu` depends on the current directory being in `sys.path`. Now `Set-Location $PSScriptRoot` is done before startup, so
  it can start with the directory placed at any path
- Double-clicking `run.cmd` produced no window at all: `run.ps1` contained Chinese but had no UTF-8 BOM, so Windows PowerShell 5.1
  parsed it as ANSI, garbling the Chinese and breaking string quotes, and the whole script failed to parse. Now it is saved as UTF-8 (BOM),
  and `run.cmd` pauses on startup failure to display the error message
- No window appeared after "Restart as administrator": during elevation only `sys.argv[1:]` was passed through, but `-m rightmenu`
  is not in argv (when started as `python -m rightmenu`, `argv[0]` is the `__main__.py` path),
  so after elevation an empty interpreter was launched. Now `-m rightmenu` is explicitly added back and the working directory is set to the project root

### Notes
- The mechanism of `Shell Extensions\Blocked` using CLSIDs as value names has been confirmed by actual testing on this machine, see `docs/decisions/2026-10-04-blocked-list-mechanism-verified.md`
- Scan performance measured: about 231ms for 192 items in the user scope, about 412ms for 414 items in the machine scope; no throttling or lazy loading needed
