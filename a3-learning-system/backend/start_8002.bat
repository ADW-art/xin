@echo off
cd /d e:\code\claude-1\a3-learning-system\backend
.\venv\Scripts\python.exe -c "import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8002, log_level='info')" > logs\uvicorn_8002.log 2>&1
