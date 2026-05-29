Historical Fork Migration & Retrospective Log (v3.0.0 Alignment)
This document provides a detailed breakdown of the evolutionary steps, architectural pivots, and historical lessons learned in upgrading the Vision AI Router (forked from v2.4) and the OpenClaude Router (forked from <v1.0) to the production-ready v3.0.0 SRE baseline.

👁️ Vision AI Router (v2.4.0 → v3.0.0)
The Vision fork was split off at v2.4.0. Upgrading this fork to v3.0.0 requires resolving critical bottlenecks associated with local execution assumptions and event-loop blockages.

⚠️ Past Mistakes & Bottlenecks (Resolved)
Asynchronous Event Loop Blocking (WinError 10054 / Latency Spikes):
Mistake: Standard telemetry and DuckDB file I/O operations were executed using async def endpoints. In ASGI servers (like FastAPI), running blocking synchronous code inside async def blocks freezes the entire single-threaded event loop, leading to connection resets and multi-second response delays.
Resolution: Converted /dashboard and metrics read endpoints (e.g., /api/v1/metrics/efficiency) from async def to standard synchronous def handlers. FastAPI automatically offloads synchronous handlers to an external Starlette threadpool, freeing the event loop.
Aggressive local Ollama DNS Loops:
Mistake: Open WebUI was configured to poll host.docker.internal:11434 for local Ollama instances when deployed in headless container environments (like Hugging Face Spaces). This resulted in continuous DNS resolution timeouts and severe memory leaks.
Resolution: Injected ENABLE_OLLAMA_API="False" into the frontend docker configurations and moved all fallback routing logic away from local daemon reliance.
Missing Handshake Endpoints:
Mistake: Strict downstream clients (like Open WebUI) verify model presence upon connection. The absence of /v1/models in v2.4 resulted in a 404 response, causing connection handshakes to fail immediately.
Resolution: Mocked the standard /v1/models endpoint returning a cached registry dictionary.

# Fork Handover: Upgrading to v3.0.0 Baseline

This document provides the exact replication steps required to upgrade your two v2.4 forks (**Image AI Router** and **Terminal Based AI Router**) to the current **v3.0.0 SRE Baseline**.

To achieve parity with the `main` stable branch, you must implement the following architectural changes in both forks:

## 1. Implement SRE Circuit Breaker (`src/circuit_breaker.py`)
- **Action**: Create the `circuit_breaker.py` module.
- **Details**: Implement the "Centipede Guardrail". This includes:
  - Token estimation pre-flight heuristic (`len(prompt) // 4`).
  - A 3-strike fault-tolerance memory dictionary that tracks consecutive `HTTP 429`/`500` errors per tier.
  - A 300-second (5-minute) cooldown mechanism for tripped circuits.
  - **Purpose**: Prevents network retry storms and massive token payload rejections.

## 2. Upgrade the Cascade Engine (`src/router.py`)
- **Action**: Migrate to the 9-Tier Cloud Cascade.
- **Details**: 
  - Remove all local Ollama routing logic and dependencies.
  - Integrate the `circuit_breaker.py` functions: Call `is_circuit_open()` before attempting a tier, and use `record_success()` / `record_failure()` based on the HTTP response.
  - Ensure the fallback waterfall relies entirely on `httpx.AsyncClient` targeting Groq, AI Studio (Gemini), OpenRouter, and NVIDIA NIM.

## 3. Harden the API Server (`src/server.py`)
- **Action**: Implement Global SRE Guardrails.
- **Details**:
  - **Global Exception Handler**: Add `@app.exception_handler(Exception)` to catch all unhandled backend crashes. Return a structured `JSONResponse` with a 500 status code instead of letting FastAPI leak raw stack traces to your clients.
  - **Upstream Validation Mocking**: Add a `GET /v1/models` endpoint that returns a static JSON array containing the `hybrid-router` model.
  - **Purpose**: Prevents strict downstream clients (like Open WebUI or Terminal CLIs) from crashing when they attempt to fetch available models and unexpectedly receive a `404 Not Found` HTML page.

## 4. Frontend & Container Environment Fixes
- **Action**: Neutralize Aggressive DNS Polling.
- **Details**: 
  - If your forks use Open WebUI or similar Dockerized frontends, explicitly inject the environment variable `ENABLE_OLLAMA_API="False"`.
  - **Purpose**: Prevents the frontend from infinitely retrying `host.docker.internal:11434`, which causes catastrophic DNS resolution logs and memory leaks in ephemeral cloud environments like Hugging Face Spaces.
  - Ensure API keys are injected via secure Space Secrets or `.env` files, never hardcoded in the `Dockerfile`.

## 5. Deprecate Outdated Modules
- **Action**: Clean up legacy code.
- **Details**: Delete `src/bot.py` and any legacy Telegram polling logic if the router is strictly acting as an API gateway.

## Summary Checklist for Forks
- [ ] Copy `src/circuit_breaker.py` from `main` to the fork.
- [ ] Sync `src/router.py` to use the 9-tier cascade and circuit breaker logic.
- [ ] Sync `src/server.py` to include the `/v1/models` endpoint and global `500` exception handler.
- [ ] Update frontend `Dockerfile` / `docker-compose.yml` to disable Ollama API connections.
- [ ] Run `eval_baseline.py` (using monkeypatching) to verify cascade integrity.
