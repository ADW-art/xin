"""
SQLite-based LangGraph Checkpoint Saver (persistent across server restarts)

Replaces InMemorySaver so that conversation state (checkpoints, message
history, agent states) survives process restarts and avoids unbounded RAM growth.

Interface: langgraph.checkpoint.base.BaseCheckpointSaver
"""

import os
import sqlite3
import random
import threading
from typing import Any, AsyncIterator, Iterator, Sequence
from contextlib import AbstractContextManager, AbstractAsyncContextManager

import ormsgpack  # used to pack/unpack (serde_type, value) tuples for SQLite BLOB storage

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    get_checkpoint_id,
    get_checkpoint_metadata,
    WRITES_IDX_MAP,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.serde.base import SerializerProtocol
from langchain_core.runnables import RunnableConfig

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id      TEXT NOT NULL,
    checkpoint_ns  TEXT NOT NULL DEFAULT '',
    checkpoint_id  TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    checkpoint     BLOB NOT NULL,
    metadata       BLOB NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS writes (
    thread_id      TEXT NOT NULL,
    checkpoint_ns  TEXT NOT NULL DEFAULT '',
    checkpoint_id  TEXT NOT NULL,
    task_id        TEXT NOT NULL,
    idx            INTEGER NOT NULL,
    channel        TEXT NOT NULL,
    task_path      TEXT NOT NULL DEFAULT '',
    value          BLOB NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE TABLE IF NOT EXISTS blobs (
    thread_id      TEXT NOT NULL,
    checkpoint_ns  TEXT NOT NULL DEFAULT '',
    channel        TEXT NOT NULL,
    version        TEXT NOT NULL,
    type           TEXT NOT NULL,
    value          BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
"""


def _pack_typed(serde, obj: Any) -> bytes:
    """Serialize obj via serde.dumps_typed and pack the (type, data) tuple as msgpack."""
    typed = serde.dumps_typed(obj)
    return ormsgpack.packb(typed)


def _unpack_typed(serde, packed: bytes) -> Any:
    """Unpack a msgpack'd (type, data) tuple and deserialize via serde.loads_typed."""
    typed = ormsgpack.unpackb(packed)
    # ormsgpack.unpackb returns list, convert to tuple for loads_typed
    if isinstance(typed, list):
        typed = (typed[0], typed[1]) if len(typed) == 2 else tuple(typed)
    return serde.loads_typed(typed)


class SqliteSaver(BaseCheckpointSaver[str], AbstractContextManager, AbstractAsyncContextManager):
    """Persistent SQLite checkpoint saver for LangGraph.

    Stores checkpoints, writes, and channel-value blobs in a local SQLite
    database so they survive server restarts.

    Thread-safe: each thread gets its own sqlite3.Connection.
    """

    _db_path: str

    def __init__(
        self,
        db_path: str = "./data/checkpoints.db",
        *,
        serde: SerializerProtocol | None = None,
    ) -> None:
        super().__init__(serde=serde or JsonPlusSerializer())
        self._db_path = os.path.abspath(db_path)
        self._local = threading.local()
        self._init_db()

    # ── thread-local connection ──────────────────────────────────

    @property
    def _conn(self) -> sqlite3.Connection:
        """Return the thread-local connection, creating one if needed."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = self._conn
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    # ── context manager support ─────────────────────────────────

    def __enter__(self) -> "SqliteSaver":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    async def __aenter__(self) -> "SqliteSaver":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    # ── CRUD: get_tuple ──────────────────────────────────────────

    def _load_blobs(self, thread_id: str, checkpoint_ns: str, versions: ChannelVersions) -> dict[str, Any]:
        channel_values: dict[str, Any] = {}
        conn = self._conn
        for channel_name, version in versions.items():
            row = conn.execute(
                "SELECT type, value FROM blobs WHERE thread_id=? AND checkpoint_ns=? AND channel=? AND version=?",
                (thread_id, checkpoint_ns, channel_name, str(version)),
            ).fetchone()
            if row and row["type"] != "empty":
                channel_values[channel_name] = self.serde.loads_typed((row["type"], row["value"]))
        return channel_values

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        conn = self._conn

        if checkpoint_id := get_checkpoint_id(config):
            row = conn.execute(
                "SELECT checkpoint, metadata, parent_checkpoint_id FROM checkpoints "
                "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchone()
            if not row:
                return None
            checkpoint = _unpack_typed(self.serde, row["checkpoint"])
            metadata = _unpack_typed(self.serde, row["metadata"])
            write_rows = conn.execute(
                "SELECT task_id, channel, value FROM writes "
                "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchall()
            pending_writes = [
                (w["task_id"], w["channel"], _unpack_typed(self.serde, w["value"]))
                for w in write_rows
            ]
            return CheckpointTuple(
                config=config,
                checkpoint={
                    **checkpoint,
                    "channel_values": self._load_blobs(thread_id, checkpoint_ns, checkpoint["channel_versions"]),
                },
                metadata=metadata,
                pending_writes=pending_writes,
                parent_config=(
                    {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns,
                                      "checkpoint_id": row["parent_checkpoint_id"]}}
                    if row["parent_checkpoint_id"] else None
                ),
            )

        # No explicit checkpoint_id -> return latest
        row = conn.execute(
            "SELECT checkpoint_id, checkpoint, metadata, parent_checkpoint_id FROM checkpoints "
            "WHERE thread_id=? AND checkpoint_ns=? ORDER BY checkpoint_id DESC LIMIT 1",
            (thread_id, checkpoint_ns),
        ).fetchone()
        if not row:
            return None

        latest_id = row["checkpoint_id"]
        checkpoint = _unpack_typed(self.serde, row["checkpoint"])
        metadata = _unpack_typed(self.serde, row["metadata"])
        write_rows = conn.execute(
            "SELECT task_id, channel, value FROM writes "
            "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
            (thread_id, checkpoint_ns, latest_id),
        ).fetchall()
        pending_writes = [
            (w["task_id"], w["channel"], _unpack_typed(self.serde, w["value"]))
            for w in write_rows
        ]
        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns,
                                      "checkpoint_id": latest_id}},
            checkpoint={
                **checkpoint,
                "channel_values": self._load_blobs(thread_id, checkpoint_ns, checkpoint["channel_versions"]),
            },
            metadata=metadata,
            pending_writes=pending_writes,
            parent_config=(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns,
                                  "checkpoint_id": row["parent_checkpoint_id"]}}
                if row["parent_checkpoint_id"] else None
            ),
        )

    # ── CRUD: list ───────────────────────────────────────────────

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        conn = self._conn

        if config:
            thread_ids = [(config["configurable"]["thread_id"], config["configurable"].get("checkpoint_ns", ""))]
        else:
            rows = conn.execute("SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoints").fetchall()
            thread_ids = [(r["thread_id"], r["checkpoint_ns"]) for r in rows]

        config_checkpoint_id = get_checkpoint_id(config) if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None

        for tid, ckpt_ns in thread_ids:
            query = "SELECT checkpoint_id, checkpoint, metadata, parent_checkpoint_id FROM checkpoints WHERE thread_id=? AND checkpoint_ns=? ORDER BY checkpoint_id DESC"
            params: list = [tid, ckpt_ns]
            rows = conn.execute(query, params).fetchall()

            for row in rows:
                ckpt_id = row["checkpoint_id"]

                if config_checkpoint_id and ckpt_id != config_checkpoint_id:
                    continue
                if before_checkpoint_id and ckpt_id >= before_checkpoint_id:
                    continue

                metadata = _unpack_typed(self.serde, row["metadata"])
                if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                    continue

                if limit is not None:
                    if limit <= 0:
                        return
                    limit -= 1

                checkpoint = _unpack_typed(self.serde, row["checkpoint"])
                write_rows = conn.execute(
                    "SELECT task_id, channel, value FROM writes WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
                    (tid, ckpt_ns, ckpt_id),
                ).fetchall()
                pending_writes = [
                    (w["task_id"], w["channel"], _unpack_typed(self.serde, w["value"]))
                    for w in write_rows
                ]

                yield CheckpointTuple(
                    config={"configurable": {"thread_id": tid, "checkpoint_ns": ckpt_ns, "checkpoint_id": ckpt_id}},
                    checkpoint={
                        **checkpoint,
                        "channel_values": self._load_blobs(tid, ckpt_ns, checkpoint["channel_versions"]),
                    },
                    metadata=metadata,
                    pending_writes=pending_writes,
                    parent_config=(
                        {"configurable": {"thread_id": tid, "checkpoint_ns": ckpt_ns,
                                          "checkpoint_id": row["parent_checkpoint_id"]}}
                        if row["parent_checkpoint_id"] else None
                    ),
                )

    # ── CRUD: put ────────────────────────────────────────────────

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        conn = self._conn

        # Store channel values as blobs
        channel_values: dict[str, Any] = checkpoint.pop("channel_values", {})
        for channel_name, version in new_versions.items():
            if channel_name in channel_values:
                type_blob = self.serde.dumps_typed(channel_values[channel_name])
                conn.execute(
                    "INSERT OR REPLACE INTO blobs (thread_id, checkpoint_ns, channel, version, type, value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (thread_id, checkpoint_ns, channel_name, str(version), type_blob[0], type_blob[1]),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO blobs (thread_id, checkpoint_ns, channel, version, type, value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (thread_id, checkpoint_ns, channel_name, str(version), "empty", b""),
                )

        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        conn.execute(
            "INSERT OR REPLACE INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, "
            "parent_checkpoint_id, checkpoint, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
             _pack_typed(self.serde, checkpoint),
             _pack_typed(self.serde, get_checkpoint_metadata(config, metadata))),
        )
        conn.commit()

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    # ── CRUD: put_writes ────────────────────────────────────────

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id: str = config["configurable"]["thread_id"]
        checkpoint_ns: str = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        conn = self._conn

        for idx, (channel, value) in enumerate(writes):
            channel_idx = WRITES_IDX_MAP.get(channel, idx)
            conn.execute(
                "INSERT OR REPLACE INTO writes (thread_id, checkpoint_ns, checkpoint_id, "
                "task_id, idx, channel, task_path, value) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (thread_id, checkpoint_ns, checkpoint_id, task_id, channel_idx,
                 channel, task_path, _pack_typed(self.serde, value)),
            )
        conn.commit()

    # ── CRUD: delete_thread ──────────────────────────────────────

    def delete_thread(self, thread_id: str) -> None:
        conn = self._conn
        conn.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
        conn.execute("DELETE FROM writes WHERE thread_id=?", (thread_id,))
        conn.execute("DELETE FROM blobs WHERE thread_id=?", (thread_id,))
        conn.commit()

    # ── versioning ───────────────────────────────────────────────

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(current.split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    # ── async wrappers ───────────────────────────────────────────

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        return self.delete_thread(thread_id)
