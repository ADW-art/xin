"""
启动 uvicorn 8002 - 不带 reload, 用于实用性校验
"""
import sys
import os

os.chdir(r"E:\code\claude-1\a3-learning-system\backend")
sys.path.insert(0, r"E:\code\claude-1\a3-learning-system\backend")

import uvicorn
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8002,
        reload=False,
        log_level="info",
    )
