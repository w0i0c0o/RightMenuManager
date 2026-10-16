> [English](2026-10-12-i18n-mechanism.md) | 简体中文

# 多语言（i18n）机制选型

date: 2026-10-12
status: 已采纳

## 背景

程序需要中英双语，且明确要求「以后加入更多语言要方便」。三条硬约束同时成立：

1. **零 pip 依赖、双击即用** —— 只用标准库，不能有构建/编译步骤；
2. **界面永不崩** —— 缺词、语言包损坏、`lang/` 目录整个丢失，都不能让程序起不来；
3. **新增语言代价要低** —— 加一门语言不应改动 Python 代码。

## 备选方案

| 方案 | 新增语言 | 零依赖 | 容错 | 结论 |
|---|---|---|---|---|
| gettext（`.po` / `.mo`） | 加 `.po`，需编译成 `.mo` | ✗ 标准库无 `.mo` 编译器，需 `msgfmt`/pip | 一般 | 否决 |
| 译文全写进 Python（纯内置字典） | 必须改代码、重新打包 | ✓ | 翻译者写错引号会让整个程序起不来 | 否决 |
| 外部 JSON 语言包（纯外部） | 丢一个 `lang/xx.json` | ✓ | 单文件损坏只影响该语言 | 采纳（但需保底） |
| **内置基准 + 外部语言包叠加** | 丢一个 `lang/xx.json` | ✓ | 目录丢失走内置、文件损坏被忽略 | **采纳** |

## 决定

采用 **内置基准 + 外部语言包叠加**：

```
内置 CATALOG（rightmenu/i18n.py）  : {"ui.title": {"zh_CN": "…", "en": "…"}, …}   # 保底 + 权威来源
外部语言包（lang/<code>.json）      : {"ui.title": "…", …}                        # 启动时扫描并叠加
取值链                             : 外部包[lang][key] → 内置[lang][key] → 内置["en"][key] → key 本身
```

理由：

- **加语言 = 丢文件**。外部包以文件名作语言代码（`lang/fr.json` → `fr`），启动时自动扫描，
  界面的语言下拉框自动出现新条目 —— 不动一行 Python。
- **内置保底让「零依赖、双击即用」成立**。`lang/` 是可选增强；删掉它，程序照跑，只是没有外挂语言。
  内置 `CATALOG` 同时是权威来源，测试断言 `zh_CN` 与 `en` 的 key 集合完全一致，杜绝漏译。
- **容错到位**。`_load_packs` 对损坏 JSON、非对象、非字符串值逐条忽略；`t()` 缺词返回 key 本身，
  绝不抛异常；`settings.json` 写失败只影响「下次启动记住选择」，不影响本次使用。
  语言包与 settings 均以 `utf-8-sig` 读取 —— 翻译者用记事本另存为「UTF-8 带 BOM」也能直接用。
- **叠加而非覆盖**。外部包可以只翻译一部分 key，未覆盖的自动回落到内置译文，
  因此一个「半成品」语言包也能用（`test_partial_new_language_falls_back_to_english`）。

## 与其他约束的衔接

- **枚举值不翻译**：`scope` / `kind` / `method` 是机器可读 token，恒为英文，
  自动化（`--scan` 的 JSON）不受界面语言影响；只有 `location` 是展示文案，随语言变化。
- **位置名动态化**：`locations.py` 的 `SCAN_TARGETS` 常量改为 `scan_targets()` 函数，
  位置名在调用时经 `t()` 生成，切语言后 `controller.refresh()` 重扫即可刷新。
- **历史记录保留原貌**：`journal` 里的 `description` 在写入时定语言，切语言后旧记录仍是原文；
  恢复/撤销前缀在显示时翻译。

## 影响

- 新增文件：`rightmenu/i18n.py`、`lang/zh_CN.json`、`lang/en.json`、`tests/test_i18n.py`。
- 所有面向用户的文案改经 `i18n.t()`；代码注释与 docstring 仍保持中文（项目既有约定）。
- 发行打包需带上 `lang/` 目录（`package_portable.ps1` 已含）。
- 语言选择持久化到 `%APPDATA%\RightMenuManager\settings.json`（`{"language": "zh_CN"}`）。

## 相关

- 规格：`docs/tech-spec.md` 的「多语言（i18n）」章节
- 实现：`rightmenu/i18n.py`
- 测试：`tests/test_i18n.py`（语言检测 LANGID 映射、回退链、两套目录 key 对齐、外部包叠加与容错、settings 读写）