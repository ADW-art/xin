# stop_uvicorn_safe.ps1
# Graceful uvicorn stop with PID lock
[CmdletBinding()]
param(
    [int]$Port = 8002,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LockFile = Join-Path $ScriptDir ".uvicorn_${Port}.pid"

function W($msg, $c = "Cyan") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $c
}

W "1) Read PID lock $LockFile..."
$pid = $null
if (Test-Path $LockFile) {
    try { $pid = [int](Get-Content $LockFile -ErrorAction SilentlyContinue) } catch {}
}

if (-not $pid) {
    W "No PID lock found, checking port $Port..." "Yellow"
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listen) {
        $pid = $listen.OwningProcess
        W "Port $Port has process PID=$pid" "Yellow"
    } else {
        W "Nothing to stop" "Cyan"
        exit 0
    }
}

$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
if (-not $proc) {
    W "PID=$pid already exited, cleaning lock" "Yellow"
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    exit 0
}
W "   Found process PID=$pid (StartTime=$($proc.StartTime), Path=$($proc.Path))"

if ($proc.ProcessName -ne "python" -and $proc.ProcessName -ne "cmd") {
    W "PID=$pid is not python/cmd ($($proc.ProcessName)). Refuse to kill!" "Red"
    exit 1
}

if ($Force) {
    W "2) Force kill PID=$pid..."
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
} else {
    W "2) Graceful stop PID=$pid..."
    try { Stop-Process -Id $pid -ErrorAction Stop } catch { W "   Stop-Process error: $_" "Yellow" }
    $exited = $false
    for ($i = 1; $i -le 5; $i++) {
        Start-Sleep -Seconds 1
        if (-not (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
            W "   Process exited in ${i}s" "Green"
            $exited = $true
            break
        }
    }
    if (-not $exited) {
        W "   Not exited in 5s, force kill" "Yellow"
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

W "3) Cleanup lock..."
Remove-Item $LockFile -Force -ErrorAction SilentlyContinue

W "4) Verify port $Port released..."
$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    W "Port $Port still in use by PID=$($listen.OwningProcess)" "Red"
    exit 1
}
W "   Port $Port released" "Green"

W "=============================================" "Green"
W "  Stopped PID=$pid OK" "Green"
W "=============================================" "Green"
