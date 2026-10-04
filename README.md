# Windows 右键菜单管理器

以**非破坏、可逆**的方式管理 Windows 资源管理器右键菜单项。

## 它解决什么问题

很多软件会往右键菜单里塞条目。常见做法是直接删注册表键，这有代价：
- 破坏软件自身的注册信息，软件可能报错或重新写回；
- 影响其他用户；
- 想恢复时已经找不回原内容。

本工具改用 Windows 官方的**屏蔽机制**，只增删注册表「值」，从不删「键」：

| 菜单项类型 | 位置 | 禁用方式 | 恢复方式 |
|---|---|---|---|
| Shell 扩展处理器（带 CLSID） | `shellex\ContextMenuHandlers` | 在 `Shell Extensions\Blocked` 写入以 CLSID 命名的值 | 删除该值 |
| 静态菜单项 | `shell\<verb>\command` | 在该键下写入 `LegacyDisable` 值 | 删除该值 |

因此：其他软件的注册信息原样保留，软件照常注册菜单项，随时可一键恢复。

## 快速开始

```
run.cmd
```

`run.cmd` 会自动定位带 tkinter 的 Python 解释器。也可直接指定：

```
C:\Python314\python.exe -m rightmenu
```

无界面模式（输出 JSON，便于排查与自动化）：

```
C:\Python314\python.exe -m rightmenu --scan --scope user
C:\Python314\python.exe -m rightmenu --scan --scope machine
```

## 使用步骤

1. **选择范围**（窗口左上角）：
   - `仅当前用户（无需管理员）`：只读取/修改 `HKCU`，不影响其他用户，随时可用。
   - `当前用户 + 全机器（需要管理员）`：追加 `HKLM`（含 32 位 `Wow6432Node`）条目。
     未提权时写操作会置灰，并出现「以管理员身份重启」按钮，点击后经 UAC 重新拉起自身。
2. **查找条目**：在「搜索」框输入名称、位置、命令或 DLL 路径片段，列表实时筛选。
   双击任意行可查看该条目的注册表键、CLSID、DLL 等详情。
3. **禁用**：选中一行或多行（`Ctrl`/`Shift` 多选），点「禁用选中项」。
   应用前会弹出**变更预览**，逐条列出将写入/删除的确切注册表路径与值名；确认后才执行。
4. **恢复单个**：选中已禁用项，点「恢复选中项」。
5. **一键恢复全部**：点「一键恢复全部改动」，按变更日志把所有被本工具改动过的项还原到
   本工具介入之前的状态。其他软件或用户自己设置的屏蔽项不会被触碰。

变更日志位于 `%APPDATA%\RightMenuManager\journal.json`。即使用户重装本工具，只要日志还在，
就能完整还原。

## 开发

```
make test          # 运行单元测试
make run           # 启动图形界面
make scan          # headless 扫描（当前用户）
make scan-machine  # headless 扫描（含全机器）
```

没有 `make` 时，直接用等价的 PowerShell 命令：

```
C:\Python314\python.exe -m unittest discover -s tests -v
```

## 安全承诺

- 不调用 `DeleteKey` / `DeleteKeyEx`，永不删除注册表键；
- 不修改菜单项自身的 `command`、`Icon`、名称等值；
- 扫描全程只读；
- 每次改动写入 `%APPDATA%\RightMenuManager\journal.json`，支持「一键恢复全部」；
- 应用前提供 dry-run 预览，明确列出将变更的注册表路径与值名；
- 批量写入前先统一做权限预检，任何一处不可写就整体中止，不留半途的部分改动。

## 环境要求

- Windows 10/11；
- 带 tkinter 的 Python 3.13+（开发与验证使用 `C:\Python314\python.exe`，自带 Tk 9.0）；
- 仅标准库依赖，无 pip 安装步骤，离线可跑。

## 文档

- 技术规格：`docs/tech-spec.md`
- 路线图：`docs/ROADMAP.md`
- 决策记录：`docs/decisions/`