$pwsh = @'
$env:LOG_LEVEL = "INFO"
$env:PYTHONUNBUFFERED = "1"
Set-Location "E:\code\claude-1\a3-learning-system\backend"
& "E:\code\claude-1\a3-learning-system\backend\venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8003 --log-level info
'@
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell.exe"
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command $pwsh"
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = "E:\code\claude-1\a3-learning-system\backend"
$p = [System.Diagnostics.Process]::Start($psi)
Write-Host "Started PID=$($p.Id)"
# 等启动
Start-Sleep -Seconds 12
Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalPort, OwningProcess
