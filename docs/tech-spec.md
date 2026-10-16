> English | [简体中文](tech-spec.zh_CN.md)

# Windows Context Menu Manager — Technical Specification

purpose:      Disable/restore Windows Explorer context menu items in a non-destructive, reversible way, without modifying the registration information of other software itself
user:         Windows users who need to clean up their context menu but are unwilling to risk deleting registry keys
use-case:     list menu items (grouped by function) → choose scope → search/multi-select → preview and disable → restore a single item at any time or restore all with one click
architecture: layered: model / registry backend abstraction / scanner / system_items / grouping / aliases / actions / journal / elevation / i18n / ui (controller separated from the tkinter view)
stack:        Python 3.14 (C:\Python314\python.exe, ships with tkinter / Tk 9.0); standard library only (winreg, tkinter, json, ctypes, dataclasses, unittest)
entry:        python -m rightmenu (starts the GUI by default); python -m rightmenu --scan --scope user|machine (headless JSON output)
contract:     see "Contract" below; RegistryBackend and scan/plan/apply are stable interfaces
flow:         disable: selected items → plan (dry-run) → preview confirmation → apply (overall permission pre-check first, then write item by item) → record to journal
flow:         restore: restore all with one click → replay journal in reverse order → clear the journal on success
invariant:    no code path calls DeleteKey/DeleteKeyEx; only registry "values" are added or removed, registry "keys" are never deleted
invariant:    scan is read-only throughout and produces no writes whatsoever
invariant:    the menu item's own other values (verb/handler key) are not modified: default value, command, Icon, MUIVerb, etc. are kept as-is
invariant:    enable/restore deletes only the block values recorded by this tool or explicitly pointing at that item; it never accidentally deletes other people's data
invariant:    when not elevated, writes to HKLM must fail first and prompt afterwards; no partial changes may be left behind half-way
constraint:   the bundled Python 3.10 has no tkinter; run.cmd/run.ps1 automatically locate an interpreter with tkinter, and exit with a clear message if none is found
constraint:   run.ps1 must be saved as UTF-8 (BOM): Windows PowerShell 5.1 parses a .ps1 without a BOM as ANSI,
              so Chinese characters are garbled and script parsing breaks (this once caused double-clicking run.cmd to open no window); run.cmd stays pure ASCII
constraint:   no pip dependency is introduced, guaranteeing offline runnability and reproducibility
convention:   TDD (write a failing test before implementing); tests use the in-memory FakeRegistry implementation and never touch the real registry
convention:   file names are snake_case; all UI text is fetched via i18n.t(), never hard-coded Chinese; comments explain only "why"
convention:   documentation is bilingual: English is the default (`X.md`), Chinese lives alongside as `X.zh_CN.md`; every change must update both
milestone:    M1–M3 complete (see docs/ROADMAP.md)

## Disable mechanism

Menu items fall into two categories, each using its corresponding official non-destructive mechanism:

```
shell extension handler  (shellex\ContextMenuHandlers\<name>, default value = CLSID)
  disable: write REG_SZ under the corresponding hive's Shell Extensions\Blocked, value name = CLSID, data = empty
  enable:  delete that value

static verb  (shell\<verb>\command)
  disable: write a REG_SZ value LegacyDisable (empty data) under that verb key
  enable:  delete that value
```

Determining the CLSID: if the handler key's default value is of the form `{...}`, take it; if the default value is empty, take the "key name" —
system components often name handler keys with a GUID (e.g. `...\ContextMenuHandlers\{596AB062-...}`),
in which case the key name itself is the CLSID. When the CLSID cannot be resolved, the item cannot be handled safely via the block list, and plan records it as skipped.

Blocked key locations:

```
user    : HKCU\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked
machine : HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked
```

Mechanism evidence: using a CLSID as the value name under `Shell Extensions\Blocked` is exactly what Windows itself does; on this machine that HKLM key contains
an existing entry `{9421DD08-...}` (an Epson printer extension) whose format matches what this tool writes.
See `docs/decisions/2026-10-04-blocked-list-mechanism-verified.md`.

