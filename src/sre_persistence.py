"""
SRE Persistence Layer — Async Single-Writer Actor Pattern.

Eliminates all process-wide locks. API worker coroutines drop validated
payloads into an asyncio.Queue (O(1), zero contention). A single
background writer task exclusively drains the queue and performs batch
INSERT OR REPLACE commits into DuckDB, preventing concurrent-writer crashes.

Complies with:
  - HANDOVER.md §3  (Strict Event-Loop Protection)
  - sql-standards.md (INSERT OR REPLACE idempotency)
  - data-validation.md §2 (Quarantine Protocol)
"""

import os
import asyncio
import logging
import datetime
from dataclasses import dataclass
from typing import Optional

import duckdb
import pandas as pd

logger = logging.getLogger("sre_persistence")

# ── Path Constants ────────────────────────────────────────────────
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.environ.get("TEST_DB_PATH", os.path.join(_DB_DIR, "pipeline_metrics.db"))

# ── Write Queue Message Types ─────────────────────────────────────

@dataclass
class _WriteMsg:
    """Standard DuckDB INSERT message."""
    db_path: str
    sql: str
    params: list


@dataclass
class _DLQMsg:
    """Dead-Letter Queue shunt message."""
    db_dir: str
    doc_id: str
    error_msg: str


@dataclass
class _CheckpointMsg:
    """Sentinel message to trigger a WAL checkpoint."""
    pass


@dataclass
class _ShutdownMsg:
    """Sentinel message to stop the writer worker."""
    pass


# ── Async Write Queue ────────────────────────────────────────────
_write_queue: asyncio.Queue = None  # Initialized in start_writer()
_writer_task: asyncio.Task = None


async def _writer_worker() -> None:
    """
    Single-writer actor. Runs as a background asyncio.Task and
    exclusively drains the write queue.  All DuckDB mutations flow
    through this single coroutine, eliminating lock contention entirely.
    """
    logger.info("[SRE] Single-writer actor started. Draining write queue...")
    while True:
        msg = await _write_queue.get()
        try:
            if isinstance(msg, _ShutdownMsg):
                logger.info("[SRE] Shutdown sentinel received. Draining remaining queue items...")
                # Drain remaining items before exiting
                while not _write_queue.empty():
                    remaining = _write_queue.get_nowait()
                    if isinstance(remaining, _WriteMsg):
                        await asyncio.to_thread(_sync_write_duckdb, remaining.db_path, remaining.sql, remaining.params)
                    elif isinstance(remaining, _DLQMsg):
                        await asyncio.to_thread(_sync_shunt_to_dlq, remaining.db_dir, remaining.doc_id, remaining.error_msg)
                    elif isinstance(remaining, _CheckpointMsg):
                        await asyncio.to_thread(_sync_force_checkpoint)
                    _write_queue.task_done()
                logger.info("[SRE] Single-writer actor stopped cleanly.")
                return

            elif isinstance(msg, _WriteMsg):
                await asyncio.to_thread(_sync_write_duckdb, msg.db_path, msg.sql, msg.params)

            elif isinstance(msg, _DLQMsg):
                await asyncio.to_thread(_sync_shunt_to_dlq, msg.db_dir, msg.doc_id, msg.error_msg)

            elif isinstance(msg, _CheckpointMsg):
                await asyncio.to_thread(_sync_force_checkpoint)

        except Exception as e:
            logger.error("[SRE] Writer actor error processing message %s: %s", type(msg).__name__, e)
        finally:
            _write_queue.task_done()


# ── Lifecycle Hooks ───────────────────────────────────────────────
async def start_writer() -> None:
    """Initialize the write queue and spawn the background writer task.
    Call this from FastAPI's startup event."""
    global _write_queue, _writer_task
    _write_queue = asyncio.Queue(maxsize=1000)
    _writer_task = asyncio.create_task(_writer_worker())
    logger.info("[SRE] Write queue initialized (maxsize=1000). Writer task spawned.")


