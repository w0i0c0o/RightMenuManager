# 屏蔽清单（Shell Extensions\Blocked）机制实证

date: 2026-10-04
status: 已验证

## 结论

`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked` 是 Windows
自身使用的、以 **CLSID 作为值名** 的屏蔽清单。本工具 D2 决策所依赖的机制成立，无需回退方案。

## 证据

在本机（Windows 11）只读检查该键，发现 1 条既有条目：

```
键：HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked
值名：{9421DD08-935F-4701-A9CA-22DF90AC4EA6}      （REG_SZ）
数据：Epson Easy Photo Print 2: Blocked by {6AF39996-9C88-459B-9282-DA18B14E4402}
```

要点：
- 值名是 CLSID（花括号 GUID 形式），与本工具 `actions._changes_for` 对 shellex 项的处理一致；
- 数据是描述性文本，可为空 —— 本工具写入空串，与"存在即屏蔽"的语义相容；
- 该条目由系统/其他程序写入，说明清单是共享的：本工具只增删自己记录过的值，不清理他人条目。

同时确认 `HKCU\...\Shell Extensions\Blocked` 在本机尚不存在 —— 首次禁用时会由本工具创建该键。
由于本工具永不删除注册表键，该键在恢复后会以空键形式保留（无副作用）。

## 影响

- 无需回退到改键名或 ShellCompatibility 方案；
- M3 的 T12 由"实测确认机制"降级为"抽查一条真实项做端到端禁用/恢复"；
- 扫描结果中 `HKLM` 下已有 1 条 disabled 项来自该系统条目，属预期。

## 相关

- 规格：docs/staging/specs/2026-10-04-windows-context-menu-manager.md （D2、D5、Working notes）