## Coverage and elevation

```
scope=user     read HKCU\Software\Classes\...          + HKCU Blocked      → no administrator needed
scope=machine  append HKLM\SOFTWARE\Classes\... (incl. Wow6432Node) + HKLM Blocked → administrator needed
```

When machine is chosen without elevation: the UI disables the write-operation buttons and offers "Restart as administrator",
relaunching itself with `ShellExecuteW(None, "runas", ...)`.

The elevated restart must explicitly add back `-m rightmenu` and set the working directory to the project root: when the program is started as
`python -m rightmenu`, `sys.argv[0]` is the path to `__main__.py`, and argv
does not contain `-m rightmenu`; passing argv through alone would leave the elevated interpreter idling (manifesting as
clicking "Restart as administrator" but no window ever appearing).

## System-built-in detection (the "show only non-Windows built-in" filter)

`ContextMenuItem.is_system` is computed by `system_items.classify()` during the scan,
based on "where the module referenced by the item lives", not on guessing the vendor. The evidence is taken from raw strings:
for static, `default value / MUIVerb / SubCommands / command / Icon`,
for shellex, `CLSID key default value / InprocServer32`.

```
absolute path (drive letter or UNC)
  under the Windows directory                → built-in
  under Program Files\Windows or Windows xxx\ → built-in (Defender / Photo Viewer / NT, etc.)
  under <Windows>\System32\DriverStore\      → third-party (driver package, e.g. NVIDIA)
  others (ordinary Program Files dir / AppData / other drives) → third-party
  multiple absolute paths present at once → if any one falls elsewhere, judge third-party
when there is no absolute path, fall back to the bare module-name whitelist (shell32.dll / rundll32.exe / notepad.exe …) → built-in
when there is no clue at all (e.g. only a display name ArmouryCrate, baidunetdisk)      → third-party (prefer showing more)
```

Key points:

- Paths must be extracted with a regex rather than split on whitespace: paths in places such as `InprocServer32` are **unquoted and contain spaces**,
  and splitting on words would truncate `C:\Program Files\Windows Defender\x.dll` into `C:\Program`.
- The absolute-path extension set must include not only modules but also `ps1/bat/cmd/…`: a
  system host plus out-of-tree payload such as `powershell.exe -File E:\x\y.ps1` must be judged third-party.
- Filtering applies to entries **before grouping** (`controller._base_items`), so system items
  mixed into a same-named function group are removed individually, and the in-group counts and state reflect the visible entries accordingly.

Measured (on this machine): of the 411 items in machine scope, 191 are judged built-in and 220 are kept;
of the 189 items in user scope, 0 are judged built-in (HKCU basically only holds third-party items).

## Scan location table (locations)

With `H = {user: HKCU\Software\Classes, machine: HKLM\SOFTWARE\Classes}` as the base, the following keys are scanned:

```
static verb (shell)                                extension handler (shellex\ContextMenuHandlers)
  H\*\shell                                         H\*\shellex\ContextMenuHandlers
  H\AllFilesystemObjects\shell                      H\AllFilesystemObjects\shellex\ContextMenuHandlers
  H\Directory\shell                                 H\Directory\shellex\ContextMenuHandlers
  H\Directory\Background\shell                      H\Directory\Background\shellex\ContextMenuHandlers
  H\Folder\shell                                    H\Folder\shellex\ContextMenuHandlers
  H\Drive\shell                                     H\Drive\shellex\ContextMenuHandlers
  H\LibraryFolder\shell                             H\LibraryFolder\shellex\ContextMenuHandlers
  H\DesktopBackground\shell                         H\DesktopBackground\shellex\ContextMenuHandlers
  H\SystemFileAssociations\<type>\shell             H\SystemFileAssociations\<type>\shellex\ContextMenuHandlers
  H\.<extension>\shell                              H\.<extension>\shellex\ContextMenuHandlers
```

