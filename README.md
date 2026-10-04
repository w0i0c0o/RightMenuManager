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
2. **列表按「功能」归并**：顶层一行 = 一个右键功能（如「上传到百度网盘」）。
   「位置」列显示它覆盖了几处位置，「类型 / 条目」列显示共有几条。
   展开某一行即可看到**逐项明细**（每条对应一个文件类型/位置），可按文件类型单独开关。
   双击任意行查看详情：功能行会列出「要关闭它，需要处理哪几条」的确切注册表路径。
   名称显示的是**实际右键菜单上看到的文字**：注册表里常见的资源引用
   （如 `@shell32.dll,-8506`）会被解析成可读文本，不会出现 `@dll,-id` 或裸 GUID。
3. **一键消除/显示某个功能（跨文件类型）**：选中功能行（`Ctrl`/`Shift` 可多选），
   点「禁用选中项」即可一次性关掉该功能在**所有文件类型**下的全部条目；点「恢复选中项」恢复。
   只选明细行则只影响那一条 —— 原来的分文件类型细粒度控制仍然保留。
4. **认不出的名字？设置别名**：有些功能（如百度网盘）的文字由 DLL 在运行时生成，
   注册表里只有 `baidunetdisk` 之类，界面会标注「（注册表名）」提示该名称取自注册表键名、
   可能与实际菜单文字不同。选中该功能行，点「设置别名…」起个能认出的名字，
   之后即可按别名搜索、归并与一键开关。别名保存在 `%APPDATA%\RightMenuManager\aliases.json`。
5. **搜索**：在「搜索」框输入名称、别名、位置、命令或 DLL 路径片段，列表实时筛选并自动展开命中项。
   命中功能名时保留该功能的全部实例；只命中某条明细时只保留该条，
   便于确认「要关掉这个功能，涉及哪几条」。
6. **只看非 Windows 自带**：勾选工具栏的「只看非 Windows 自带」，可隐藏 Windows 自身注册的
   菜单项（BitLocker、固定到快速访问、发送到、新建、压缩文件夹、Windows Defender 等），
   只留下第三方软件装进来的条目，便于聚焦「我要清理什么」。状态栏会显示本次隐藏了多少条。
   判定依据是「该项引用的模块落在哪里」：落在 Windows 目录或 `Program Files\Windows*` 系统组件
   目录的算自带；落在 `DriverStore`（厂商驱动包，如 NVIDIA）、`Program Files` 普通目录、
   `AppData` 等处的算第三方；只有裸模块名（如 `shell32.dll`、`rundll32.exe`）也按自带处理。
   拿不到任何线索的项**不会**被隐藏 —— 宁可多显示，也不误藏你自己装的项。
7. **应用前预览**：任何禁用/恢复都会弹出**变更预览**，逐条列出将写入/删除的确切注册表路径与值名；
   确认后才执行。
8. **一键恢复全部**：点「一键恢复全部改动」，按变更日志把所有被本工具改动过的项还原到
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

## 移植到其他机器

程序不依赖安装、不写系统目录，整个目录可以放在任意路径（U 盘、桌面、其他盘符都行），
`run.ps1` 会自行切换到脚本所在目录，从快捷方式或其他目录启动都不会出错。

生成一份干净的发行副本（默认输出到 `release\`）：

```
powershell -ExecutionPolicy Bypass -File package_portable.ps1
powershell -ExecutionPolicy Bypass -File package_portable.ps1 -Destination D:\RightMenuManager -Zip
```

**需要一起移植的文件**（共 21 个，脚本会自动挑好）：

| 内容 | 说明 |
|---|---|
| `run.cmd`、`run.ps1` | 启动入口，`run.cmd` 双击即用 |
| `rightmenu\` 下全部 `.py` | 程序本体（`ui\` 子目录含界面） |
| `README.md` | 可选，方便目标机器上查用法 |
| `VERSION.txt` | 发行标记：版本号、打包时间、运行要求（脚本自动生成） |

**不需要移植**：`tests\`、`docs\`、`Makefile`、`CHANGELOG.md`、`.gitignore`、
`__pycache__\` 与 `*.pyc`（不同 Python 版本的字节码缓存，拷过去也没用，还可能干扰）。
`fake_registry.py` 仅供测试，但它在包内、体积可忽略，一并带上更省心。

**不要移植 `%APPDATA%\RightMenuManager\`**（`journal.json` / `aliases.json`）：
那是**本机**的注册表改动记录，拷到别的机器后点「一键恢复全部」会去还原那台机器上
并不存在的改动。换机器请从零开始记录。

目标机器要求：Windows 10/11 + 带 tkinter 的 Python 3.13+，双击 `run.cmd` 即可。

## 文档

- 技术规格：`docs/tech-spec.md`
- 路线图：`docs/ROADMAP.md`
- 决策记录：`docs/decisions/`