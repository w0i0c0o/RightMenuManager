> [English](tech-spec.md) | 简体中文

# Windows 右键菜单管理器 — 技术规格

purpose:      以非破坏、可逆的方式禁用/恢复 Windows 资源管理器右键菜单项，且不修改其他软件自身的注册信息
user:         需要清理右键菜单、又不愿冒险删注册表键的 Windows 用户
use-case:     列出菜单项（按功能归并）→ 选择范围 → 搜索/多选 → 预览并禁用 → 随时恢复单个或一键恢复全部
architecture: 分层：model / registry 后端抽象 / scanner / system_items / grouping / aliases / actions / journal / elevation / i18n / ui（controller 与 tkinter 视图分离）
stack:        Python 3.14（C:\Python314\python.exe，自带 tkinter / Tk 9.0）；仅标准库（winreg, tkinter, json, ctypes, dataclasses, unittest）
entry:        python -m rightmenu（默认启动 GUI）；python -m rightmenu --scan --scope user|machine（headless 输出 JSON）
contract:     见下方「契约」；RegistryBackend 与 scan/plan/apply 是稳定接口
flow:         disable: 选中项 → plan(dry-run) → 预览确认 → apply(先整体权限预检，再逐条写入) → 记入 journal
flow:         restore: 一键恢复全部 → journal 逆序回放 → 成功则清空 journal
invariant:    任何代码路径都不调用 DeleteKey/DeleteKeyEx，只增删注册表「值」，绝不删「键」
invariant:    scan 全程只读，不产生任何写入
invariant:    不修改菜单项自身（verb/handler 键）的其它值：默认值、command、Icon、MUIVerb 等原样保留
invariant:    enable/恢复只删除本工具记录过或明确指向该项的屏蔽值，不误删他人数据
invariant:    未提权时对 HKLM 的写入必须先失败、后提示，不得半途留下部分改动
constraint:   内置 Python 3.10 无 tkinter；run.cmd/run.ps1 自动定位带 tkinter 的解释器，找不到则明确提示退出
constraint:   run.ps1 必须以 UTF-8 (BOM) 保存：Windows PowerShell 5.1 对无 BOM 的 .ps1 按 ANSI 解析，
              含中文会乱码并破坏脚本解析（曾导致双击 run.cmd 无窗口）；run.cmd 保持纯 ASCII
constraint:   不引入任何 pip 依赖，保证离线可跑、可复现
convention:   TDD（先写失败测试再实现）；测试用 FakeRegistry 内存实现，不碰真实注册表
convention:   文件名 snake_case；界面文案一律经 i18n.t() 取词，不硬编码中文；注释仅解释「为什么」
convention:   文档双语：英文为默认（`X.md`），中文并列（`X.zh_CN.md`）；每次改动需同步更新两份
milestone:    M1–M3 已完成（见 docs/ROADMAP.md）

## 禁用机制

菜单项分两类，各用对应的官方非破坏机制：

```
shell 扩展处理器  (shellex\ContextMenuHandlers\<名称>，默认值 = CLSID)
  disable: 在对应 hive 的 Shell Extensions\Blocked 写入 REG_SZ，值名 = CLSID，数据 = 空
  enable:  删除该值

static 静态动词  (shell\<verb>\command)
  disable: 在该 verb 键下写入 REG_SZ 值 LegacyDisable（空数据）
  enable:  删除该值
```

CLSID 的确定：处理器键默认值若形如 `{...}` 即取之；默认值为空时取「键名」——
系统组件常以 GUID 命名 handler 键（如 `...\ContextMenuHandlers\{596AB062-...}`），
此时键名即 CLSID。CLSID 解析不出来时该项无法用屏蔽清单安全处理，plan 会记为 skipped。

Blocked 键位置：

```
user    : HKCU\Software\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked
machine : HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked
```

机制实证：`Shell Extensions\Blocked` 以 CLSID 作值名正是 Windows 自身做法，本机 HKLM 该键下存在
既有条目 `{9421DD08-...}`（Epson 打印机扩展），格式与本工具写入一致。
详见 `docs/decisions/2026-10-04-blocked-list-mechanism-verified.md`。

