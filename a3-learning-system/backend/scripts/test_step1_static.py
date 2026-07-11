"""步骤 1: 静态验证 - 4 个修复文件 syntax + import + 配置加载"""
import sys
import os
sys.path.insert(0, r"E:\code\claude-1\a3-learning-system\backend")

print("=" * 60)
print("步骤 1: 静态验证 - syntax / import / config")
print("=" * 60)

# 1.1 syntax check
import ast
files = [
    "app/utils/llm_helper.py",
    "app/services/rag_service.py",
    "app/api/chat.py",
    "app/config.py",
    "scripts/clean_checkpoint_stale_flags.py",
    "scripts/test_truncate.py",
]
print("\n--- 1.1 Syntax Check ---")
for f in files:
    fp = os.path.join(r"E:\code\claude-1\a3-learning-system\backend", f)
    try:
        ast.parse(open(fp, encoding="utf-8").read())
        print(f"  OK    {f}")
    except SyntaxError as e:
        print(f"  FAIL  {f}: {e}")

# 1.2 Import check
print("\n--- 1.2 Import Check ---")
modules = [
    ("app.config", "Settings"),
    ("app.utils.llm_helper", "truncate_messages, safe_chat_sync, safe_chat_stream, StreamGuard, ContentGuard"),
    ("app.utils.content_guard", "StreamGuard, ContentGuard, get_guard"),
    ("app.services.rag_service", "_get_reranker, is_rag_ready, _get_dense_model, hybrid_search"),
    ("app.checkpoint_sqlite", "SqliteSaver"),
    ("scripts.clean_checkpoint_stale_flags", ""),
]
for mod, names in modules:
    try:
        __import__(mod)
        print(f"  OK    {mod}")
    except Exception as e:
        print(f"  FAIL  {mod}: {e}")

# 1.3 Config check
print("\n--- 1.3 Config Check ---")
from app.config import settings
print(f"  hf_mirror:           {settings.hf_mirror}")
print(f"  embedding_model:     {settings.embedding_model}")
print(f"  embedding_local_path: {settings.embedding_local_path}")
print(f"  reranker_model:      {getattr(settings, 'reranker_model', 'MISSING')}")
print(f"  reranker_local_path: {repr(getattr(settings, 'reranker_local_path', 'MISSING'))}")
print(f"  checkpoint_db_path:  {settings.checkpoint_db_path}")

# 1.4 Env vars
print("\n--- 1.4 Env Vars (HF) ---")
for k in ["HF_ENDPOINT", "HF_HUB_DOWNLOAD_TIMEOUT", "HF_HUB_ENABLE_HF_TRANSFER",
          "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"]:
    print(f"  {k}: {os.environ.get(k, 'NOT SET')}")

print("\n=== 步骤 1 完成 ===")
