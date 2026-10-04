# 启动 Windows 右键菜单管理器。
# 自动挑选一个带 tkinter 的 Python 解释器。
# 注意：本文件必须以 UTF-8 (带 BOM) 保存 —— Windows PowerShell 5.1 读取无 BOM 的
# .ps1 时按系统 ANSI 代码页解析，中文会变乱码并破坏脚本解析。

$ErrorActionPreference = 'Continue'

# 切到脚本所在目录：`python -m rightmenu` 依赖当前目录在 sys.path 里，
# 若从桌面快捷方式或其他目录启动，不切换就会「No module named rightmenu」。
Set-Location -LiteralPath $PSScriptRoot

$candidates = @(
    @{ Exe = 'py';                      Args = @('-3.14') },
    @{ Exe = 'py';                      Args = @('-3.13') },
    @{ Exe = 'py';                      Args = @('-3')    },
    @{ Exe = 'C:\Python314\python.exe'; Args = @()        },
    @{ Exe = 'python';                  Args = @()        }
)

function Test-HasTkinter($exe, $pre) {
    try {
        $null = & $exe @($pre + @('-c', 'import tkinter')) 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

foreach ($c in $candidates) {
    if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue) -and -not (Test-Path $c.Exe)) {
        continue
    }
    if (Test-HasTkinter $c.Exe $c.Args) {
        & $c.Exe @($c.Args + @('-m', 'rightmenu') + $args)
        exit $LASTEXITCODE
    }
}

Write-Host '[错误] 未找到带 tkinter 的 Python 解释器。' -ForegroundColor Red
Write-Host '请安装 Python 3.13+，或直接使用：C:\Python314\python.exe -m rightmenu'
exit 1