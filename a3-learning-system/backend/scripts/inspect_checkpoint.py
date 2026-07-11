"""深入查看 user-1 checkpoint 的所有 agent_outputs"""
import sys
import os
import json
import pickle

sys.path.insert(0, r"E:\code\claude-1\a3-learning-system\backend")

from app.checkpoint_sqlite import SqliteSaver

saver = SqliteSaver(db_path=r"E:\code\claude-1\a3-learning-system\backend\data\checkpoints.db")

ckpt_list = list(saver.list({"configurable": {"thread_id": "user-1"}}, limit=20))
print(f"user-1 has {len(ckpt_list)} checkpoints")

# 排序 by checkpoint_id desc
def get_cid(t):
    return t.config.get("configurable", {}).get("checkpoint_id", "")
ckpt_list_sorted = sorted(ckpt_list, key=get_cid, reverse=True)

# 看最近 5 个 checkpoint 的核心状态
for i, ckpt_tuple in enumerate(ckpt_list_sorted[:5]):
    vals = ckpt_tuple.checkpoint.get("channel_values", {})
    cid = get_cid(ckpt_tuple)
    print(f"\n========== checkpoint #{i+1} ==========")
    print(f"  cid: {cid[-12:]}")
    print(f"  current_agent: {vals.get('current_agent')}")
    print(f"  next_agent: {vals.get('next_agent')}")
    print(f"  pending_writes: {len(ckpt_tuple.pending_writes or [])}")
    for w in (ckpt_tuple.pending_writes or [])[:5]:
        print(f"    write: task_id={w[0]} channel={w[1]}")
    # stream_buffer 完整内容
    sb = vals.get('stream_buffer', '') or ''
    print(f"  stream_buffer length: {len(sb)}")
    if sb:
        print(f"  stream_buffer first 200: {sb[:200]}")
        print(f"  stream_buffer last 200: {sb[-200:]}")
    # agent_outputs
    ao = vals.get('agent_outputs', {}) or {}
    print(f"  agent_outputs keys: {list(ao.keys())}")
    for k, v in ao.items():
        if isinstance(v, dict):
            has_sp = 'stream_pending' in v
            print(f"    {k}: keys={list(v.keys())[:8]}{'...' if len(v)>8 else ''}, has_stream_pending={has_sp}")
            if has_sp:
                sp = v.get('stream_pending', {})
                if isinstance(sp, dict):
                    print(f"      stream_pending: max_tokens={sp.get('max_tokens')}, use_safe={sp.get('use_safe')}")
