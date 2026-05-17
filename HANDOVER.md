# Standalone Repository: Hybrid-AI-Router-Vision

Welcome to the independent, standalone codebase specifically optimized for multi-modal and vision capabilities. This repository has been decoupled from the text-only router to establish a robust, specialized service layer.

---

## 1. Core Architecture & SRE Stack

Our system is engineered to guarantee extremely high throughput, low latency, and deterministic reliability. The technical core consists of:

*   **FastAPI (ASGI Core)**: Built for high-concurrency async operations. FastAPI manages the primary gateway API surface, ensuring minimum network overhead and robust request routing.
*   **DuckDB (Resilient Analytical & Caching Store)**: Integrated as our low-latency, localized storage engine. DuckDB manages semantic caching, request telemetry, and audit logs.
    *   *SRE Safeguard*: All DuckDB operations are completely decoupled from the main ASGI event loop via dedicated telemetry thread pools to prevent blocking/disk I/O contention.
*   **Pydantic (Strict Data Validation)**: Every ingress request and egress response is validated using strict, declarative Pydantic schemas. This prevents downstream type failures and guarantees a highly reliable payload contract.

---

## 2. Primary Objective: Multi-Modal Payload Processing

The absolute priority for this repository is the seamless processing and routing of **Multi-Modal payloads (specifically Base64-encoded Images)**:

1.  **Direct Image Injection**: Support incoming payloads that contain raw Base64 image strings directly inside the API request structure.
2.  **Schema Enforcement**: Utilize specialized Pydantic models to parse, validate, and sanitize incoming multi-modal requests before they enter the model cascade.
3.  **Cascading Waterfall Routing**: Intelligently route multi-modal inputs through high-availability vision models (e.g., GPT-4o, Gemini Pro Vision, Claude 3.5 Sonnet, or local multi-modal NIMs/Ollama), utilizing an automated cascade fallback system.

---

## 3. Operations & Observability

To maintain SRE compliance, any new multi-modal endpoint must adhere to the following telemetry standards:

*   **Strict Event-Loop Protection**: Under no circumstances should synchronous filesystem reads/writes or database ingestion tasks block the main asynchronous threads.
*   **O(1) Content Negotiation**: Dynamic provider health checks and token hydration must be performed through O(1) in-memory or localized caching, avoiding continuous active network/disk polling.
*   **Telemetry Schemas**: Every multi-modal transaction is persisted into DuckDB with exact latency numbers, token counts, and input/output payload hashes.

---

## 4. Challan Anomaly Pipeline

The pipeline utilizes a 4-stage SRE-grade architecture to process invoices and challans:
1. **Ingress Validation**: Validates `InvoiceIngress` via Pydantic to catch malformed payloads.
2. **Vision Extraction**: Processes the Base64 image using Gemini 1.5 Flash natively (with `asyncio.to_thread` for event loop protection).
3. **Deterministic Anomaly Engine**: Pure Python anomaly checks (Line Item Math, Grand Total Balance, Duplicate Document Detection).
4. **Persistence & Quarantine**: Valid data is written to DuckDB via `BackgroundTasks` using `INSERT OR REPLACE`. Malformed requests are safely quarantined to Parquet files without blocking the active stream.

**Endpoint**: `POST /api/v1/pipeline/ingest`
