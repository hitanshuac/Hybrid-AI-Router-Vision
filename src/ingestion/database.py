import duckdb
import os
import logging

logger = logging.getLogger("ingestion.db")

def get_duckdb_conn(db_path: str = "data/usage.db"):
    """
    Scaffolds a DuckDB connection following SRE best practices:
    - Enables Write-Ahead Logging (WAL) for integrity.
    - Sets strict memory limits to prevent OOM.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = duckdb.connect(db_path)
    
    # Enforce WAL and Memory Limits (DuckDB Optimizer Skill)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA memory_limit='2GB';")
    
    logger.info(f"Connected to DuckDB at {db_path} (WAL enabled, memory_limit=2GB)")
    return conn

def initialize_tables(conn):
    """Initializes the usage_metrics table with a primary key for idempotency."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_metrics (
            request_id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            model_name VARCHAR,
            provider VARCHAR,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            status VARCHAR,
            latency_ms DOUBLE
        )
    """)
    logger.info("Initialized usage_metrics table.")