async def stop_writer() -> None:
    """Send shutdown sentinel and wait for the writer to drain.
    Call this from FastAPI's shutdown event."""
    global _writer_task
    if _write_queue and _writer_task:
        await _write_queue.put(_ShutdownMsg())
        await _writer_task
        _writer_task = None
        logger.info("[SRE] Writer task shut down cleanly.")


# ── Fire-and-Forget Public API ────────────────────────────────────
def enqueue_write(db_path: str, sql: str, params: list) -> None:
    """
    Drop a DuckDB write payload onto the async queue. O(1), zero contention.
    Non-blocking — returns immediately. The background writer task will
    process this message exclusively.
    """
    if _write_queue is None:
        logger.error("[SRE] Write queue not initialized. Call start_writer() first.")
        return
    try:
        _write_queue.put_nowait(_WriteMsg(db_path=db_path, sql=sql, params=params))
    except asyncio.QueueFull:
        logger.error("[SRE] Write queue is FULL (1000 items). Dropping write payload. Possible backpressure.")


def enqueue_dlq(db_dir: str, doc_id: str, error_msg: str) -> None:
    """
    Drop a DLQ shunt message onto the async queue. O(1), zero contention.
    Non-blocking — returns immediately.
    """
    logger.error(
        "[PIPELINE] Malformed or failed payload. Routing to DLQ. Error: %s",
        error_msg,
    )
    if _write_queue is None:
        logger.error("[SRE] Write queue not initialized. Call start_writer() first.")
        return
    try:
        _write_queue.put_nowait(_DLQMsg(db_dir=db_dir, doc_id=doc_id, error_msg=error_msg))
    except asyncio.QueueFull:
        logger.error("[SRE] Write queue is FULL. Dropping DLQ payload for doc %s.", doc_id)


# ── Backward-compatible async wrappers (for existing callers) ─────
async def async_write_duckdb_idempotent(db_path: str, sql: str, params: list) -> None:
    """Backward-compatible wrapper. Enqueues the write and returns immediately."""
    enqueue_write(db_path, sql, params)


async def async_shunt_to_dlq(db_dir: str, doc_id: str, error_msg: str) -> None:
    """Backward-compatible wrapper. Enqueues the DLQ shunt and returns immediately."""
    enqueue_dlq(db_dir, doc_id, error_msg)


# ── Thread-Safe DuckDB Writer (runs in worker thread) ─────────────
def _sync_write_duckdb(db_path: str, sql: str, params: list) -> None:
    """Blocking DuckDB insert — runs inside a worker thread only."""
    con = duckdb.connect(db_path)
    try:
        con.execute(sql, params)
    finally:
        con.close()


# ── Dead-Letter Queue (DLQ) Writer ────────────────────────────────
def _sync_shunt_to_dlq(db_dir: str, doc_id: str, error_msg: str) -> None:
    """Blocking Parquet append — runs inside a worker thread only."""
    quarantine_dir = os.path.join(db_dir, "quarantine")
    os.makedirs(quarantine_dir, exist_ok=True)

    dlq_file = os.path.join(
        quarantine_dir,
        f"dlq_{datetime.date.today().strftime('%Y%m%d')}.parquet",
    )

    error_record = pd.DataFrame([{
        "document_id": doc_id,
        "timestamp": datetime.datetime.utcnow(),
        "error_msg": error_msg,
    }])

    try:
        if os.path.exists(dlq_file):
            existing_df = pd.read_parquet(dlq_file)
            updated_df = pd.concat([existing_df, error_record], ignore_index=True)
            updated_df.to_parquet(dlq_file)
        else:
            error_record.to_parquet(dlq_file)
        logger.info("[DLQ] Quarantined doc %s → %s", doc_id, dlq_file)
    except Exception as pq_err:
        logger.error("[DLQ] Failed to write quarantine parquet: %s", pq_err)


# ── DuckDB WAL Checkpoint ─────────────────────────────────────────
def _sync_force_checkpoint() -> None:
    """Blocking DuckDB CHECKPOINT — flushes the WAL to disk. Runs in worker thread."""
    try:
        con = duckdb.connect(_DB_PATH)
        con.execute("CHECKPOINT;")
        con.close()
        logger.info("[SRE] DuckDB WAL checkpoint completed successfully.")
    except Exception as e:
        logger.error("[SRE] DuckDB checkpoint failed: %s", e)