machine scope additionally reads `HKLM\SOFTWARE\Classes\Wow6432Node\...` (the 32-bit view).

CLSID resolution: the default value of `H\CLSID\<clsid>\InprocServer32` → the DLL path (expanding environment variables such as `%SystemRoot%`);
the default value of `H\CLSID\<clsid>` → the friendly name.

## Display name resolution (resources.py)

What the registry stores is often not readable text but an indirect string `@dll,-id` (e.g. `@%SystemRoot%\system32\shell32.dll,-8506`);
shown directly, the user has no way to tell which menu it corresponds to. During the scan it is uniformly resolved into the text actually displayed in the context menu:

```
static : MUIVerb → default value → key name
shellex: readable default value → CLSID key default value (friendly name) → key name
```

- `resolve_text` hands `@dll,-id` to `SHLoadIndirectString` (calling shlwapi via ctypes) for resolution;
  plain text is returned as-is; an empty value returns None.
- `strip_accelerator` removes the accelerator marker `&`: `打开(&O)` → `打开(O)`, and `&&` is treated as a literal `&`.
- When resolution fails (DLL not installed, resource ID does not exist, CLSID key has no name), it falls back level by level, ultimately landing on the key name;
  the raw `@dll,-id` is never displayed as-is. The scan is read-only, and a resolution failure does not raise an exception.
- `scan(..., loader=...)` allows a resolver to be injected; tests use a fake loader to guarantee no dependency on local DLLs.

## Function grouping and aliases

The same context-menu function (e.g. "Upload to Baidu Netdisk") is often registered once for each of several file types/locations. What the user really wants
is to "turn this function off", not to click through every file type. The UI therefore adds a layer of **grouping by function** on top of the per-item view:

```
group_key(item)      = item.display_name.strip().casefold()      # grouping key: display text (case/whitespace insensitive)
group_items(items)   -> list[MenuGroup]                          # bucket by grouping key, groups with more instances first
MenuGroup            : {key, label, raw_name, items[]}
  .total             = number of instances in the group
  .state             = "enabled" | "disabled" | "partial"        # by proportion of disabled instances
  .locations/.kinds/.scopes/.dll_paths/.commands                 # deduplicated summary, for detail display
  .sample_detail     = prefer DLL, then command, for the list's "Command / DLL" column
  .has_alias         = label != raw_name
  .needs_alias       = all items in the group are name_is_fallback and no alias is set → UI hints "(registry name)"
```

The UI (`ui/app.py`) expresses this with two trees: **the top-level row = one function group**, and expanding it reveals the **per-item details**.
Selecting a function row → `selected_items()` expands to all entries in the group → one-click disable/restore then takes effect across file types;
selecting only a detail row → only that one entry is handled (preserving the original fine-grained capability). When `filter_groups(query)` matches a group name (including its alias), all
instances are kept; when it matches only a certain detail, only that entry is kept — this is used to answer "which entries are involved in turning this off".

Aliases (`aliases.py`): a few function texts are generated at runtime by a DLL, and the registry only contains something like `baidunetdisk`,
which cannot be resolved automatically. The user can set an alias for such a group, persisted **by group key** to
`%APPDATA%\RightMenuManager\aliases.json`; the alias only overrides the display name `label`, not the group key `key`,
so the same function is still grouped into the same group after a rescan. Aliases are not written to the registry — purely a local file.

```
AliasStore(path=None)   # in-memory only when path=None (for tests)
  .get(key) -> str|None
  .set(key, label)      # if label is blank, delete that alias; persist to disk immediately
  .as_dict()            # for group_items to override label
```

## Internationalization (i18n)

UI text, location names, change descriptions, and CLI help are all fetched via `i18n.t(key)`; Chinese is never hard-coded in the code.
Language set: `zh_CN`, `en` (these two first).

### Mechanism: built-in baseline + external language pack overlay