## 覆盖范围与提权

```
scope=user     读取 HKCU\Software\Classes\...          + HKCU Blocked      → 无需管理员
scope=machine  追加 HKLM\SOFTWARE\Classes\...（含 Wow6432Node） + HKLM Blocked → 需要管理员
```

未提权却选择 machine 时：界面禁用写操作按钮，并提供「以管理员身份重启」，
用 `ShellExecuteW(None, "runas", ...)` 重新拉起自身。

提权重启必须显式补回 `-m rightmenu` 并把工作目录设为项目根：程序以
`python -m rightmenu` 启动时 `sys.argv[0]` 是 `__main__.py` 的路径，argv 中
并不包含 `-m rightmenu`，只透传 argv 会让提权后的解释器空转（表现为
点了「以管理员身份重启」却不出现窗口）。

## 系统自带判定（「只看非 Windows 自带」过滤）

`ContextMenuItem.is_system` 由 `system_items.classify()` 在扫描时算出，
依据是「该项引用的模块落在哪里」，不猜厂商。证据取原始字符串：
static 取 `默认值 / MUIVerb / SubCommands / command / Icon`，
shellex 取 `CLSID 键默认值 / InprocServer32`。

```
绝对路径（盘符或 UNC）
  在 Windows 目录下                          → 自带
  在 Program Files\Windows 或 Windows xxx\   → 自带（Defender / Photo Viewer / NT 等）
  在 <Windows>\System32\DriverStore\ 下      → 第三方（驱动包，如 NVIDIA）
  其它（Program Files 普通目录 / AppData / 其他盘）→ 第三方
  同时存在多个绝对路径 → 只要有一个落在别处就判第三方
无绝对路径时，退回裸模块名白名单（shell32.dll / rundll32.exe / notepad.exe …）→ 自带
无任何线索（如只有显示名 ArmouryCrate、baidunetdisk）      → 第三方（宁可多显示）
```

要点：

- 路径必须用正则抽取而不是按空白切词：`InprocServer32` 等处的路径**不带引号且含空格**，
  切词会把 `C:\Program Files\Windows Defender\x.dll` 截断成 `C:\Program`。
- 绝对路径的扩展名除模块外还要含 `ps1/bat/cmd/…`：`powershell.exe -File E:\x\y.ps1`
  的系统宿主 + 站外载荷必须判为第三方。
- 过滤在**归并之前**对条目生效（`controller._base_items`），因此同名功能组里
  混着的系统项会被单独剔除，组内计数与状态随之反映可见条目。

实测（本机）：machine 范围 411 项中 191 项判为自带、220 项保留；
user 范围 189 项中 0 项判为自带（HKCU 基本只装第三方项）。

## 扫描位置表（locations）

以 `H = {user: HKCU\Software\Classes, machine: HKLM\SOFTWARE\Classes}` 为基，扫描以下键：

```
静态动词 (shell)                                  扩展处理器 (shellex\ContextMenuHandlers)
  H\*\shell                                         H\*\shellex\ContextMenuHandlers
  H\AllFilesystemObjects\shell                      H\AllFilesystemObjects\shellex\ContextMenuHandlers
  H\Directory\shell                                 H\Directory\shellex\ContextMenuHandlers
  H\Directory\Background\shell                      H\Directory\Background\shellex\ContextMenuHandlers
  H\Folder\shell                                    H\Folder\shellex\ContextMenuHandlers
  H\Drive\shell                                     H\Drive\shellex\ContextMenuHandlers
  H\LibraryFolder\shell                             H\LibraryFolder\shellex\ContextMenuHandlers
  H\DesktopBackground\shell                         H\DesktopBackground\shellex\ContextMenuHandlers
  H\SystemFileAssociations\<类型>\shell              H\SystemFileAssociations\<类型>\shellex\ContextMenuHandlers
  H\.<扩展名>\shell                                  H\.<扩展名>\shellex\ContextMenuHandlers
```

