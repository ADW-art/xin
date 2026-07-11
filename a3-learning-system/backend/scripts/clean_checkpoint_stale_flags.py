"""手动清理 user-X checkpoint 中残留的一次性标志

用途: 当 init_teaching / teaching_continue 等被错误继承时,
     在不杀 uvicorn 的情况下强制重置这些标志

用法: python scripts/clean_checkpoint_stale_flags.py [user_id]
"""
import sys
import os
import pickle


def main():
    sys.path.insert(0, r"E:\code\claude-1\a3-learning-system\backend")

    from app.checkpoint_sqlite import SqliteSaver

    USER_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"=== 清理 user-{USER_ID} 的 checkpoint ===")

    # 直接用 sqlite3 操作 blobs 表
    import sqlite3
    db_path = r"E:\code\claude-1\a3-learning-system\backend\data\checkpoints.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 找 context 通道的所有 version
    cur.execute("""
        SELECT channel, version, type FROM blobs
        WHERE thread_id = ? AND channel = 'context'
        ORDER BY version DESC LIMIT 1
    """, (f"user-{USER_ID}",))

    row = cur.fetchone()
    if not row:
        print(f"  user-{USER_ID} 没有 context 通道")
        return

    channel, version, type_str = row
    print(f"  找到 context 通道: version={version[:20]}...")

    # 读取原始 value
    cur.execute("SELECT value FROM blobs WHERE thread_id=? AND channel=? AND version=?",
                (f"user-{USER_ID}", channel, version))
    vrow = cur.fetchone()
    raw_value = vrow[0]

    # 用 serde 解码
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serde = JsonPlusSerializer()
    ctx = serde.loads_typed((type_str, raw_value))
    print(f"  原始 context keys: {list(ctx.keys()) if isinstance(ctx, dict) else type(ctx)}")

    if not isinstance(ctx, dict):
        print("  context 不是 dict 类型,跳过")
        return

    # 清除一次性标志
    _stale_flags = (
        "init_teaching", "teaching_continue", "replan_path",
        "teach_target_index", "_new_intent_handled", "profile_first",
        "_qa_stage", "_bkt_relevant", "_quality_retry",
    )
    cleaned = []
    for f in _stale_flags:
        if f in ctx:
            ctx.pop(f, None)
            cleaned.append(f)

    if not cleaned:
        print(f"  没有发现需要清除的标志, context 已经干净")
        return

    print(f"  清除标志: {cleaned}")

    # 重新序列化并写回
    new_type, new_value = serde.dumps_typed(ctx)
    cur.execute("""UPDATE blobs SET value=?, type=? WHERE thread_id=? AND channel=? AND version=?""",
                (new_value, new_type, f"user-{USER_ID}", channel, version))
    conn.commit()
    print(f"  清理完成, 写回成功")
    print(f"  新 context keys: {list(ctx.keys())}")
    conn.close()


if __name__ == "__main__":
    main()