# Keep the old name alive for circuit_breaker.py import
force_checkpoint_sync = _sync_force_checkpoint


async def force_checkpoint() -> None:
    """Async wrapper — enqueues a WAL checkpoint via the writer actor."""
    if _write_queue:
        try:
            _write_queue.put_nowait(_CheckpointMsg())
        except asyncio.QueueFull:
            logger.error("[SRE] Write queue FULL. Cannot enqueue checkpoint.")
    else:
        # Fallback if writer not started yet
        await asyncio.to_thread(_sync_force_checkpoint)


# ── CQRS Read Layer — Silver View Queries ─────────────────────────
# Reads use read_only=True connections — zero contention with the writer actor.

def _sync_get_invoice_audit(document_id: str = None, search_query: str = None) -> list[dict]:
    """Blocking read against vw_silver_invoice_audit. Read-only connection."""
    con = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        if document_id:
            df = con.execute(
                "SELECT * FROM vw_silver_invoice_audit WHERE document_id = ? LIMIT 50",
                [document_id],
            ).fetchdf()
        elif search_query:
            # Compound ILIKE search for Vendor + Invoice Number
            df = con.execute(
                "SELECT * FROM vw_silver_invoice_audit WHERE CONCAT(vendor_name, ' ', invoice_number) ILIKE ? LIMIT 50",
                [f"%{search_query}%"],
            ).fetchdf()
        else:
            df = con.execute(
                "SELECT * FROM vw_silver_invoice_audit ORDER BY ingested_at DESC LIMIT 50"
            ).fetchdf()
        return df.to_dict('records')
    except duckdb.CatalogException:
        logger.warning("[CQRS] vw_silver_invoice_audit view not found. Run sql_silver_layer.sql first.")
        return []
    finally:
        con.close()


def _sync_get_invoice_lines(document_id: str = None, search_query: str = None) -> list[dict]:
    """Blocking read against vw_silver_invoice_line_items. Read-only connection."""
    con = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        if document_id:
            df = con.execute(
                "SELECT * FROM vw_silver_invoice_line_items WHERE document_id = ? LIMIT 200",
                [document_id],
            ).fetchdf()
        elif search_query:
            df = con.execute(
                "SELECT * FROM vw_silver_invoice_line_items WHERE CONCAT(vendor_name, ' ', invoice_number) ILIKE ? LIMIT 200",
                [f"%{search_query}%"],
            ).fetchdf()
        else:
            df = con.execute(
                "SELECT * FROM vw_silver_invoice_line_items LIMIT 200"
            ).fetchdf()
        return df.to_dict('records')
    except duckdb.CatalogException:
        logger.warning("[CQRS] vw_silver_invoice_line_items view not found. Run sql_silver_layer.sql first.")
        return []
    finally:
        con.close()


def _sync_get_duplicates() -> list[dict]:
    """Blocking read against vw_silver_invoice_duplicates. Read-only connection."""
    con = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        df = con.execute("SELECT * FROM vw_silver_invoice_duplicates LIMIT 50").fetchdf()
        return df.to_dict('records')
    except duckdb.CatalogException:
        logger.warning("[CQRS] vw_silver_invoice_duplicates view not found. Run sql_silver_layer.sql first.")
        return []
    finally:
        con.close()


async def async_get_invoice_audit(document_id: str = None, search_query: str = None) -> list[dict]:
    """CQRS read — offloads Silver Layer invoice audit query to a worker thread."""
    return await asyncio.to_thread(_sync_get_invoice_audit, document_id, search_query)


async def async_get_invoice_lines(document_id: str = None, search_query: str = None) -> list[dict]:
    """CQRS read — offloads Silver Layer line items query to a worker thread."""
    return await asyncio.to_thread(_sync_get_invoice_lines, document_id, search_query)


async def async_get_duplicates() -> list[dict]:
    """CQRS read — offloads Silver Layer duplicate detection query to a worker thread."""
    return await asyncio.to_thread(_sync_get_duplicates)
