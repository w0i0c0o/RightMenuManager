# Changelog

本文件记录所有值得注意的变更。格式参考 Keep a Changelog。

## [Unreleased]

### Added
- 项目脚手架：包结构、测试目录、运行脚本与任务脚本
- 数据模型 `ContextMenuItem`：稳定 id、scope/kind/method 枚举与派生字段
- 注册表后端抽象 `RegistryBackend`，提供 `Win32Registry`（真实）与 `FakeRegistry`（内存）
- 扫描器：按位置表枚举静态菜单项与 Shell 扩展处理器，计算 disabled 与 location
- 禁用/启用动作：shellex 走 `Shell Extensions\Blocked`，static 走 `LegacyDisable`；`apply` 幂等且写入前统一权限预检
- 变更日志与「一键恢复全部」：只回放本工具记录过的值，恢复成功后清空日志
- tkinter 图形界面：范围切换、搜索筛选、多选禁用/恢复、变更预览对话框、条目详情
- 管理员提权：`is_admin()` 检测与 `ShellExecuteW(runas)` 提权重启；全机器范围未提权时置灰写操作并提示
- 全机器范围扫描：`HKLM\SOFTWARE\Classes` 及 32 位 `Wow6432Node`
- 安全不变式测试：全流程断言不删注册表键、不触碰其他软件的注册信息
- 界面冒烟测试：构建窗口、禁用→应用→恢复回到初始、权限提示状态
- 启动脚本编码回归测试：`run.ps1` 必须带 UTF-8 BOM 或为纯 ASCII
- 功能归并（`grouping.py`）：按右键显示文字把同一功能在多个文件类型/位置注册的条目
  归并为 `MenuGroup`；界面顶层一行 = 一个功能，选中即一键禁用/恢复该功能在**所有文件类型**下的
  全部条目，展开后仍可按文件类型逐项控制
- 功能别名（`aliases.py`）：为无法自动解析名称的功能（如百度网盘，注册表里只有 `baidunetdisk`）
  设置别名，按归并键持久化到 `%APPDATA%\RightMenuManager\aliases.json`，之后可按别名搜索、归并、一键开关
- 界面：新增「设置别名…」「展开全部」「折叠全部」按钮；功能行详情列出「要关闭它需处理哪几条」的
  确切注册表路径；搜索命中功能名时保留全部实例、仅命中某条明细时只保留该条
- 模型新增 `name_is_fallback`：标记名称只是回退到键名，界面据此提示「（未识别，可设置别名）」
- 测试：新增 `test_grouping.py`、`test_aliases.py`，并扩充 controller / scanner / UI 冒烟用例（131 → 170 项）
- 「只看非 Windows 自带」勾选框：新增 `system_items.py` 与 `ContextMenuItem.is_system`，
  按「引用的模块落在哪里」判定（Windows 目录 / `Program Files\Windows*` / 裸系统模块名算自带；
  `DriverStore`、`Program Files` 普通目录、`AppData` 算第三方；无线索时不隐藏）。
  过滤在归并前对条目生效，状态栏显示本次隐藏数量。实测 machine 范围 411 项中 191 项判为自带
- 测试：新增 `test_system_items.py`，并扩充 controller / UI 冒烟用例（170 → 198 项）
- 可移植打包：新增 `package_portable.ps1`，一键挑出运行必需文件（`run.cmd` / `run.ps1` /
  `rightmenu\` 下 `.py` / `README.md`）到发行目录 `release\`，自动生成 `VERSION.txt`
  （版本号、打包时间、运行要求），可选 `-Zip`；README 新增「移植到其他机器」章节，
  明确哪些要带、哪些不要带

### Fixed
- 从桌面快捷方式或其他工作目录启动报 `No module named rightmenu`：`run.ps1` 未切换工作目录，
  而 `python -m rightmenu` 依赖当前目录在 `sys.path` 中。现于启动前 `Set-Location $PSScriptRoot`，
  目录放在任意路径均可启动
- 双击 `run.cmd` 无任何窗口：`run.ps1` 含中文但无 UTF-8 BOM，Windows PowerShell 5.1
  按 ANSI 解析导致中文乱码并破坏字符串引号，整个脚本解析失败。现改为 UTF-8 (BOM) 保存，
  并在 `run.cmd` 中于启动失败时暂停以显示错误信息
- 「以管理员身份重启」后不出现窗口：提权时只透传了 `sys.argv[1:]`，而 `-m rightmenu`
  并不在 argv 里（以 `python -m rightmenu` 启动时 `argv[0]` 是 `__main__.py` 路径），
  于是提权后拉起的是一个空解释器。现显式补回 `-m rightmenu` 并把工作目录设为项目根

### Notes
- `Shell Extensions\Blocked` 以 CLSID 作值名的机制已在本机实测确认，见 `docs/decisions/2026-10-04-blocked-list-mechanism-verified.md`
- 扫描性能实测：用户范围 192 项约 231ms，机器范围 414 项约 412ms，无需限流或懒加载