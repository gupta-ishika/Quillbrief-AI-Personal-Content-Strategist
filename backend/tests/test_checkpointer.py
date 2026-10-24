import os
import tempfile

import pytest
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

from app.graph.checkpointer import (
    delete_thread_checkpoints,
    get_async_sqlite_checkpointer,
    get_sqlite_checkpointer,
    resolve_checkpoints_db_path,
)


def test_resolve_checkpoints_db_path() -> None:
    assert resolve_checkpoints_db_path("sqlite:///./checkpoints.db") == "./checkpoints.db"
    assert resolve_checkpoints_db_path("sqlite:///:memory:") == ":memory:"
    assert resolve_checkpoints_db_path("/tmp/test.db") == "/tmp/test.db"


def test_sync_sqlite_checkpointer_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_checkpoints.db")
        thread_id = "thread_sync_001"

        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint: Checkpoint = {
            "v": 1,
            "id": "cp_001",
            "ts": "2026-10-24T22:00:00Z",
            "channel_values": {"user_goal": "Grow subscriber base", "execution_steps": 1},
            "channel_versions": {"user_goal": 1, "execution_steps": 1},
            "versions_seen": {},
            "pending_sends": [],
        }
        metadata: CheckpointMetadata = {"source": "input", "step": 1, "writes": {}, "score": 1}

        with get_sqlite_checkpointer(db_path) as checkpointer:
            # Store checkpoint
            checkpointer.put(config, checkpoint, metadata, {})

            # Retrieve checkpoint
            saved = checkpointer.get(config)
            assert saved is not None
            assert saved["id"] == "cp_001"
            assert saved["channel_values"]["user_goal"] == "Grow subscriber base"


@pytest.mark.asyncio
async def test_async_sqlite_checkpointer_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_async_checkpoints.db")
        thread_id = "thread_async_001"

        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint: Checkpoint = {
            "v": 1,
            "id": "cp_async_001",
            "ts": "2026-10-24T22:05:00Z",
            "channel_values": {"user_goal": "Publish 2 shorts", "execution_steps": 2},
            "channel_versions": {"user_goal": 1, "execution_steps": 2},
            "versions_seen": {},
            "pending_sends": [],
        }
        metadata: CheckpointMetadata = {"source": "input", "step": 2, "writes": {}, "score": 1}

        async with get_async_sqlite_checkpointer(db_path) as checkpointer:
            await checkpointer.aput(config, checkpoint, metadata, {})
            saved = await checkpointer.aget(config)
            assert saved is not None
            assert saved["id"] == "cp_async_001"
            assert saved["channel_values"]["user_goal"] == "Publish 2 shorts"


def test_delete_thread_checkpoints_creator_isolation() -> None:
    """Verifies ADR-024 / DATABASE.md: Deletion removes checkpoints for specified thread only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_del_checkpoints.db")
        thread_1 = "thread_to_delete"
        thread_2 = "thread_to_keep"

        cfg1 = {"configurable": {"thread_id": thread_1, "checkpoint_ns": ""}}
        cfg2 = {"configurable": {"thread_id": thread_2, "checkpoint_ns": ""}}

        cp1: Checkpoint = {
            "v": 1,
            "id": "cp_1",
            "ts": "2026-10-24T22:00:00Z",
            "channel_values": {"step": 1},
            "channel_versions": {"step": 1},
            "versions_seen": {},
            "pending_sends": [],
        }
        cp2: Checkpoint = {
            "v": 1,
            "id": "cp_2",
            "ts": "2026-10-24T22:00:00Z",
            "channel_values": {"step": 2},
            "channel_versions": {"step": 2},
            "versions_seen": {},
            "pending_sends": [],
        }
        meta: CheckpointMetadata = {"source": "input", "step": 1, "writes": {}, "score": 1}

        with get_sqlite_checkpointer(db_path) as checkpointer:
            checkpointer.put(cfg1, cp1, meta, {})
            checkpointer.put(cfg2, cp2, meta, {})

        # Delete thread 1
        deleted = delete_thread_checkpoints(thread_1, db_path=db_path)
        assert deleted >= 1

        with get_sqlite_checkpointer(db_path) as checkpointer:
            # Thread 1 should be gone
            assert checkpointer.get(cfg1) is None
            # Thread 2 must remain
            saved_2 = checkpointer.get(cfg2)
            assert saved_2 is not None
            assert saved_2["id"] == "cp_2"
