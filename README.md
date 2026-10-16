> English | [简体中文](README.zh_CN.md)

# Windows Context Menu Manager

Manage Windows Explorer context menu entries in a **non-destructive, reversible** way.

## What problem it solves

Many programs stuff entries into the context menu. The common approach is to delete registry keys directly, but that has costs:
- it breaks the program's own registration information, so the program may error out or write it back;
- it affects other users;
- once you want to restore it, the original content can no longer be found.

This tool instead uses Windows' official **blocking mechanism**, only adding or removing registry **values**, never deleting **keys**:

| Menu item type | Location | How it is disabled | How it is restored |
|---|---|---|---|
| Shell extension handler (with CLSID) | `shellex\ContextMenuHandlers` | Write a value named after the CLSID under `Shell Extensions\Blocked` | Delete that value |
| Static menu item | `shell\<verb>\command` | Write a `LegacyDisable` value under that key | Delete that value |

As a result: other programs' registration information is preserved as-is, programs register their menu items as usual, and everything can be restored with one click at any time.

## Quick start

```
run.cmd
```

`run.cmd` automatically locates a Python interpreter that has tkinter. You can also specify one directly:

```
C:\Python314\python.exe -m rightmenu
```

Headless mode (outputs JSON, handy for troubleshooting and automation):

```
C:\Python314\python.exe -m rightmenu --scan --scope user
C:\Python314\python.exe -m rightmenu --scan --scope machine
```

## Usage steps

1. **Choose a scope** (top-left of the window):
   - `Current user only (no administrator needed)`: only reads/modifies `HKCU`, does not affect other users, and is always available.
   - `Current user + entire machine (administrator needed)`: additionally includes `HKLM` (including 32-bit `Wow6432Node`) entries.
     Without elevation, write operations are greyed out and a "Restart as administrator" button appears; clicking it relaunches itself through UAC.
2. **The list is merged by function**: the top level shows one row per context-menu function (e.g. "Upload to Baidu Netdisk").
   The "Location" column shows how many locations it covers, and the "Type / Entries" column shows how many entries there are in total.
   Expanding a row reveals the **per-entry details** (each entry corresponds to one file type/location), which can be toggled individually by file type.
   Double-click any row to view details: a function row lists the exact registry paths of "which entries must be handled to turn it off".
   The displayed name is the **actual text seen on the context menu**: common resource references in the registry
   (such as `@shell32.dll,-8506`) are resolved into readable text, so you never see `@dll,-id` or a bare GUID.
3. **Turn a function on/off with one click (across file types)**: select function rows (`Ctrl`/`Shift` for multi-select),
   then click "Disable selected" to turn off all entries of that function under **all file types** at once; click "Restore selected" to restore them.
   Selecting only detail rows affects only that one entry — the original fine-grained per-file-type control is still preserved.
4. **Unrecognizable name? Set an alias**: some functions (such as Baidu Netdisk) have their text generated at runtime by a DLL,
   so the registry only contains something like `baidunetdisk`; the interface marks this with "(registry name)" to indicate that the name comes from the registry key name
   and may differ from the actual menu text. Select that function row, click "Set alias…" to give it a recognizable name,
   and afterwards you can search, merge, and toggle it by alias. Aliases are stored in `%APPDATA%\RightMenuManager\aliases.json`.
5. **Search**: enter a name, alias, location, command, or DLL path fragment in the "Search" box; the list filters in real time and automatically expands matching items.
   When a function name matches, all instances of that function are kept; when only a detail entry matches, only that entry is kept,
   making it easy to confirm "which entries are involved in turning off this function".
6. **Hide Windows built-ins**: check "Hide Windows built-ins" in the toolbar to hide the menu items registered by
   Windows itself (BitLocker, Pin to Quick access, Send to, New, Compressed folder, Windows Defender, etc.),
   leaving only entries installed by third-party software, so you can focus on "what do I want to clean up". The status bar shows how many entries were hidden this time.
   The criterion is "where the module referenced by the item resides": modules located in the Windows directory or the `Program Files\Windows*` system component
   directories count as built-in; modules located in `DriverStore` (vendor driver packages, such as NVIDIA), ordinary `Program Files` directories,
   `AppData`, and similar count as third-party; items with only a bare module name (such as `shell32.dll`, `rundll32.exe`) are also treated as built-in.
   Items for which no clue can be obtained are **not** hidden — it is better to show more than to mistakenly hide an item you installed yourself.
7. **Preview before applying**: any disable/restore pops up a **change preview** listing, item by item, the exact registry paths and value names that will be written/deleted;
   it is executed only after you confirm.
8. **Restore everything with one click**: click "Restore all changes" to return, according to the change journal, all items changed by this tool to
   the state they were in before this tool intervened. Blocking entries set by other programs or by the user themselves are not touched.

The change journal is located at `%APPDATA%\RightMenuManager\journal.json`. Even if the user reinstalls this tool, as long as the journal is still there,
a complete restore is possible.

## Interface language

Built-in **Simplified Chinese** and **English**, defaulting to **following the system language** (Chinese system → Simplified Chinese, otherwise → English).

- **Switch**: the "Language:" drop-down in the toolbar takes effect immediately upon selection; the choice is recorded in
  `%APPDATA%\RightMenuManager\settings.json` and used again on the next launch.
