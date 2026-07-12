$env:PYTHONUNBUFFERED = "1"
$env:LOG_LEVEL = "INFO"
Set-Location "E:\code\claude-1\a3-learning-system\backend"
$venvPy = "E:\code\claude-1\a3-learning-system\backend\venv\Scripts\python.exe"
& $venvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --log-level info 2>&1 | Out-Null
