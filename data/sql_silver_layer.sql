-- ============================================================
-- DuckDB Silver Layer — Medallion Architecture DDL/DML
-- Migrates anomaly detection from Python into SQL.
--
-- Complies with:
--   sql-standards.md  (Idempotent DDL, explicit PKs)
--   HANDOVER.md §4    (Invoice Anomaly Pipeline)
-- ============================================================


-- ── Bronze Layer: Raw JSON Ledger ─────────────────────────────
CREATE TABLE IF NOT EXISTS bronze_invoice_ledger (
    document_id  VARCHAR PRIMARY KEY,
    raw_json     TEXT    NOT NULL,
    ingested_at  TIMESTAMP DEFAULT current_timestamp
);


-- ── Silver Layer: Invoice Audit View ──────────────────────────
-- Unnests line_items from the raw JSON, recalculates line totals
-- and the grand total, then flags arithmetic anomalies entirely
-- in SQL — no Python needed.
CREATE OR REPLACE VIEW vw_silver_invoice_audit AS
WITH parsed AS (
    SELECT
        document_id,
        ingested_at,
        json_extract_string(raw_json, '$.invoice_number')   AS invoice_number,
        json_extract_string(raw_json, '$.vendor_name')      AS vendor_name,
        CAST(json_extract(raw_json, '$.tax_amount')   AS DOUBLE) AS tax_amount,
        CAST(json_extract(raw_json, '$.grand_total')   AS DOUBLE) AS printed_grand_total,
        raw_json
    FROM bronze_invoice_ledger
),
unnested AS (
    SELECT
        p.document_id,
        p.invoice_number,
        p.vendor_name,
        p.tax_amount,
        p.printed_grand_total,
        p.ingested_at,
        CAST(json_extract(li.item, '$.quantity')    AS DOUBLE) AS qty,
        CAST(json_extract(li.item, '$.unit_price')  AS DOUBLE) AS unit_price,
        CAST(json_extract(li.item, '$.total_price')  AS DOUBLE) AS printed_line_total,
        json_extract_string(li.item, '$.item_code')            AS item_code
    FROM parsed p,
         LATERAL (
             SELECT unnest(
                 from_json(json_extract(p.raw_json, '$.line_items'), '["json"]')
             ) AS item
         ) li
),
line_audit AS (
    SELECT
        document_id,
        invoice_number,
        vendor_name,
        tax_amount,
        printed_grand_total,
        ingested_at,
        item_code,
        qty,
        unit_price,
        printed_line_total,
        qty * unit_price                              AS computed_line_total,
        ABS(qty * unit_price - printed_line_total)    AS line_delta
    FROM unnested
)
SELECT
    la.document_id,
    la.invoice_number,
    la.vendor_name,
    la.ingested_at,
    SUM(la.computed_line_total)                                         AS computed_subtotal,
    la.tax_amount,
    la.printed_grand_total,
    SUM(la.computed_line_total) + la.tax_amount                        AS computed_grand_total,
    ABS(SUM(la.computed_line_total) + la.tax_amount - la.printed_grand_total) AS grand_total_delta,
    -- Flag: any line item math mismatch (> 1 cent tolerance)
    BOOL_OR(la.line_delta > 0.01)                                      AS has_line_item_skew,
    -- Flag: subtotal + tax != grand total (> 1 cent tolerance)
    ABS(SUM(la.computed_line_total) + la.tax_amount - la.printed_grand_total) > 0.01 AS has_balance_error,
    -- Combined anomaly flag
    BOOL_OR(la.line_delta > 0.01)
        OR ABS(SUM(la.computed_line_total) + la.tax_amount - la.printed_grand_total) > 0.01
                                                                       AS is_anomaly
FROM line_audit la
GROUP BY
    la.document_id,
    la.invoice_number,
    la.vendor_name,
    la.tax_amount,
    la.printed_grand_total,
    la.ingested_at;


-- ── Silver Layer: Invoice Line Items View ───────────────────────
CREATE OR REPLACE VIEW vw_silver_invoice_line_items AS
WITH parsed AS (
    SELECT
        document_id,
        json_extract_string(raw_json, '$.invoice_number')   AS invoice_number,
        json_extract_string(raw_json, '$.vendor_name')      AS vendor_name,
        raw_json
    FROM bronze_invoice_ledger
),
unnested AS (
    SELECT
        p.document_id,
        p.invoice_number,
        p.vendor_name,
        CAST(json_extract(li.item, '$.quantity')    AS DOUBLE) AS qty,
        CAST(json_extract(li.item, '$.unit_price')  AS DOUBLE) AS unit_price,
        CAST(json_extract(li.item, '$.total_price')  AS DOUBLE) AS printed_line_total,
        json_extract_string(li.item, '$.item_code')            AS item_code
    FROM parsed p,
         LATERAL (
             SELECT unnest(
                 from_json(json_extract(p.raw_json, '$.line_items'), '["json"]')
             ) AS item
         ) li
)
SELECT
    document_id,
    vendor_name,
    invoice_number,
    item_code,
    qty,
    unit_price,
    printed_line_total,
    qty * unit_price                              AS computed_line_total,
    ABS(qty * unit_price - printed_line_total)    AS line_delta,
    ABS(qty * unit_price - printed_line_total) > 0.01 AS has_line_item_skew
FROM unnested;


-- ── Silver Layer: Duplicate Invoice Detection ─────────────────
CREATE OR REPLACE VIEW vw_silver_invoice_duplicates AS
SELECT
    json_extract_string(raw_json, '$.invoice_number') AS invoice_number,
    COUNT(*)                                          AS occurrence_count,
    LIST(document_id)                                 AS duplicate_document_ids,
    MIN(ingested_at)                                  AS first_seen,
    MAX(ingested_at)                                  AS last_seen
FROM bronze_invoice_ledger
GROUP BY json_extract_string(raw_json, '$.invoice_number')
HAVING COUNT(*) > 1;
