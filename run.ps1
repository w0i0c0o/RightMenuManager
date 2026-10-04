# 启动 Windows 右键菜单管理器。
# 自动挑选一个带 tkinter 的 Python 解释器。

$ErrorActionPreference = 'Continue'

$candidates = @(
    @{ Exe = 'py';                         Args = @('-3.14') },
    @{ Exe = 'py';                         Args = @('-3.13') },
    @{ Exe = 'py';                         Args = @('-3')    },
    @{ Exe = 'C:\Python314\python.exe';    Args = @()        },
    @{ Exe = 'python';                     Args = @()        }
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