machine 范围额外读 `HKLM\SOFTWARE\Classes\Wow6432Node\...`（32 位视图）。

CLSID 解析：`H\CLSID\<clsid>\InprocServer32` 默认值 → DLL 路径（展开 `%SystemRoot%` 等环境变量）；
`H\CLSID\<clsid>` 默认值 → 友好名。

## 显示名称解析（resources.py）

注册表里存的往往不是可读文字，而是间接字符串 `@dll,-id`（如 `@%SystemRoot%\system32\shell32.dll,-8506`），
直接显示用户完全认不出对应哪个菜单。扫描时统一解析成实际右键显示的文字：

```
static : MUIVerb → 默认值 → 键名
shellex: 可读的默认值 → CLSID 键默认值（友好名）→ 键名
```

- `resolve_text` 把 `@dll,-id` 交给 `SHLoadIndirectString`（ctypes 调 shlwapi）解析；
  普通文本原样返回；空值返回 None。
- `strip_accelerator` 去掉快捷键标记 `&`：`打开(&O)` → `打开(O)`，`&&` 视为字面量 `&`。
- 解析不出（DLL 未安装、资源号不存在、CLSID 键无名称）时逐级回退，最终落到键名；
  绝不把 `@dll,-id` 原样展示。扫描只读，解析失败不抛异常。
- `scan(..., loader=...)` 可注入解析器，测试用假 loader 保证不依赖本机 DLL。

## 功能归并（grouping）与别名（aliases）

同一个右键功能（如「上传到百度网盘」）往往在多个文件类型/位置各注册一份。用户真正想做的
是「把这个功能关掉」，而不是逐个文件类型去点。因此界面在逐项视图之上加了一层**按功能归并**：

```
group_key(item)      = item.display_name.strip().casefold()      # 归并键：显示文字（忽略大小写/空白）
group_items(items)   -> list[MenuGroup]                          # 按归并键分桶，实例多的组排在前
MenuGroup            : {key, label, raw_name, items[]}
  .total             = 组内实例数
  .state             = "enabled" | "disabled" | "partial"        # 按已禁用实例占比
  .locations/.kinds/.scopes/.dll_paths/.commands                 # 去重汇总，供详情展示
  .sample_detail     = 优先取 DLL，其次命令，供列表「命令 / DLL」列
  .has_alias         = label != raw_name
  .needs_alias       = 组内所有项 name_is_fallback 且未设别名 → 界面提示「（注册表名）」
```

界面（`ui/app.py`）用两棵树表达：**顶层一行 = 一个功能组**，展开后是**逐项明细**。
选中功能行 → `selected_items()` 展开为组内全部条目 → 一键禁用/恢复即跨文件类型生效；
只选明细行 → 只处理那一条（保留原细粒度能力）。`filter_groups(query)` 命中组名（含别名）时
保留全部实例，仅命中某条明细时只保留该条，用于回答「要关掉它涉及哪几条」。

别名（`aliases.py`）：少数功能文字由 DLL 在运行时生成，注册表里只有 `baidunetdisk` 之类，
无法自动解析。用户可为该组设置别名，**按归并键**持久化到
`%APPDATA%\RightMenuManager\aliases.json`；别名只覆盖展示名 `label`，不改归并键 `key`，
因此同一功能在重扫后仍归为同组。别名不写注册表，纯本地文件。

```
AliasStore(path=None)   # path=None 时仅内存（测试用）
  .get(key) -> str|None
  .set(key, label)      # label 空白则删除该别名；随即落盘
  .as_dict()            # 供 group_items 覆盖 label
```

## 多语言（i18n）

界面文案、位置名称、变更描述与 CLI 帮助一律经 `i18n.t(key)` 取词，代码里不硬编码中文。
语言集合：`zh_CN`、`en`（先做这两种）。

### 机制：内置基准 + 外部语言包叠加

```
内置 CATALOG（i18n.py） : {"ui.title": {"zh_CN": "…", "en": "…"}, …}   # 保底，lang/ 丢失也能跑
外部语言包（lang/*.json）: {"ui.title": "…", …}                        # 启动时扫描并叠加
取值顺序                : 外部包[lang][key] → 内置[lang][key] → 内置["en"][key] → key 本身
```