```
built-in CATALOG (i18n.py) : {"ui.title": {"zh_CN": "…", "en": "…"}, …}   # fallback, still runs if lang/ is lost
external language packs (lang/*.json): {"ui.title": "…", …}              # scanned and overlaid at startup
lookup order               : external pack[lang][key] → built-in[lang][key] → built-in["en"][key] → key itself
```

Rationale for the choice (full comparison in `docs/decisions/2026-10-12-i18n-mechanism.md`):

- gettext's `.po/.mo` requires a compilation step (the standard library does not include a `.mo` compiler), which conflicts with "zero pip dependencies, double-click and go";
- writing all translations into Python would mean adding a language requires changing code, and a translator's mistaken quote can prevent the whole program from starting;
- external JSON makes "adding a language = dropping in one `lang/xx.json`", without touching a single line of code, and a single corrupted file affects only that language.

### Language determination and persistence

```
startup : settings.json's language → GetUserDefaultUILanguage() detection → "en" fallback
switch  : UI dropdown → set_language() → write settings.json → controller.refresh() → rebuild the UI
CLI     : --lang {zh_CN,en} takes priority, then the saved value, then system detection
settings: %APPDATA%\RightMenuManager\settings.json    {"language": "zh_CN"}
```

`GetUserDefaultUILanguage()` returns a LANGID: Chinese variants (0x0804 Simplified / 0x0404 Traditional / 0x0C04 Hong Kong /
0x1004 Singapore / 0x1404 Macau) → `zh_CN`, everything else → `en`. If the ctypes call fails, it falls back to the environment variable, and finally to `en`.

### Translation boundary

```
translated    : all UI text, location names (locations), change descriptions (actions), preview text (controller),
                restore prefixes (journal), CLI help (__main__)
not translated: code comments and docstrings (kept in Chinese, an existing project convention)
                enum values scope/kind/method (machine-readable tokens are always English, so automated output is unaffected by language)
```

`locations.py`'s `SCAN_TARGETS` constant is changed into a `scan_targets()` function: location names are generated with `t()` at call time,
so after switching languages `controller.refresh()` just rescans to refresh them; the injection point of `scan(..., targets=...)` is unchanged,
and tests can still pass in custom targets.

In the JSON produced by `--scan`, `location` changes with the language (it is display text), while `scope/kind/method` are always English tokens.

### Missing keys and fault tolerance

- Missing key: return the key itself, never raise an exception — the UI does not crash because a translation is missing
- `lang/` directory missing: fall back entirely to the built-in catalog; functionality is unaffected
- Language pack JSON corrupted or not an object: ignore that file and continue starting
- Tests assert that the key sets of `zh_CN` and `en` in `CATALOG` are exactly identical, eliminating missing translations

### One trade-off

The journal's `description` has its language fixed at write time, so after switching languages old records remain in the original text — historical records should indeed keep their original form;
the `恢复：` / `撤销：` prefixes used at restore time are translated when displayed.

## Data model

```
@dataclass(frozen=True)
ContextMenuItem:
  id            : str          # sha1(hive + key_path), stable across sessions
  scope         : "user"|"machine"
  kind          : "static"|"shellex"
  location      : str          # human-readable location, e.g. "All Files", "Directory Background", ".txt files"
  key_path      : str          # full path of the registry key this item lives in
  display_name  : str          # resolved readable name (see "Display name resolution", falling back level by level to the key name)
  key_name      : str          # key name (verb name or handler name)
  command       : str|None     # static: command subkey default value
  clsid         : str|None     # shellex: CLSID
  dll_path      : str|None     # shellex: resolved DLL
  extended      : bool         # whether it is shown only on Shift+right-click
  disabled      : bool         # computed from whether the block value/LegacyDisable exists
  method        : "blocked"|"legacy_disable"|None   # currently effective disable method
  name_is_fallback : bool      # whether display_name only fell back to the key name (no readable text resolved)
  needs_admin   : bool
```

## Contract

