# Standalone Repository: Hybrid-AI-Router-Vision

Welcome to the independent, standalone codebase specifically optimized for multi-modal and vision capabilities. This repository has been decoupled from the text-only router to establish a robust, specialized service layer.

---

## 1. Core Architecture & SRE Stack

Our system is engineered to guarantee extremely high throughput, low latency, and deterministic reliability. The technical core consists of:

*   **FastAPI (ASGI Core)**: Built for high-concurrency async operations. FastAPI manages the primary gateway API surface, ensuring minimum network overhead and robust request routing.
*   **DuckDB (Resilient Analytical & Caching Store)**: Integrated as our low-latency, localized storage engine. DuckDB manages semantic caching, request telemetry, and audit logs.
    *   *SRE Safeguard*: All DuckDB operations are completely decoupled from the main ASGI event loop via dedicated `asyncio.to_thread` pools with a process-wide `asyncio.Lock` to prevent concurrent writer crashes.
*   **Pydantic (Strict Data Validation)**: Every ingress request and egress response is validated using strict, declarative Pydantic schemas. This prevents downstream type failures and guarantees a highly reliable payload contract.

---

## 2. Primary Objective: Multi-Modal Payload Processing

The absolute priority for this repository is the seamless processing and routing of **Multi-Modal payloads (specifically Base64-encoded Images)**:

1.  **Direct Image Injection**: Support incoming payloads that contain raw Base64 image strings directly inside the API request structure.
2.  **Schema Enforcement**: Utilize specialized Pydantic models to parse, validate, and sanitize incoming multi-modal requests before they enter the model cascade.
3.  **Cascading Waterfall Routing**: Intelligently route multi-modal inputs through high-availability vision models (Groq, OpenRouter, NVIDIA NIM, Gemini, Ollama), utilizing an automated cascade fallback system.

---

## 3. Operations & Observability

To maintain SRE compliance, any new multi-modal endpoint must adhere to the following telemetry standards:

*   **Strict Event-Loop Protection**: Under no circumstances should synchronous filesystem reads/writes or database ingestion tasks block the main asynchronous threads. All blocking I/O is offloaded via `asyncio.to_thread` in `sre_persistence.py`.
*   **Circuit Breaker Protocol**: A stateful circuit breaker (`circuit_breaker.py`) monitors upstream Vision LLM (Gemini) responses. After 3 consecutive 429/503 failures, the circuit trips OPEN, halts outbound requests for a 60-second cooldown, and triggers a DuckDB WAL checkpoint to secure data state.
*   **O(1) Content Negotiation**: Dynamic provider health checks and token hydration must be performed through O(1) in-memory or localized caching, avoiding continuous active network/disk polling.
*   **Telemetry Schemas**: Every multi-modal transaction is persisted into DuckDB with exact latency numbers, token counts, and input/output payload hashes.

---

## 4. Invoice Anomaly Pipeline

The pipeline utilizes a 4-stage SRE-grade architecture to process invoices:
1. **Ingress Validation**: Validates `InvoiceIngress` via Pydantic to catch malformed payloads.
2. **Vision Extraction**: Processes the Base64 image using Gemini 2.5 Flash natively (with `asyncio.to_thread` for event loop protection).
3. **SQL Silver Layer (Medallion Architecture)**: Anomaly detection is implemented in DuckDB SQL views (Silver Layer) for high-performance deterministic checks (Line Item Math, Grand Total Balance, Duplicate Document Detection) and strict CQRS.
4. **SRE Persistence & DLQ Quarantine**: Valid data is written to DuckDB via an async lock-guarded offloader (`asyncio.to_thread` in `sre_persistence.py`) using `INSERT OR REPLACE`. Malformed requests are safely routed to a daily-partitioned DLQ Parquet file in the `data/quarantine/` directory without blocking the active stream.

---

## 5. CQRS Read Layer & Silver View Endpoints

The system enforces strict Command Query Responsibility Segregation (CQRS). All read operations use `duckdb.connect(read_only=True)` to eliminate lock contention with the ingestion writer.

### Endpoints

| Endpoint | Purpose | Format Support |
|---|---|---|
| `POST /api/v1/pipeline/ingest` | Polymorphic document ingestion (Invoice/Letter) | JSON |
| `GET /api/v1/pipeline/invoices` | Invoice audit summary (header-level aggregation) | JSON, HTML, CSV, Markdown |
| `GET /api/v1/pipeline/invoices/lines` | Invoice line items detail (unnested rows) | JSON, HTML, CSV, Markdown |
| `GET /api/v1/pipeline/anomalies/duplicates` | Duplicate invoice detection | JSON, HTML, CSV, Markdown |

### Silver Layer Views (`data/sql_silver_layer.sql`)

| View | Source Table | Purpose |
|---|---|---|
| `vw_silver_invoice_audit` | `bronze_invoice_ledger` | Recalculates line totals and grand totals, flags arithmetic anomalies |
| `vw_silver_invoice_line_items` | `bronze_invoice_ledger` | Unnests individual line items with per-row delta audits |
| `vw_silver_invoice_duplicates` | `bronze_invoice_ledger` | Groups by invoice number, flags entries with count > 1 |

### SRE Guardrails
- All DB reads use `asyncio.to_thread` (prevents event loop blocking).
- All read connections use `read_only=True` (prevents lock contention).
- All queries enforce `LIMIT 50` (or `LIMIT 200` for line items) to prevent memory overflow.
- Compound search via `CONCAT(vendor_name, ' ', invoice_number) ILIKE ?` for flexible querying.