选型理由（完整对比见 `docs/decisions/2026-10-12-i18n-mechanism.md`）：

- gettext 的 `.po/.mo` 需要编译步骤（标准库不含 `.mo` 编译器），与「零 pip 依赖、双击即用」冲突；
- 译文全写进 Python 则新增语言必须改代码，翻译者写错引号会让整个程序起不来；
- 外部 JSON 让「加一门语言 = 丢一个 `lang/xx.json`」，不动一行代码，且单个文件损坏只影响该语言。

### 语言决定与持久化

```
启动    : settings.json 的 language → GetUserDefaultUILanguage() 检测 → "en" 兜底
切换    : 界面下拉框 → set_language() → 写 settings.json → controller.refresh() → 重建界面
CLI     : --lang {zh_CN,en} 优先，其次保存值，其次系统检测
settings: %APPDATA%\RightMenuManager\settings.json    {"language": "zh_CN"}
```

`GetUserDefaultUILanguage()` 返回 LANGID：中文各变体（0x0804 简体 / 0x0404 繁体 / 0x0C04 香港 /
0x1004 新加坡 / 0x1404 澳门）→ `zh_CN`，其余 → `en`。ctypes 调用失败时退回环境变量，最终兜底 `en`。

### 翻译边界

```
翻译   : 界面全部文案、位置名称（locations）、变更描述（actions）、预览文本（controller）、
         恢复前缀（journal）、CLI 帮助（__main__）
不翻译 : 代码注释与 docstring（保持中文，项目既有约定）
         枚举值 scope/kind/method（机器可读 token 恒为英文，自动化输出不受语言影响）
```

`locations.py` 的 `SCAN_TARGETS` 常量改为 `scan_targets()` 函数：位置名在调用时用 `t()` 生成，
因此切语言后 `controller.refresh()` 重扫即可刷新；`scan(..., targets=...)` 的注入点不变，
测试仍可传入自定义 targets。

`--scan` 的 JSON 中 `location` 随语言变化（它是展示文案），`scope/kind/method` 恒为英文 token。

### 缺词与容错

- 缺 key：返回 key 本身，绝不抛异常 —— 界面不因翻译缺失而崩
- `lang/` 目录缺失：完全走内置目录，功能不受影响
- 语言包 JSON 损坏或不是对象：忽略该文件继续启动
- 测试断言 `CATALOG` 中 `zh_CN` 与 `en` 的 key 集合完全一致，杜绝漏译

### 一处取舍

journal 里的 `description` 在写入时定语言，切换语言后旧记录仍是原文 —— 历史记录本就该保留原貌；
恢复时的 `恢复：` / `撤销：` 前缀则在显示时翻译。

## 数据模型

```
@dataclass(frozen=True)
ContextMenuItem:
  id            : str          # sha1(hive + key_path)，跨会话稳定
  scope         : "user"|"machine"
  kind          : "static"|"shellex"
  location      : str          # 人类可读位置，如「所有文件」「目录背景」「.txt 文件」
  key_path      : str          # 该项所在注册表键全路径
  display_name  : str          # 已解析的可读名称（见「显示名称解析」，逐级回退到键名）
  key_name      : str          # 键名（verb 名或 handler 名）
  command       : str|None     # static：command 子键默认值
  clsid         : str|None     # shellex：CLSID
  dll_path      : str|None     # shellex：解析出的 DLL
  extended      : bool         # 是否仅在 Shift+右键 显示
  disabled      : bool         # 由屏蔽值/LegacyDisable 是否存在计算得出
  method        : "blocked"|"legacy_disable"|None   # 当前生效的禁用方式
  name_is_fallback : bool      # display_name 是否只是回退到键名（没解析出可读文字）
  needs_admin   : bool
```

## 契约

