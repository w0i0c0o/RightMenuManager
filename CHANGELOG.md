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

### Fixed
- 双击 `run.cmd` 无任何窗口：`run.ps1` 含中文但无 UTF-8 BOM，Windows PowerShell 5.1
  按 ANSI 解析导致中文乱码并破坏字符串引号，整个脚本解析失败。现改为 UTF-8 (BOM) 保存，
  并在 `run.cmd` 中于启动失败时暂停以显示错误信息

### Notes
- `Shell Extensions\Blocked` 以 CLSID 作值名的机制已在本机实测确认，见 `docs/decisions/2026-10-04-blocked-list-mechanism-verified.md`
- 扫描性能实测：用户范围 192 项约 231ms，机器范围 414 项约 412ms，无需限流或懒加载