```
class RegistryBackend(Protocol):
    def key_exists(self, path: str) -> bool
    def list_subkeys(self, path: str) -> list[str]
    def read_value(self, path: str, name: str|None) -> tuple[object, int] | None
    def write_value(self, path: str, name: str|None, value: object, vtype: int) -> None
    def delete_value(self, path: str, name: str|None) -> None
    def ensure_writable(self, path: str) -> None          # no change produced, permission pre-check only

scan(backend, scope, targets=SCAN_TARGETS, loader=None) -> list[ContextMenuItem]  # read-only; loader is for test injection
plan(items, target_disabled: bool) -> PlanResult          # pure function: {changes, skipped}
apply(backend, changes, journal=None) -> ApplyResult      # overall pre-check first, then execute item by item
```

`apply` is idempotent: when the target state has already been reached, `plan` produces no changes, and deleting a non-existent value is treated as success.

## Change journal and restore

```
journal file : %APPDATA%\RightMenuManager\journal.json
each record  : {ts, action, scope, key_path, value_name, item_id, description,
                had_previous, previous_value, previous_type}
write timing : appended after each disable / enable that actually changed state (no-ops are not recorded)
restore_all(): replay the journal in reverse order — if there was no value before writing, delete the value; if there was, write the original value back
cleanup timing: clear the journal only after a full successful restore; on failure, keep it so it can be retried
```

The semantics of "restore all with one click" is to return to the state before this tool made changes: only values recorded in the journal are touched,
and block entries set by other software or by the users themselves are never touched. Even if the user reinstalls this tool, as long as the journal still exists, a complete restoration is possible.

## Preview and safety

- Before applying, show the dry-run list: the exact registry paths and value names that will be written/deleted; execute only after the user confirms
- Before batch operations, the journal can be exported as a backup
- All failures (permissions, key does not exist, value occupied) are listed separately, without affecting the predetermined results of the remaining items

## Failure modes

```
no tkinter            → run.cmd suggests switching to C:\Python314\python.exe and exits (no stack trace)
no admin rights to write HKLM → PermissionError is caught, nothing is applied at all, UI suggests restarting elevated
key/value does not exist → recorded as skipped, no exception is raised to interrupt
value name contains illegal characters → skipped and recorded
32/64-bit view        → machine scope explicitly reads Wow6432Node
```

## File structure

```
rightmenu/
  __init__.py
  model.py         # ContextMenuItem, Scope, Kind, DisableMethod
  registry.py      # RegistryBackend protocol + Win32Registry (winreg implementation)
  fake_registry.py # FakeRegistry (in-memory dict, for tests and dry-run)
  locations.py     # scan location table (pure data)
  resources.py     # indirect string resolution: resolve_text / strip_accelerator / load_indirect_string
  grouping.py      # group functions by display text: group_key / MenuGroup / group_items
  aliases.py       # function alias persistence: AliasStore (%APPDATA%\RightMenuManager\aliases.json)
  scanner.py       # scan(backend, scope) -> list[ContextMenuItem]
  actions.py       # plan / apply / disable / enable
  journal.py       # change-log read/write + restore_all
  elevation.py     # is_admin() / relaunch_as_admin()
  i18n.py          # t()/set_language()/detect_language(); built-in CATALOG + external lang/*.json overlay
  ui/__init__.py
  ui/controller.py # presentation logic (no tkinter dependency, testable headless): filter/group/alias/plan/commit
  ui/app.py        # tkinter main window: function-group tree (parent = function, child = per-item detail)
  __main__.py      # entry point, supports --scan (headless JSON output) and starts the GUI by default
tests/
  test_model.py  test_registry.py  test_scanner.py  test_actions.py
  test_journal.py  test_safety.py  test_elevation.py  test_controller.py
  test_resources.py  # indirect string resolution and accelerator stripping
  test_grouping.py   # grouping by function: merge/state/alias override/detail summary
  test_aliases.py    # alias read/write and UTF-8 persistence, corrupted-file tolerance
  test_ui_smoke.py   # UI smoke: build/disable-restore/permission prompt/function-group tree (skipped when tkinter is absent)
  test_i18n.py       # language detection LANGID mapping, entry fallback chain, alignment of the two catalogs' keys, settings read/write, language-pack fault tolerance
lang/
  zh_CN.json       # external language pack (flat key -> text); shipped with the distribution, consistent with the built-in CATALOG
  en.json
docs/
  tech-spec.md     # this file (English, default)
  tech-spec.zh_CN.md   # Chinese twin of this file
  ROADMAP.md
  ROADMAP.zh_CN.md     # Chinese twin
  decisions/       # key mechanism evidence and decision records
                   # (each record ships as English `X.md` + Chinese `X.zh_CN.md`)
run.cmd            # double-click launcher: forwards to run.ps1
run.ps1            # locates an interpreter with tkinter and launches it
Makefile           # test / run / scan / scan-machine tasks
README.md  README.zh_CN.md  CHANGELOG.md  CHANGELOG.zh_CN.md  .gitignore
```

