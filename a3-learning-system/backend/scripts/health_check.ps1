# health_check.ps1
# A3 Learning System health check
[CmdletBinding()]
param(
    [int]$Port = 8002,
    [string]$ListenHost = "127.0.0.1",
    [switch]$Full
)

$ErrorActionPreference = "Continue"
$BaseUrl = "http://${ListenHost}:${Port}"

function W($msg, $c = "White") {
    Write-Host $msg -ForegroundColor $c
}

$pass = 0
$fail = 0

function Test-Endpoint($name, $method, $url, $expectStatus, $body = $null) {
    Write-Host ""
    W "-> $method $url" "Cyan"
    try {
        $params = @{
            Uri = $url
            Method = $method
            TimeoutSec = 10
            UseBasicParsing = $true
        }
        if ($body) {
            $params.Body = $body
            $params.ContentType = "application/json"
        }
        $r = Invoke-WebRequest @params -ErrorAction Stop
        if ($r.StatusCode -eq $expectStatus) {
            W "  OK [$($r.StatusCode)] $name" "Green"
            $script:pass++
            return @{ ok = $true; status = $r.StatusCode; body = $r.Content }
        } else {
            W "  FAIL [$($r.StatusCode)] expected $expectStatus - $name" "Red"
            $script:fail++
            return @{ ok = $false; status = $r.StatusCode; body = $r.Content }
        }
    } catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq $expectStatus) {
            W "  OK [$code] $name (expected error)" "Green"
            $script:pass++
            return @{ ok = $true; status = $code; body = "" }
        }
        W "  FAIL [-] $name : $_" "Red"
        $script:fail++
        return @{ ok = $false; status = 0; body = $_.Exception.Message }
    }
}

# 1. Port alive
W "=== 1. Port alive ===" "Magenta"
$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    W "  OK Port $Port listening (PID=$($listen.OwningProcess))" "Green"
} else {
    W "  FAIL Port $Port not listening" "Red"
    W "  Hint: .\scripts\start_uvicorn_safe.ps1 -Port $Port" "Yellow"
    exit 1
}

# 2. Root
W "`n=== 2. Root GET / ===" "Magenta"
$r = Test-Endpoint "Root" "GET" "$BaseUrl/" 200
if ($r.ok) {
    try {
        $j = $r.body | ConvertFrom-Json -ErrorAction Stop
        W "  name: $($j.name)" "Gray"
        W "  version: $($j.version)" "Gray"
        W "  status: $($j.status)" "Gray"
        W "  docs: $($j.docs)" "Gray"
        W "  health: $($j.health)" "Gray"
    } catch {}
}

# 3. Health
W "`n=== 3. Health GET /api/health ===" "Magenta"
$r = Test-Endpoint "Health" "GET" "$BaseUrl/api/health" 200
if ($r.ok) {
    try {
        $j = $r.body | ConvertFrom-Json -ErrorAction Stop
        $stColor = if ($j.status -eq "ok") { "Green" } else { "Yellow" }
        W "  status: $($j.status)" $stColor
        W "  version: $($j.version)" "Gray"
        if ($j.checks) {
            foreach ($k in $j.checks.PSObject.Properties) {
                $val = $k.Value
                $color = "Gray"
                if ($val -eq "ok" -or $val -like "ready") { $color = "Green" }
                elseif ($val -like "error:*") { $color = "Red" }
                elseif ($val -like "loading") { $color = "Yellow" }
                W "    [$($k.Name)] $val" $color
            }
        }
    } catch {}
}

# 4. Swagger
W "`n=== 4. Swagger GET /docs ===" "Magenta"
$r = Test-Endpoint "Swagger UI" "GET" "$BaseUrl/docs" 200
if ($r.ok) {
    W "  Response length: $($r.body.Length) bytes" "Gray"
}

# 5. OpenAPI
W "`n=== 5. OpenAPI GET /openapi.json ===" "Magenta"
$r = Test-Endpoint "OpenAPI Schema" "GET" "$BaseUrl/openapi.json" 200
if ($r.ok) {
    try {
        $j = $r.body | ConvertFrom-Json -ErrorAction Stop
        W "  OpenAPI: $($j.openapi)" "Gray"
        W "  Routes: $($j.paths.PSObject.Properties.Count)" "Gray"
        $groups = @{}
        foreach ($p in $j.paths.PSObject.Properties) {
            $parts = $p.Name -split "/"
            $seg = if ($parts.Length -ge 3) { $parts[2] } else { "(root)" }
            if ($groups.ContainsKey($seg)) {
                $groups[$seg] = $groups[$seg] + 1
            } else {
                $groups[$seg] = 1
            }
        }
        W "  Route groups:" "Gray"
        $sortedList = @()
        foreach ($k in $groups.Keys) { $sortedList += @{ key = $k; value = $groups[$k] } }
        $sortedList = $sortedList | Sort-Object value -Descending
        foreach ($g in $sortedList) {
            W "    $($g.key) -> $($g.value)" "Gray"
        }
    } catch {}
}

# 6. 404
W "`n=== 6. 404 GET /notexist ===" "Magenta"
Test-Endpoint "404 fallback" "GET" "$BaseUrl/notexist" 404

# 7. Rate-limit exemption
W "`n=== 7. Rate-limit exemption (5x GET /api/health) ===" "Magenta"
$rlPass = 0
for ($i = 1; $i -le 5; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $rlPass++ }
    } catch {}
}
if ($rlPass -eq 5) {
    W "  OK 5/5 - rate limit exempt works" "Green"
    $pass++
} else {
    W "  FAIL only $rlPass / 5 OK" "Red"
    $fail++
}

# 8. Login (Full mode)
if ($Full) {
    W "`n=== 8. Login POST /api/auth/login (Full) ===" "Magenta"
    $body = '{"username":"test","password":"test"}'
    Test-Endpoint "Login" "POST" "$BaseUrl/api/auth/login" "any" $body
}

# Summary
W ""
W "============================================" "Magenta"
W "  Health check summary" "Magenta"
W "============================================" "Magenta"
W "  OK:   $pass" "Green"
W "  FAIL: $fail" $(if ($fail -gt 0) { "Red" } else { "Green" })
W "  Port: $Port" "Gray"
W "  Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" "Gray"
W "============================================" "Magenta"
W ""

if ($fail -gt 0) { exit 1 } else { exit 0 }
