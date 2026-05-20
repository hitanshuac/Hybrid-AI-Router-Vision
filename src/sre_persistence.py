"""
SRE Persistence Layer — Compute Separation Module.

Isolates ALL blocking I/O (DuckDB writes, Parquet DLQ dumps) from the
FastAPI ASGI event loop via asyncio.to_thread.  A single asyncio.Lock
serializes DuckDB writers to prevent concurrent-writer crashes.

Complies with:
  - HANDOVER.md §3  (Strict Event-Loop Protection)
  - sql-standards.md (INSERT OR REPLACE idempotency)
  - data-validation.md §2 (Quarantine Protocol)
"""

import os
import asyncio
import logging
import datetime

import duckdb
import pandas as pd

logger = logging.getLogger("sre_persistence")

# ── Singleton Write Lock ───────────────────────────────────────────
# Prevents concurrent DuckDB writer crashes within a single process.
_DUCKDB_WRITE_LOCK = asyncio.Lock()


# ── Thread-Safe DuckDB Writer ─────────────────────────────────────
def _sync_write_duckdb(db_path: str, sql: str, params: list) -> None:
    """Blocking DuckDB insert — runs inside a worker thread only."""
    con = duckdb.connect(db_path)
    try:
        con.execute(sql, params)
    finally:
        con.close()


async def async_write_duckdb_idempotent(
    db_path: str,
    sql: str,
    params: list,
) -> None:
    """
    Acquire the process-wide write lock, then offload the DuckDB insert
    to a background thread so the ASGI event loop is never blocked.

    The caller is responsible for using INSERT OR REPLACE (or ON CONFLICT)
    SQL to satisfy sql-standards.md idempotency requirements.
    """
    async with _DUCKDB_WRITE_LOCK:
        await asyncio.to_thread(_sync_write_duckdb, db_path, sql, params)


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


async def async_shunt_to_dlq(db_dir: str, doc_id: str, error_msg: str) -> None:
    """
    Offloads the Parquet DLQ write to a worker thread.
    Daily-partitioned file: data/quarantine/dlq_YYYYMMDD.parquet
    """
    logger.error(
        "[PIPELINE] Malformed or failed payload. Routing to DLQ. Error: %s",
        error_msg,
    )
    await asyncio.to_thread(_sync_shunt_to_dlq, db_dir, doc_id, error_msg)