```
class RegistryBackend(Protocol):
    def key_exists(self, path: str) -> bool
    def list_subkeys(self, path: str) -> list[str]
    def read_value(self, path: str, name: str|None) -> tuple[object, int] | None
    def write_value(self, path: str, name: str|None, value: object, vtype: int) -> None
    def delete_value(self, path: str, name: str|None) -> None
    def ensure_writable(self, path: str) -> None          # 不产生改动，只做权限预检

scan(backend, scope, targets=SCAN_TARGETS, loader=None) -> list[ContextMenuItem]  # 只读；loader 供测试注入
plan(items, target_disabled: bool) -> PlanResult          # 纯函数：{changes, skipped}
apply(backend, changes, journal=None) -> ApplyResult      # 先整体预检，再逐条执行
```

`apply` 幂等：目标状态已达成时 `plan` 不产出变更，且删除不存在的值视为成功。

## 变更日志与恢复

```
journal 文件 : %APPDATA%\RightMenuManager\journal.json
每条记录     : {ts, action, scope, key_path, value_name, item_id, description,
                had_previous, previous_value, previous_type}
写入时机     : 每次 disable / enable 真正改变了状态后追加（空操作不记录）
restore_all(): 按 journal 逆序回放 —— 写入前无值则删值，有值则回写原值
清理时机     : 恢复全部成功后才清空 journal；有失败则保留以便重试
```

「一键恢复全部」的语义是回到本工具改动之前的状态：只动 journal 记录过的值，
其他软件或用户自己设置的屏蔽项一律不碰。即使用户重装本工具，只要 journal 还在，就能完整还原。

## 预览与安全

- 应用前展示 dry-run 清单：将写入/删除的确切注册表路径与值名，用户确认后才执行
- 批量操作前可将 journal 导出备份
- 所有失败（权限、键不存在、值被占）单独列出，不影响其余项的既定结果

## 失败模式

```
无 tkinter            → run.cmd 提示改用 C:\Python314\python.exe 并退出（不报栈）
无管理员权限写 HKLM   → PermissionError 被捕获，整体不落地，界面提示提权重启
键/值不存在           → 记为 skipped，不抛异常中断
值名含非法字符        → 跳过并记录
32/64 位视图          → machine 范围显式读 Wow6432Node
```

## 文件结构

```
rightmenu/
  __init__.py
  model.py         # ContextMenuItem, Scope, Kind, DisableMethod
  registry.py      # RegistryBackend 协议 + Win32Registry（winreg 实现）
  fake_registry.py # FakeRegistry（内存字典，供测试与 dry-run）
  locations.py     # 扫描位置表（纯数据）
  resources.py     # 间接字符串解析：resolve_text / strip_accelerator / load_indirect_string
  grouping.py      # 按显示文字归并功能组：group_key / MenuGroup / group_items
  aliases.py       # 功能别名持久化：AliasStore（%APPDATA%\RightMenuManager\aliases.json）
  scanner.py       # scan(backend, scope) -> list[ContextMenuItem]
  actions.py       # plan / apply / disable / enable
  journal.py       # 变更日志读写 + restore_all
  elevation.py     # is_admin() / relaunch_as_admin()
  i18n.py          # t()/set_language()/detect_language()；内置 CATALOG + 外部 lang/*.json 叠加
  ui/__init__.py
  ui/controller.py # 展示逻辑（不依赖 tkinter，可无界面测试）：筛选/分组/别名/plan/commit
  ui/app.py        # tkinter 主窗口：功能组树（父=功能，子=逐项明细）
  __main__.py      # 入口，支持 --scan（headless 输出 JSON）与默认启动 GUI
tests/
  test_model.py  test_registry.py  test_scanner.py  test_actions.py
  test_journal.py  test_safety.py  test_elevation.py  test_controller.py
  test_resources.py  # 间接字符串解析与快捷键标记
  test_grouping.py   # 按功能归并：合并/状态/别名覆盖/明细汇总
  test_aliases.py    # 别名读写与 UTF-8 落盘、损坏文件容错
  test_ui_smoke.py   # 界面冒烟：构建/禁用恢复/权限提示/功能组树（无 tkinter 时跳过）
  test_i18n.py       # 语言检测 LANGID 映射、词条回退链、两套目录 key 对齐、settings 读写、语言包容错
lang/
  zh_CN.json       # 外部语言包（扁平 key -> 文本）；随发行版随附，与内置 CATALOG 一致
  en.json
docs/
  tech-spec.md     # 本文件（英文，默认）
  tech-spec.zh_CN.md   # 本文件的中文版
  ROADMAP.md
  ROADMAP.zh_CN.md     # 中文版
  decisions/       # 关键机制实证与决策记录
                   # （每篇为英文 `X.md` + 中文 `X.zh_CN.md`）
run.cmd            # 双击启动：转发到 run.ps1
run.ps1            # 定位带 tkinter 的解释器并启动
Makefile           # test / run / scan / scan-machine 任务
README.md  README.zh_CN.md  CHANGELOG.md  CHANGELOG.zh_CN.md  .gitignore
```

