# Goal

Build a comprehensive Evaluation (Eval) System to rigorously verify the Hybrid AI Router's core components (Ingestion, Circuit Breaker, Layout Cache, SRE Persistence, and CQRS Read Layer) are functioning without errors.

## Proposed Changes

### 1. `tests/eval_system.py`
Create a robust, self-contained Python evaluation script using FastAPI's `TestClient` to run end-to-end integration tests on the system architecture.

**Evaluations to run:**
1. **Layout Cache Eval:** Inject a Base64 document. Verify a Cache MISS on the first pass (writes to DuckDB), and a Cache HIT on the second pass (bypasses LLM).
2. **Circuit Breaker Eval:** Simulate API failures to verify the state transitions from `CLOSED` → `OPEN` → `HALF_OPEN`. Ensure `Retry-After` headers and jitter backoffs are respected.
3. **SRE Persistence Eval:** Verify the Async Single-Writer Actor pattern correctly drains the `asyncio.Queue` and persists data to the DuckDB Bronze Layer without locking.
4. **CQRS Read Layer Eval:** Hit the `/api/v1/pipeline/invoices` and `/api/v1/pipeline/invoices/lines` endpoints to ensure read-only connections are successfully querying the Silver Layer views.

### 2. `.agents/workflows/run-eval.md`
Create a dedicated workflow file that agents can trigger to automatically run the evaluation suite and report the system health before major checkpoints or deployments.

### 3. `start_all.bat` Update
Integrate the evaluation check into `start_all.bat`.
- Add an optional flag (e.g., `start_all.bat --eval`) to run the eval suite before booting the router and WebUI.
- If the eval fails, the script halts, preventing a broken system from launching.

## User Review Required

> [!IMPORTANT]
> The eval system will inject test data into the local `pipeline_metrics.db`. Do you want the eval script to use an isolated test database (e.g., `test_metrics.db`) to avoid polluting your main database, or is it okay to test directly on the primary DB? (I recommend an isolated test DB, which I will configure the eval script to use).
