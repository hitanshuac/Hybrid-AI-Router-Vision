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


# ── DuckDB WAL Checkpoint ─────────────────────────────────────────
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.path.join(_DB_DIR, "pipeline_metrics.db")


def force_checkpoint_sync() -> None:
    """Blocking DuckDB CHECKPOINT — flushes the WAL to disk. Runs in worker thread."""
    try:
        con = duckdb.connect(_DB_PATH)
        con.execute("CHECKPOINT;")
        con.close()
        logger.info("[SRE] DuckDB WAL checkpoint completed successfully.")
    except Exception as e:
        logger.error("[SRE] DuckDB checkpoint failed: %s", e)


async def force_checkpoint() -> None:
    """Async wrapper — offloads the WAL checkpoint flush to a worker thread."""
    async with _DUCKDB_WRITE_LOCK:
        await asyncio.to_thread(force_checkpoint_sync)


# ── CQRS Read Layer — Silver View Queries ─────────────────────────
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