## 测试（如何证明）

```
1. test_safety : 全流程断言 backend 从未调用 delete_key；verb/handler 键的其它值保持不变
2. test_actions: 禁用 shellex → Blocked 下出现以 CLSID 命名的 REG_SZ；启用后消失
3. test_actions: 禁用 static → verb 键下出现 LegacyDisable；启用后消失
4. test_scanner: 种子 FakeRegistry → 正确识别两类项、正确计算 disabled 与 location；
   显示名称优先级（MUIVerb / 间接字符串 / GUID 键名）与解析失败逐级回退
5. test_journal: restore_all 按逆序只删除记录过的值，恢复后与初始状态逐字节一致
6. test_safety : 未提权 + machine 范围 → 抛出明确异常且 FakeRegistry 无任何写入
7. test_actions: apply 幂等 —— 连续两次应用结果相同
8. test_ui_smoke: 用 FakeRegistry 构造真实窗口，执行 disable→应用→restore_all 后无残留；
   模拟非提权 + machine 范围时写操作按钮呈禁用态且出现提权入口
9. test_grouping / test_controller / test_ui_smoke: 同一功能在多位置注册时归并为一行；
   选中功能行一键禁用即覆盖全部实例；仅命中明细的搜索只保留该条；别名覆盖展示名且可搜索
10. 实测：`--scan --scope machine` 输出真实条目（本机 411 项）；`Blocked` 机制结论见 docs/decisions/
11. test_i18n  : 语言检测 LANGID 映射（中文各变体 → zh_CN）、取值回退链、`CATALOG` 两套目录 key
    完全对齐、外部包叠加与容错（损坏/非对象/半成品）、settings 读写与优先级、`lang/*.json` 与内置无漂移
```

验收命令：`make test`（即 `C:\Python314\python.exe -m unittest discover -s tests`）。

## 实测记录

- 扫描性能：user 范围 189 项、machine 范围 411 项；无阻塞感，无需限流或懒加载。
- 显示名称：扫描结果中除 1 项（其 CLSID 键本身无名称，`{474C98EE-...}`）外全部解析为可读文本；
  修复前含大量 `@dll,-id` 原文与裸 GUID。shellex 项现已 100% 解析出 CLSID（默认值为空时取键名），
  因此全部可用屏蔽清单禁用——此前这类项会因 `clsid is None` 被 plan 判为 skipped。
- Wow6432Node：本机该键存在但无 shell 菜单项，故 machine 扫描中 0 条来自 32 位视图，属正确结果。
- `restore_all` 对「非本工具写入」的屏蔽值默认不动；如需清理他人条目应另设显式功能。

## 非目标 / deferred

```
- 不做“真删除注册表键”（用户已确认只做可逆禁用/恢复）
- 不做自定义菜单项新建 / 拖拽排序
- 多语言：已支持 zh_CN / en，机制为「内置基准 + 外部语言包叠加」（见「多语言（i18n）」章节），
  更多语言按 `lang/<code>.json` 外挂即可，无需改代码
- 不做安装包、代码签名
- DLL 发布者与图标解析属加分项，未排期
```