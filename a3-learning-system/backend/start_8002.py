"""
启动 uvicorn 8002 - 简单包装
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
        reload=True,
        reload_dirs=["app"],
        log_level="info",
    )
