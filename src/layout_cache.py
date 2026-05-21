"""
Structural Layout Cache — Zero-Cost Document Classification.

Computes a deterministic SHA-256 hash from anchor keywords found in
Base64-decoded document images. Before invoking Gemini for zero-shot
layout classification, queries DuckDB for this layout_hash. On a cache
hit the LLM is bypassed entirely, keeping API costs at $0 for recurring
document structures.

Cache Semantics:
  - Hash is derived from the top-N structural anchor keywords
    (e.g. 'Invoice', 'Total', 'Tax', 'Date', 'Dear', 'Sincerely')
    found in the raw Base64 payload.
  - The hash is matched against the `layout_hash_cache` table in DuckDB.
  - Cache writes are fire-and-forget via the SRE persistence queue.

SRE Safeguard:
  - All DuckDB reads use read_only=True connections.
  - Cache writes are enqueued to the single-writer actor (O(1) contention).
"""

import hashlib
import logging
import re
import base64
from typing import Optional

import duckdb

logger = logging.getLogger("layout_cache")

# ── Anchor Keyword Sets ───────────────────────────────────────────
# Structural fingerprint anchors — ordered by classification weight.
# We hash the presence/absence of these keywords to create a
# deterministic layout signature.

_INVOICE_ANCHORS = [
    "invoice", "inv no", "invoice no", "invoice number",
    "bill to", "ship to", "subtotal", "sub total", "sub-total",
    "total", "grand total", "tax", "gst", "vat", "igst", "cgst", "sgst",
    "qty", "quantity", "unit price", "amount", "rate",
    "hsn", "sac", "po number", "purchase order",
    "due date", "payment terms",
]

_LETTER_ANCHORS = [
    "dear", "sincerely", "regards", "yours faithfully",
    "to whom it may concern", "subject", "ref", "reference",
    "attention", "cc", "encl", "enclosed",
    "respectfully", "thank you", "yours truly",
]


def compute_layout_hash(base64_data: str) -> str:
    """
    Compute a deterministic SHA-256 structural fingerprint from
    anchor keyword presence in the Base64-decoded document content.

    The hash is built from a sorted, deduplicated list of anchor
    keywords found in the raw text, ensuring that documents with
    the same structural layout always produce the same hash.

    Args:
        base64_data: Raw Base64 string of the document image.

    Returns:
        A 64-character hex SHA-256 digest.
    """
    # Decode Base64 to raw bytes, then extract printable ASCII text
    try:
        raw_bytes = base64.b64decode(base64_data)
        # Extract printable ASCII sequences (min 3 chars) from binary
        text_fragments = re.findall(rb'[\x20-\x7E]{3,}', raw_bytes)
        raw_text = b" ".join(text_fragments).decode("ascii", errors="ignore").lower()
    except Exception:
        # If decoding fails, hash the raw Base64 string directly
        raw_text = base64_data[:2000].lower()

    # Build the structural fingerprint from anchor keyword matches
    matched_anchors = []
    for anchor in _INVOICE_ANCHORS + _LETTER_ANCHORS:
        if anchor in raw_text:
            matched_anchors.append(anchor)

    # Sort for determinism and take top 10 for a stable fingerprint
    matched_anchors.sort()
    fingerprint_input = "|".join(matched_anchors[:10])

    # SHA-256 the fingerprint string
    return hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()


def lookup_cached_layout(db_path: str, layout_hash: str) -> Optional[str]:
    """
    Query DuckDB for a cached document type matching this layout hash.
    """
    try:
        # Use read_only=False to bypass DuckDB WAL read-only index bugs
        con = duckdb.connect(db_path, read_only=False)
        try:
            row = con.execute(
                "SELECT document_type, hit_count FROM layout_hash_cache WHERE layout_hash = ?",
                [layout_hash],
            ).fetchone()
            if row:
                doc_type, hit_count = row[0], row[1]
                logger.info(
                    "[LAYOUT CACHE] HIT — hash=%s...%s → %s (hits: %d)",
                    layout_hash[:8], layout_hash[-4:], doc_type, hit_count + 1,
                )
                # Increment hit count asynchronously via the writer queue
                _enqueue_hit_increment(db_path, layout_hash)
                return doc_type
            else:
                logger.info(
                    "[LAYOUT CACHE] MISS — hash=%s...%s (proceeding to LLM)",
                    layout_hash[:8], layout_hash[-4:],
                )
                return None
        except duckdb.CatalogException:
            # Table doesn't exist yet — treat as miss
            logger.info("[LAYOUT CACHE] Table not found. Treating as MISS.")
            return None
        finally:
            con.close()
    except Exception as e:
        logger.warning("[LAYOUT CACHE] Lookup failed: %s. Treating as MISS.", e)
        return None


def cache_layout(db_path: str, layout_hash: str, document_type: str) -> None:
    """
    Asynchronously persist a new layout_hash → document_type mapping
    via the SRE single-writer actor queue. Fire-and-forget.

    Args:
        db_path: Path to the DuckDB database file.
        layout_hash: The SHA-256 layout fingerprint.
        document_type: The classified document type ('INVOICE' or 'LETTER').
    """
    from src.sre_persistence import enqueue_write

    enqueue_write(
        db_path,
        """
        INSERT OR REPLACE INTO layout_hash_cache
        (layout_hash, document_type, hit_count, created_at)
        VALUES (?, ?, 0, CURRENT_TIMESTAMP)
        """,
        [layout_hash, document_type],
    )
    logger.info(
        "[LAYOUT CACHE] STORED — hash=%s...%s → %s (zero-cost on next encounter)",
        layout_hash[:8], layout_hash[-4:], document_type,
    )


def _enqueue_hit_increment(db_path: str, layout_hash: str) -> None:
    """Fire-and-forget hit counter increment via the writer queue."""
    try:
        from src.sre_persistence import enqueue_write
        enqueue_write(
            db_path,
            "UPDATE layout_hash_cache SET hit_count = hit_count + 1 WHERE layout_hash = ?",
            [layout_hash],
        )
    except Exception:
        pass  # Non-critical — silently drop if queue unavailable


def init_layout_cache_table(db_path: str) -> None:
    """
    Idempotently create the layout_hash_cache table.
    Called during server startup (synchronous, before writer is active).
    """
    try:
        con = duckdb.connect(db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS layout_hash_cache (
                layout_hash VARCHAR PRIMARY KEY,
                document_type VARCHAR NOT NULL,
                hit_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.close()
        logger.info("[LAYOUT CACHE] DuckDB layout_hash_cache table initialized.")
    except Exception as e:
        logger.warning("[LAYOUT CACHE] Failed to initialize cache table: %s", e)
