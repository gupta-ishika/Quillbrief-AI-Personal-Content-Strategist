import os
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import settings


def resolve_checkpoints_db_path(url: str | None = None) -> str:
    raw_url = url or settings.checkpoints_database_url
    if raw_url.startswith("sqlite:///"):
        path = raw_url.replace("sqlite:///", "")
        return path
    if raw_url.startswith("sqlite://"):
        return raw_url.replace("sqlite://", "")
    return raw_url


def configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.close()


async def configure_async_sqlite_connection(conn: aiosqlite.Connection) -> None:
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA journal_mode = WAL;")
    await conn.execute("PRAGMA busy_timeout = 5000;")


@contextmanager
def get_sqlite_checkpointer(db_path: str | None = None) -> Iterator[SqliteSaver]:
    """Sync context manager providing SqliteSaver on its dedicated database file (ADR-007)."""
    resolved_path = resolve_checkpoints_db_path(db_path)

    # Ensure parent directory exists if file path
    if resolved_path != ":memory:":
        parent = Path(resolved_path).parent
        if not parent.exists():
            os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(resolved_path, check_same_thread=False)
    configure_sqlite_connection(conn)
    try:
        checkpointer = SqliteSaver(conn)
        checkpointer.setup()
        yield checkpointer
    finally:
        conn.close()


@asynccontextmanager
async def get_async_sqlite_checkpointer(
    db_path: str | None = None,
) -> AsyncIterator[AsyncSqliteSaver]:
    """Async context manager providing AsyncSqliteSaver on dedicated database file."""
    resolved_path = resolve_checkpoints_db_path(db_path)

    if resolved_path != ":memory:":
        parent = Path(resolved_path).parent
        if not parent.exists():
            os.makedirs(parent, exist_ok=True)

    async with aiosqlite.connect(resolved_path) as conn:
        await configure_async_sqlite_connection(conn)
        checkpointer = AsyncSqliteSaver(conn)
        await checkpointer.setup()
        yield checkpointer


def delete_thread_checkpoints(thread_id: str, db_path: str | None = None) -> int:
    """Deletes all checkpoints and checkpoint writes for a given thread_id.

    Required for ADR-024 / DATABASE.md Section 8 & 11 (Creator data deletion).
    """
    resolved_path = resolve_checkpoints_db_path(db_path)
    if not os.path.exists(resolved_path) and resolved_path != ":memory:":
        return 0

    deleted_count = 0
    conn = sqlite3.connect(resolved_path)
    try:
        configure_sqlite_connection(conn)
        cursor = conn.cursor()
        # Find tables created by langgraph checkpoint
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'")
        if cursor.fetchone():
            cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            deleted_count += cursor.rowcount

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoint_writes'"
        )
        if cursor.fetchone():
            cursor.execute("DELETE FROM checkpoint_writes WHERE thread_id = ?", (thread_id,))
            deleted_count += cursor.rowcount

        conn.commit()
    finally:
        conn.close()
    return deleted_count
