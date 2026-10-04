# Windows 右键菜单管理器 — 技术规格

purpose:      以非破坏、可逆的方式禁用/恢复 Windows 资源管理器右键菜单项，且不修改其他软件自身的注册信息
user:         需要清理右键菜单、又不愿冒险删注册表键的 Windows 用户
use-case:     列出菜单项 → 选择范围 → 搜索/多选 → 预览并禁用 → 随时恢复单个或一键恢复全部
architecture: 分层：model / registry 后端抽象 / scanner / actions / journal / elevation / ui（controller 与 tkinter 视图分离）
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
convention:   文件名 snake_case；界面文案中文；注释仅解释「为什么」
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
`H\CLSID\<clsid>` 默认值 → 友好名（形如 `@dll,-123` 的资源引用保留原文，不强行解析）。

## 数据模型

```
@dataclass(frozen=True)
ContextMenuItem:
  id            : str          # sha1(hive + key_path)，跨会话稳定
  scope         : "user"|"machine"
  kind          : "static"|"shellex"
  location      : str          # 人类可读位置，如「所有文件」「目录背景」「.txt 文件」
  key_path      : str          # 该项所在注册表键全路径
  display_name  : str          # 默认值 / MUIVerb / 键名，按优先级取
  key_name      : str          # 键名（verb 名或 handler 名）
  command       : str|None     # static：command 子键默认值
  clsid         : str|None     # shellex：CLSID
  dll_path      : str|None     # shellex：解析出的 DLL
  extended      : bool         # 是否仅在 Shift+右键 显示
  disabled      : bool         # 由屏蔽值/LegacyDisable 是否存在计算得出
  method        : "blocked"|"legacy_disable"|None   # 当前生效的禁用方式
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

scan(backend, scope) -> list[ContextMenuItem]             # 只读
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
  scanner.py       # scan(backend, scope) -> list[ContextMenuItem]
  actions.py       # plan / apply / disable / enable
  journal.py       # 变更日志读写 + restore_all
  elevation.py     # is_admin() / relaunch_as_admin()
  ui/__init__.py
  ui/controller.py # 展示逻辑（不依赖 tkinter，可无界面测试）
  ui/app.py        # tkinter 主窗口
  __main__.py      # 入口，支持 --scan（headless 输出 JSON）与默认启动 GUI
tests/
  test_model.py  test_registry.py  test_scanner.py  test_actions.py
  test_journal.py  test_safety.py  test_elevation.py  test_controller.py
  test_ui_smoke.py   # 界面冒烟：构建/禁用恢复/权限提示（无 tkinter 时跳过）
docs/
  tech-spec.md     # 本文件
  ROADMAP.md
  decisions/       # 关键机制实证与决策记录
run.cmd            # 双击启动：转发到 run.ps1
run.ps1            # 定位带 tkinter 的解释器并启动
Makefile           # test / run / scan / scan-machine 任务
README.md  CHANGELOG.md  .gitignore
```

## 测试（如何证明）

```
1. test_safety : 全流程断言 backend 从未调用 delete_key；verb/handler 键的其它值保持不变
2. test_actions: 禁用 shellex → Blocked 下出现以 CLSID 命名的 REG_SZ；启用后消失
3. test_actions: 禁用 static → verb 键下出现 LegacyDisable；启用后消失
4. test_scanner: 种子 FakeRegistry → 正确识别两类项、正确计算 disabled 与 location
5. test_journal: restore_all 按逆序只删除记录过的值，恢复后与初始状态逐字节一致
6. test_safety : 未提权 + machine 范围 → 抛出明确异常且 FakeRegistry 无任何写入
7. test_actions: apply 幂等 —— 连续两次应用结果相同
8. test_ui_smoke: 用 FakeRegistry 构造真实窗口，执行 disable→应用→restore_all 后无残留；
   模拟非提权 + machine 范围时写操作按钮呈禁用态且出现提权入口
9. 实测：`--scan --scope machine` 输出真实条目（本机 416 项）；`Blocked` 机制结论见 docs/decisions/
```

验收命令：`make test`（即 `C:\Python314\python.exe -m unittest discover -s tests`）。

## 实测记录

- 扫描性能：user 范围 194 项、machine 范围 416 项；无阻塞感，无需限流或懒加载。
- Wow6432Node：本机该键存在但无 shell 菜单项，故 machine 扫描中 0 条来自 32 位视图，属正确结果。
- `restore_all` 对「非本工具写入」的屏蔽值默认不动；如需清理他人条目应另设显式功能。

## 非目标 / deferred

```
- 不做“真删除注册表键”（用户已确认只做可逆禁用/恢复）
- 不做自定义菜单项新建 / 拖拽排序
- 不做多语言（界面中文）
- 不做安装包、代码签名
- DLL 发布者与图标解析属加分项，未排期
```