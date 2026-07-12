# test_sse_chat.ps1
# A3 Learning System SSE chat test
[CmdletBinding()]
param(
    [int]$Port = 8002,
    [string]$ListenHost = "127.0.0.1",
    [string]$Message = "Hello, what is Python?",
    [string]$UserId = "test_sse_user",
    [int]$Timeout = 60
)

$ErrorActionPreference = "Continue"
$BaseUrl = "http://${ListenHost}:${Port}"

function W($msg, $c = "White") { Write-Host $msg -ForegroundColor $c }

# 1. Port alive
W "=== 1. Port alive ===" "Magenta"
$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listen) {
    W "  FAIL Port $Port not listening" "Red"
    exit 1
}
W "  OK Port $Port listening (PID=$($listen.OwningProcess))" "Green"

# 2. Build request
W "`n=== 2. Build request ===" "Magenta"
# ChatRequest 字段: content (必需), images (可选), regenerate (可选)
# user_id 从 _optional_user 推断, 匿名 = 0; conversation_id 走 query param 或 header
$body = @{
    content = $Message
} | ConvertTo-Json -Compress
W "  POST $BaseUrl/api/chat/send" "Cyan"
W "  Body: $body" "Gray"

# 3. Send request
W "`n=== 3. SSE response (timeout ${Timeout}s) ===" "Magenta"
$startTime = Get-Date
$events = @()
$chunks = @()
$firstEventTime = $null
$doneStatus = $null
$hasError = $false
$errorMessage = ""
$totalContent = ""

