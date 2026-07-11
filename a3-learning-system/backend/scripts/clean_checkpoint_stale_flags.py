"""手动清理 user-X checkpoint 中残留的一次性标志

用途: 当 init_teaching / teaching_continue 等被错误继承时,
     在不杀 uvicorn 的情况下强制重置这些标志

用法:
  python scripts/clean_checkpoint_stale_flags.py [user_id]   # 清理 user_id (默认 1)
  python scripts/clean_checkpoint_stale_flags.py --list      # 列出所有 checkpoint
  python scripts/clean_checkpoint_stale_flags.py --help      # 显示帮助
"""
import sys
import os
import pickle
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="清理 LangGraph checkpoint 中残留的一次性标志",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python scripts/clean_checkpoint_stale_flags.py 1        # 清理 user-1\n"
               "  python scripts/clean_checkpoint_stale_flags.py --list   # 列出所有 checkpoints\n"
               "  python scripts/clean_checkpoint_stale_flags.py --all    # 清理所有 user"
    )
    parser.add_argument("user_id", type=int, nargs="?", default=None,
                        help="要清理的 user_id (默认 1)")
    parser.add_argument("--list", action="store_true", help="列出所有 checkpoints")
    parser.add_argument("--all", action="store_true", help="清理所有 user")
    args = parser.parse_args()

    sys.path.insert(0, r"E:\code\claude-1\a3-learning-system\backend")
    from app.checkpoint_sqlite import SqliteSaver

    # --list 模式
    if args.list:
        import sqlite3
        db_path = r"E:\code\claude-1\a3-learning-system\backend\data\checkpoints.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT thread_id FROM writes")
        thread_ids = [r[0] for r in cur.fetchall()]
        print(f"=== Checkpoint threads ({len(thread_ids)}) ===")
        for tid in thread_ids:
            # thread_id 格式: "user-X-..."
            user_part = tid.split("-")[1] if "-" in tid else "?"
            print(f"  {tid} (user-{user_part})")
        conn.close()
        return

    if args.all:
        # 清理所有 user
        import sqlite3
        db_path = r"E:\code\claude-1\a3-learning-system\backend\data\checkpoints.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT thread_id FROM writes")
        thread_ids = [r[0] for r in cur.fetchall()]
        for tid in thread_ids:
            user_part = int(tid.split("-")[1]) if "-" in tid and tid.split("-")[1].isdigit() else 1
            print(f"=== 清理 thread {tid} (user-{user_part}) ===")
        print(f"\n共 {len(thread_ids)} 个 thread, 请单独用 user_id 清理")
        conn.close()
        return

    USER_ID = args.user_id if args.user_id is not None else 1
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
