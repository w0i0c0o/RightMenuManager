> English | [简体中文](2026-10-04-blocked-list-mechanism-verified.zh_CN.md)

# Block list (Shell Extensions\Blocked) mechanism verified

date: 2026-10-04
status: verified

## Conclusion

`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked` is a block list
used by Windows itself, in which **the CLSID serves as the value name**. The mechanism on which this tool's D2 decision relies holds, and no fallback plan is needed.

## Evidence

A read-only check of this key on this machine (Windows 11) found 1 pre-existing entry:

```
Key: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Shell Extensions\Blocked
Value name: {9421DD08-935F-4701-A9CA-22DF90AC4EA6}      (REG_SZ)
Data: Epson Easy Photo Print 2: Blocked by {6AF39996-9C88-459B-9282-DA18B14E4402}
```

Key points:
- The value name is a CLSID (a braced GUID form), consistent with this tool's handling of shellex items in `actions._changes_for`;
- The data is descriptive text and may be empty — this tool writes an empty string, which is compatible with the semantics of "existence means blocked";
- This entry was written by the system/another program, showing that the list is shared: this tool only adds and removes the values it has recorded itself, and does not clean up others' entries.

It was also confirmed that `HKCU\...\Shell Extensions\Blocked` does not yet exist on this machine — this tool will create that key on the first disable.
Since this tool never deletes registry keys, that key will remain as an empty key after restore (no side effects).

## Impact

- No need to fall back to renaming keys or a ShellCompatibility approach;
- M3's T12 is downgraded from "verify the mechanism by actual testing" to "spot-check one real item for end-to-end disable/restore";
- In the scan results, the 1 existing disabled item under `HKLM` comes from that system entry and is expected.

## Related

- Spec: docs/staging/specs/2026-10-04-windows-context-menu-manager.md (D2, D5, Working notes)