# PowerShell 5.1 用 .NET Framework, 用 [System.Net.HttpWebRequest] 兼容
$req = [System.Net.HttpWebRequest]::Create("$BaseUrl/api/chat/send")
$req.Method = "POST"
$req.Timeout = $Timeout * 1000
$req.ReadWriteTimeout = $Timeout * 1000
$req.ContentType = "application/json"
$req.Accept = "text/event-stream"
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$req.ContentLength = $bodyBytes.Length
try {
    $reqStream = $req.GetRequestStream()
    $reqStream.Write($bodyBytes, 0, $bodyBytes.Length)
    $reqStream.Close()

    $response = $req.GetResponse()
    W "  OK HTTP $($response.StatusCode) $($response.StatusDescription)" "Green"
    W "  Content-Type: $($response.ContentType)" "Gray"

    if ($response.ContentType -notmatch "text/event-stream") {
        W "  FAIL not text/event-stream!" "Red"
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        $body2 = $reader.ReadToEnd()
        W "  Body: $body2" "Gray"
        exit 1
    }

    $stream = $response.GetResponseStream()
    $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
    $eventName = ""
    $dataBuffer = ""

    while (-not $reader.EndOfStream) {
        $line = $reader.ReadLine()
        if ($null -eq $line) { continue }
        if ($firstEventTime -eq $null) { $firstEventTime = Get-Date }

        if ($line -eq "") {
            if ($dataBuffer) {
                $events += @{ event = $eventName; data = $dataBuffer }
                # 兼容 v1. 前缀 (claude 引入的协议): v1.message, v1.chunk, v1.content
                $isContentEvent = ($eventName -eq "chunk" -or $eventName -eq "content" -or $eventName -eq "message" `
                    -or $eventName -eq "v1.message" -or $eventName -eq "v1.chunk" -or $eventName -eq "v1.content")
                $isDoneEvent = ($eventName -eq "done" -or $eventName -eq "v1.done")
                $isErrorEvent = ($eventName -eq "error" -or $eventName -eq "v1.error")

                if ($isContentEvent) {
                    try {
                        $d = $dataBuffer | ConvertFrom-Json -ErrorAction Stop
                        if ($d.content) { $chunks += $d.content; $totalContent += $d.content }
                        elseif ($d.text) { $chunks += $d.text; $totalContent += $d.text }
                    } catch {
                        $chunks += $dataBuffer
                        $totalContent += $dataBuffer
                    }
                }
                if ($isDoneEvent) {
                    try { $d = $dataBuffer | ConvertFrom-Json -ErrorAction Stop; $doneStatus = $d.status } catch {}
                }
                if ($isErrorEvent) {
                    $hasError = $true
                    try { $d = $dataBuffer | ConvertFrom-Json -ErrorAction Stop; $errorMessage = $d.message } catch { $errorMessage = $dataBuffer }
                }
                $eventName = ""
                $dataBuffer = ""
            }
        } elseif ($line -match "^event:\s*(.+)$") {
            $eventName = $matches[1].Trim()
        } elseif ($line -match "^data:\s*(.*)$") {
            $dataBuffer = $matches[1]
        }
    }
    $reader.Close()
    $response.Close()
} catch {
    W "  FAIL request error: $_" "Red"
}

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds
$ttfb = if ($firstEventTime) { ($firstEventTime - $startTime).TotalSeconds } else { -1 }

# 4. Stats
W "`n=== 4. Stats ===" "Magenta"
W "  Duration: $([math]::Round($duration, 2))s" "Gray"
W "  TTFB:     $([math]::Round($ttfb, 2))s" "Gray"
W "  Events:   $($events.Count)" "Gray"
W "  Chunks:   $($chunks.Count)" "Gray"
W "  Content:  $($totalContent.Length) chars" "Gray"

$eventTypes = @{}
foreach ($e in $events) {
    $k = if ($e.event) { $e.event } else { "(default)" }
    if ($eventTypes.ContainsKey($k)) { $eventTypes[$k] = $eventTypes[$k] + 1 } else { $eventTypes[$k] = 1 }
}
W "  Event types:" "Gray"
foreach ($k in ($eventTypes.Keys | Sort-Object)) {
    W "    $k -> $($eventTypes[$k])" "Gray"
}

# 5. Validation
W "`n=== 5. Validation ===" "Magenta"
$pass = 0
$fail = 0

# 检查 v1. 前缀的 content/chunk 事件
$hasChunk = ($eventTypes["chunk"] -or $eventTypes["content"] -or $eventTypes["message"] `
    -or $eventTypes["v1.chunk"] -or $eventTypes["v1.content"] -or $eventTypes["v1.message"])
if ($hasChunk) {
    W "  OK has content/chunk event" "Green"
    $pass++
} else {
    W "  FAIL no content/chunk event" "Red"
    $fail++
}

if ($events.Count -gt 0) {
    $lastEvent = $events[-1]
    # done 事件可能带 v1. 前缀
    if ($lastEvent.event -eq "done" -or $lastEvent.event -eq "v1.done") {
        W "  OK done event is last" "Green"
        $pass++
    } else {
        W "  FAIL last event is not done: $($lastEvent.event)" "Red"
        $fail++
    }
}

if ($hasError) {
    if ($events[-1].event -eq "done" -or $events[-1].event -eq "v1.done") {
        W "  OK error+done pair (status=$doneStatus)" "Green"
        $pass++
    } else {
        W "  FAIL error without done" "Red"
        $fail++
    }
    W "  Error message: $errorMessage" "Yellow"
}

if ($totalContent.Length -gt 0) {
    W "  OK response not empty ($($totalContent.Length) chars)" "Green"
    $pass++
} else {
    W "  FAIL response empty" "Red"
    $fail++
}

$sparkTokenPattern = '"[sS][a-z0-9]{1,2}">'
if ($totalContent -notmatch $sparkTokenPattern) {
    W "  OK no Spark token residue" "Green"
    $pass++
} else {
    W "  FAIL Spark token residue detected" "Red"
    $fail++
}

# 6. Content preview
W "`n=== 6. Content preview (first 500 chars) ===" "Magenta"
$preview = $totalContent.Substring(0, [Math]::Min(500, $totalContent.Length))
W "---" "DarkGray"
W $preview "White"
if ($totalContent.Length -gt 500) {
    W "`n... ($($totalContent.Length - 500) chars omitted)" "DarkGray"
}
W "---" "DarkGray"

# Summary
W ""
W "============================================" "Magenta"
W "  SSE test result" "Magenta"
W "============================================" "Magenta"
W "  OK:   $pass" "Green"
W "  FAIL: $fail" $(if ($fail -gt 0) { "Red" } else { "Green" })
W "  Duration: $([math]::Round($duration, 2))s" "Gray"
W "  Content:  $($totalContent.Length) chars / $($chunks.Count) chunks" "Gray"
W "============================================" "Magenta"

if ($fail -gt 0) { exit 1 } else { exit 0 }
