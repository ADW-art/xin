@echo off
REM 启动红豆专用 uvicorn (8002 端口, 跟 codex 8001 隔离)
REM 不抢 8001, 不动 codex 进程, 自动 reload + 排除 scripts/data 不触发 reload
REM
REM 用法: 双击运行, 或 .\start_uvicorn_8002.bat

cd /d E:\code\claude-1\a3-learning-system\backend

echo === 启动 uvicorn 8002 (红豆专用, 含 P0/P1/P2 所有修复) ===
echo === 排除 scripts/data 目录, 防止 reload 失败 ===

E:\code\claude-1\a3-learning-system\backend\venv\Scripts\python.exe -m uvicorn app.main:app ^
    --host 127.0.0.1 ^
    --port 8002 ^
    --reload ^
    --reload-dir app ^
    --reload-include "*.py" ^
    --log-level info

pause
