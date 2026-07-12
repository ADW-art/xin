# start_uvicorn_safe.ps1
# Safe uvicorn starter with PID lock, port check, reload exclude
[CmdletBinding()]
param(
    [int]$Port = 8002,
    [string]$ListenHost = "127.0.0.1",
    [switch]$NoReload,
    [switch]$Force,
    [string]$BgLog = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Split-Path -Parent $ScriptDir
$VenvPy = Join-Path $BackendDir "venv\Scripts\python.exe"
$LockFile = Join-Path $ScriptDir ".uvicorn_${Port}.pid"
$LogFile = if ($BgLog) { $BgLog } else { Join-Path $ScriptDir "logs\uvicorn_${Port}.log" }
$LogErr = "$LogFile.err"

$LogDir = Split-Path -Parent $LogFile
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function W($msg, $c = "Cyan") {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $c
}

# 1. Check venv
W "1) Check venv..."
if (-not (Test-Path $VenvPy)) {
    W "venv python missing: $VenvPy" "Red"
    exit 1
}
W "   venv OK: $VenvPy"

# 2. Check port
W "2) Check port $Port..."
if ($Port -eq 8001) {
    $l8001 = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
    if ($l8001) {
        W "Port 8001 is in use (PID=$($l8001.OwningProcess)) - use 8002 or 8003" "Red"
        exit 1
    }
}
$listenPort = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listenPort) {
    W "Port $Port is in use (PID=$($listenPort.OwningProcess))" "Yellow"
    $lockedPid = $null
    if (Test-Path $LockFile) {
        try { $lockedPid = [int](Get-Content $LockFile -ErrorAction SilentlyContinue) } catch {}
    }
    if ($lockedPid -and $lockedPid -eq $listenPort.OwningProcess) {
        W "   Occupant is our old instance, skip" "Cyan"
        exit 0
    }
    W "Port $Port is in use by another process. Use a different port." "Red"
    exit 1
}
W "   Port $Port is free"

# 3. PID lock
W "3) Check PID lock $LockFile..."
if (Test-Path $LockFile) {
    $oldPid = $null
    try { $oldPid = [int](Get-Content $LockFile -ErrorAction SilentlyContinue) } catch {}
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        W "Old uvicorn instance running (PID=$oldPid)" "Yellow"
        if (-not $Force) {
            W "Use -Force to kill old instance" "Red"
            exit 1
        }
        try { Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue } catch {}
        Start-Sleep -Seconds 1
    } else {
        W "Stale lock file, cleaning" "Yellow"
    }
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
W "   PID lock OK"

# 4. Env bootstrap
W "4) Set env vars..."
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONHASHSEED = "random"  # prevent Start-Process child hash init failure
if (-not $env:LOG_LEVEL) { $env:LOG_LEVEL = "INFO" }
if (-not $env:HF_ENDPOINT) { $env:HF_ENDPOINT = "https://hf-mirror.com" }
if (-not $env:HF_HUB_DOWNLOAD_TIMEOUT) { $env:HF_HUB_DOWNLOAD_TIMEOUT = "60" }
$env:TOKENIZERS_PARALLELISM = "false"
$env:ANONYMIZED_TELEMETRY = "False"
$env:CHROMA_TELEMETRY_DISABLED = "True"
# WATCHFILES_IGNORE: 防止 uvicorn --reload 监控 scripts/ logs/ chroma_data/ 触发不必要 reload
# 用 ; 分隔多个 pattern (watchfiles 格式)
if (-not $env:WATCHFILES_IGNORE) {
    $env:WATCHFILES_IGNORE = "scripts/*;logs/*;chroma_data*;*.log;data/*;_reembed*;*.pid"
}
if (-not (Test-Path (Join-Path $BackendDir ".env"))) {
    W "No .env file - using defaults" "Yellow"
}
W "   Env OK (WATCHFILES_IGNORE=$env:WATCHFILES_IGNORE)"

# 5. Build args (avoid PowerShell globbing of * patterns)
W "5) Build uvicorn args..."
# 注意: 不传 --reload-include *.py 等带通配符的参数,避免 PowerShell glob 展开
# 改用 WATCHFILES_IGNORE 环境变量过滤不需要监控的目录
$argList = @(
    "-m", "uvicorn", "app.main:app",
    "--host", $ListenHost,
    "--port", "$Port",
    "--log-level", "info"
)
if (-not $NoReload) {
    $argList += @(
        "--reload",
        "--reload-dir", "app"
    )
}
# 数组元素逐个用双引号包裹, cmd /c 不会展开
$quotedArgs = ""
foreach ($a in $argList) {
    if ($quotedArgs.Length -gt 0) { $quotedArgs += " " }
    $quotedArgs += '"' + $a + '"'
}
$cmd = $VenvPy + " " + $quotedArgs
W "   CMD: $cmd"

# 6. Start via cmd /c (cmd does NOT glob *, so *.py stays as literal)
W "6) Start uvicorn via cmd /c -> $LogFile"
$redirectCmd = "$cmd > `"$LogFile`" 2> `"$LogErr`""
W "   Redirect: $redirectCmd"
$proc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", $redirectCmd `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -PassThru
Start-Sleep -Seconds 3

# Verify python child started
$proc = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if (-not $proc) {
    W "Process exited immediately!" "Red"
    if (Test-Path $LogErr) {
        W "--- stderr ---" "Red"
        Get-Content $LogErr | ForEach-Object { W "  $_" "DarkGray" }
    }
    exit 1
}
$pidToLock = $proc.Id
$pidToLock | Out-File -FilePath $LockFile -Encoding ASCII -Force
W "   Started OK PID=$pidToLock"

# 7. Health check poll
W "7) Wait for service ready (max 60s)..."
$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://${ListenHost}:${Port}/api/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            W "   Service ready (try $i)" "Green"
            $ready = $true
            break
        }
    } catch {
        if ($i -eq 60) {
            W "   Service not ready in 60s, see log: $LogFile" "Red"
        }
    }
}

if (-not $ready) {
    W "START FAILED - last 30 log lines:" "Red"
    if (Test-Path $LogFile) {
        Get-Content $LogFile -Tail 30 | ForEach-Object { W "  $_" "DarkGray" }
    }
    if (Test-Path $LogErr) {
        W "--- stderr ---" "Red"
        Get-Content $LogErr | ForEach-Object { W "  $_" "DarkGray" }
    }
    exit 1
}

W "=============================================" "Green"
W "  uvicorn started OK" "Green"
W "  Port: $Port"
W "  PID:  $pidToLock"
W "  Log:  $LogFile"
W "  Err:  $LogErr"
W "  URL:  http://${ListenHost}:${Port}/api/health"
W "  Stop: .\scripts\stop_uvicorn_safe.ps1 -Port $Port"
W "=============================================" "Green"