## Tests (how to prove it)

```
1. test_safety : asserts across the whole flow that backend never calls delete_key; the verb/handler key's other values stay unchanged
2. test_actions: disable shellex → a REG_SZ named after the CLSID appears under Blocked; it disappears after enable
3. test_actions: disable static → LegacyDisable appears under the verb key; it disappears after enable
4. test_scanner: seed FakeRegistry → correctly identifies both item kinds, correctly computes disabled and location;
   display-name priority (MUIVerb / indirect string / GUID key name) and level-by-level fallback on resolution failure
5. test_journal: restore_all deletes only the recorded values, in reverse order, and after restore is byte-for-byte identical to the initial state
6. test_safety : no elevation + machine scope → raises a clear exception and FakeRegistry has no writes at all
7. test_actions: apply is idempotent — two consecutive applications yield the same result
8. test_ui_smoke: build a real window with FakeRegistry, run disable→apply→restore_all with no residue;
   when simulating non-elevated + machine scope, the write-operation buttons are disabled and an elevation entry point appears
9. test_grouping / test_controller / test_ui_smoke: a function registered in multiple locations is merged into one row;
   selecting the function row and disabling it in one click covers all instances; a search matching only a detail keeps only that entry; an alias overrides the display name and is searchable
10. measured: `--scan --scope machine` outputs real entries (411 items on this machine); the `Blocked` mechanism conclusion is in docs/decisions/
11. test_i18n  : language detection LANGID mapping (Chinese variants → zh_CN), value fallback chain, the two `CATALOG` key sets
    fully aligned, external pack overlay and fault tolerance (corrupted/non-object/half-written), settings read/write and priority, `lang/*.json` with no drift from the built-in
```

Acceptance command: `make test` (i.e. `C:\Python314\python.exe -m unittest discover -s tests`).

## Measured results

- Scan performance: 189 items in user scope, 411 items in machine scope; no sense of blocking, so no rate limiting or lazy loading is needed.
- Display names: in the scan results, all but 1 item (whose CLSID key itself has no name, `{474C98EE-...}`) resolve to readable text;
  before the fix there were a large number of raw `@dll,-id` strings and bare GUIDs. shellex items now resolve a CLSID 100% of the time (taking the key name when the default value is empty),
  so all of them can be disabled via the block list — previously such items were judged skipped by plan because `clsid is None`.
- Wow6432Node: on this machine that key exists but has no shell menu items, so 0 of the machine scan entries come from the 32-bit view, which is the correct result.
- `restore_all` leaves block values "not written by this tool" untouched by default; cleaning up other people's entries would require a separate explicit feature.

## Non-goals / deferred

```
- no "true deletion of registry keys" (the user has confirmed only reversible disable/restore)
- no creating custom menu items / drag-and-drop reordering
- i18n: zh_CN / en are supported, via "built-in baseline + external language pack overlay" (see the "Internationalization (i18n)" section);
  more languages just need a `lang/<code>.json` add-on, no code change required
- no installer, no code signing
- DLL publisher and icon resolution are nice-to-haves, not scheduled
```