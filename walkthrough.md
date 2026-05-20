# Walkthrough: Dynamic Vision Cascade Architecture

We have fundamentally upgraded the main Hybrid AI Router gateway (`/v1/chat/completions`) to be fully multi-modal aware. It will no longer discard images sent from frontends like **Open WebUI**. 

Instead, it intelligently switches its underlying model tier the split second it detects an image payload!

---

## The Vision Cascade Fallback Network

When the gateway identifies `image_data` inside the OpenAI-style payload, it bypasses the standard text-only models and dynamically mounts the **Vision Tier**:

1. **Groq Engine:** Switches from `llama-3.3-70b-versatile` to `llama-3.2-11b-vision-preview`
2. **OpenRouter Engine:** Switches from `gemma-4-31b-it` to `google/gemini-2.5-flash`
3. **NVIDIA NIM:** Switches from `llama-3.1-8b-instruct` to `meta/llama-3.2-90b-vision-instruct`
4. **Gemini Engine:** Retains `gemini-2.5-flash` since it is natively multi-modal
5. **Local Engine:** Switches from `gemma2:9b` to `llava:13b`

---

## SRE Compute Separation (v2.7.0)

### Architecture Changes
The system now enforces strict compute separation between the FastAPI event loop and all blocking I/O:

- **`src/sre_persistence.py`**: All DuckDB writes and Parquet DLQ dumps are offloaded to `asyncio.to_thread` worker pools. A process-wide `asyncio.Lock` (`_DUCKDB_WRITE_LOCK`) serializes all writes to prevent concurrent writer crashes.
- **`src/circuit_breaker.py`**: A stateful, thread-safe circuit breaker monitors upstream Vision LLM responses. After 3 consecutive 429/503 failures, it trips OPEN, halts requests for 60s, and triggers a DuckDB WAL checkpoint.

### CQRS Read Layer
All anomaly detection has been migrated from Python to SQL Silver Layer views:

| View | Purpose |
|---|---|
| `vw_silver_invoice_audit` | Header-level audit with computed subtotals, tax validation, and anomaly flags |
| `vw_silver_invoice_line_items` | Unnested line items with per-row arithmetic delta checks |
| `vw_silver_invoice_duplicates` | Duplicate invoice detection by invoice number |

### Read Endpoints
Three new CQRS read endpoints serve the Silver Layer data:

- `GET /api/v1/pipeline/invoices` — Invoice audit summary
- `GET /api/v1/pipeline/invoices/lines` — Line items detail
- `GET /api/v1/pipeline/anomalies/duplicates` — Duplicate anomalies

All endpoints support multi-format output (`?format=json|html|csv|markdown`) and compound search via `?search_query=` (searches across vendor name + invoice number using DuckDB `ILIKE`).

### SRE Guardrails Enforced
- All reads use `duckdb.connect(read_only=True)` to eliminate lock contention.
- All reads use `asyncio.to_thread` to prevent event loop blocking.
- All queries enforce result set limits (`LIMIT 50` / `LIMIT 200`).

> [!SUCCESS]
> The server boot test passed flawlessly, and all changes have been committed.

To see it in action, restart your **Uvicorn** server and navigate to `http://localhost:8001/api/v1/pipeline/invoices` for the tabular dashboard with CSV export and compound search.