- **Command line**: `--lang zh_CN` / `--lang en` specify the language for this run, with priority over the saved choice.
- **Add a language without changing code**: just drop a `<language code>.json` into the program directory's `lang\`,
  and the file name is the language code (e.g. `lang\fr.json` → "Français" appears in the interface).

A language pack is a flat `key → text` JSON; you may translate only some keys, and untranslated ones automatically fall back to English:

```json
{
  "app.title": "Gestionnaire de menus contextuels Windows",
  "btn.disable": "Désactiver la sélection"
}
```

To see which keys need translating, you can copy `lang\zh_CN.json` directly (it is the authoritative source). Fault-tolerance principles:
a missing key displays the key name itself, and a corrupted language pack or deleting the whole `lang\` does not affect the program's operation — the interface will never crash because of it;
saving the file as "UTF-8 with BOM" also reads correctly.

## Development

```
make test          # run unit tests
make run           # launch the graphical interface
make scan          # headless scan (current user)
make scan-machine  # headless scan (including entire machine)
```

If you don't have `make`, use the equivalent PowerShell commands directly:

```
C:\Python314\python.exe -m unittest discover -s tests -v
```

## Safety commitments

- Does not call `DeleteKey` / `DeleteKeyEx`, and never deletes registry keys;
- Does not modify the menu item's own `command`, `Icon`, name, or other values;
- Scanning is entirely read-only;
- Every change is written to `%APPDATA%\RightMenuManager\journal.json`, supporting "Restore all changes";
- A dry-run preview is provided before applying, clearly listing the registry paths and value names that will be changed;
- A unified permission pre-check is performed before batch writes; if any single location is not writable, the whole operation is aborted, leaving no partial changes behind.

## Requirements

- Windows 10/11;
- Python 3.13+ with tkinter (development and verification use `C:\Python314\python.exe`, which ships with Tk 9.0);
- Standard library dependencies only, no pip install steps, and it runs offline.

## Porting to other machines

The program does not depend on an installation and does not write to system directories; the whole directory can be placed at any path (a USB drive, the desktop, or another drive letter all work).
`run.ps1` switches itself to the script's own directory, so launching from a shortcut or another directory will not go wrong.

Generate a clean distribution copy (output to `release\` by default):

```
powershell -ExecutionPolicy Bypass -File package_portable.ps1
powershell -ExecutionPolicy Bypass -File package_portable.ps1 -Destination D:\RightMenuManager -Zip
```

**Files that must be ported along** (25 in total, the script picks them automatically):

| Content | Description |
|---|---|
| `run.cmd`, `run.ps1` | Launch entry points; `run.cmd` works with a double-click |
| All `.py` under `rightmenu\` | The program itself (the `ui\` subdirectory contains the interface) |
| All `.json` under `lang\` | External language packs (optional; it still runs without them thanks to the built-in fallback directory); adding a language just means dropping a file here |
| `README.md`, `README.zh_CN.md` | Optional; the English and Chinese usage docs, convenient for looking up usage on the target machine |
| `VERSION.txt` | Release marker: version number, packaging time, runtime requirements (generated automatically by the script) |

**No need to port**: `tests\`, `docs\`, `Makefile`, `CHANGELOG.md`, `.gitignore`,
`__pycache__\` and `*.pyc` (bytecode caches for different Python versions; copying them over is useless and may even interfere).
`fake_registry.py` is only for testing, but it lives inside the package and its size is negligible, so bringing it along is less trouble.

**Do not port `%APPDATA%\RightMenuManager\`** (`journal.json` / `aliases.json` / `settings.json`):
that is the **local machine's** registry change record and personal preferences; after copying it to another machine, clicking "Restore all changes" would try to restore changes that
do not exist on that machine. When changing machines, start recording from scratch.

Target machine requirements: Windows 10/11 + Python 3.13+ with tkinter; just double-click `run.cmd`.

## License

This project is released under the **GNU General Public License v3.0 (GPL-3.0)**; the full text is in [LICENSE](LICENSE).

You are free to use, modify, and distribute this software (including for commercial purposes); however, if you distribute a modified version,
you must likewise license it under GPL-3.0 and publish the complete source code (copyleft). In other words: use and secondary development are welcome,
but you **cannot close-source and resell this project's code** — anyone who receives your distributed version has the right to obtain its source code for free.

```
Copyright (C) 2026 w0i0c0o

This program is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this
program.  If not, see <https://www.gnu.org/licenses/>.
```

## Documentation

This file is the **English (default)** documentation; the Chinese version is [README.zh_CN.md](README.zh_CN.md).

- Technical specification: [English (default)](docs/tech-spec.md) · [Chinese](docs/tech-spec.zh_CN.md)
- Roadmap: [English (default)](docs/ROADMAP.md) · [Chinese](docs/ROADMAP.zh_CN.md)
- Decision records: `docs/decisions/` (each record is English `X.md` + Chinese `X.zh_CN.md`)
- Changelog: [English (default)](CHANGELOG.md) · [Chinese](CHANGELOG.zh_CN.md)

**Documentation convention**: all documentation is bilingual. English is the default (`X.md`) and Chinese
lives alongside it as `X.zh_CN.md`; every change must update both, so the two languages never drift apart.