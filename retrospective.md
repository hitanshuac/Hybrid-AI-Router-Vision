# 🔍 Project Forensic Audit: Failure & Resolution History

This document logs every critical failure, its resolution, and its eventual outcome. It is the "Hard Memory" of the project.

## 🔴 Failure Logs (Last 100 Cycles)

| ID | Timestamp | Problem | Fix Implemented | Status | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2026-05-11 | **AWS Billing Block** | Purged AWS, pivoted to Groq/OpenRouter | ✅ **Stayed** | Stable |
| 2 | 2026-05-11 | **Groq Deprecation** | Upgraded `llama3-70b-8192` -> `gpt-oss-120b` | ✅ **Stayed** | Stable |
| 3 | 2026-05-11 | **Gemini 429 Flood** | Implemented `RateLimitManager` v1 | ✅ **Stayed** | Lite version active |
| 4 | 2026-05-11 | **Git Rebase Data Loss** | Established "Working Baseline" protocol | ✅ **Stayed** | Enforced |
| 5 | 2026-05-10 | **NVIDIA NIM 404** | Corrected model ID from `minimax/` to `minimaxai/` | ✅ **Stayed** | Working |
| 6 | 2026-05-10 | **URL Parsing Error** | Removed double-quotes from `.env` URL | ✅ **Stayed** | Working |
| 7 | 2026-05-09 | **RAG Token Crush** | Optimized chunking to 1000 tokens | ❌ **Failed Now** | RAG Purged |
| 8 | 2026-05-08 | **Git Merge Conflict** | Manual cleanup of `<<<<<<< HEAD` markers | ❌ **Failed Later** | Overwritten by rebase |
| 9 | 2026-05-07 | **Apps Script Payload Limit** | Pivoted to Python-based `fms_normalizer.py` | ✅ **Stayed** | Externalized |
| 10 | 2026-05-11 | **Semantic Complexity** | Stripped logic to Waterfall Cascade | ✅ **Stayed** | New Baseline |
| 11 | 2026-05-11 | **Config NameError** | Deep Cleaned AWS references from `config.py` | ✅ **Stayed** | Stable Boot |
| 12 | 2026-05-04 | **Local Gemma Latency** | Implemented Semantic Cache (ChromaDB) | ❌ **Failed Now** | Purged for Simplicity |
| 13 | 2026-05-03 | **VRAM Overflow (8GB)** | Set `num_ctx: 4096` in Ollama | ✅ **Stayed** | Active |
| 14 | 2026-05-05 | **Context Fragmentation** | Created `ContextManager` for history | ✅ **Stayed** | Active |
| 15 | 2026-05-06 | **API Key Exposure** | Moved all keys to `secrets/*.txt` | ✅ **Stayed** | Security Standard |
| 16 | 2026-05-11 | **NVIDIA Paid Model** | Switched to `meta/llama-3.1-8b-instruct` | ✅ **Stayed** | Free Tier |
| 17 | 2026-05-11 | **Workspace Bloat** | Total System Purge (30+ files removed) | ✅ **Stayed** | Minimalist Baseline |
| 18 | 2026-05-17 | **Context Drift (Ungrounded Models)** | Implemented Ephemeral Context Grounding v2.3.0 — system prompt injected at index 0 of every outbound payload | ✅ **Stayed** | Active |
| 19 | 2026-05-17 | **Token Wastage (Uncompacted Payloads)** | Implemented Context Compaction v2.4.0 — boilerplate stripping, 10-msg sliding window, DuckDB telemetry tracking | ✅ **Stayed** | Active |
| 20 | 2026-05-17 | **Event Loop Blocking** | Converted `/dashboard` and `/api/v1/metrics/efficiency` endpoints from `async def` to standard `def` to offload synchronous file I/O to Starlette's background threadpool | ✅ **Stayed** | Zero-latency LLM routing restored, 9/9 baseline tests passed |
| 21 | 2026-05-17 | **Gemini SDK 404 Path Failure** | Stripped `models/` prefix namespace inside the constructor, passing flat model tracking strings. | ✅ **Stayed** | Stable Execution |
| 22 | 2026-05-17 | **Base64 Token Inflation Bypass** | Decoupled Base64 character loops from calculation engine and applied a fixed `+1024` token weight proxy. | ✅ **Stayed** | Circuit breaker protected |
| 23 | 2026-05-17 | **Silent Chat Array Flattening** | Intercepted client multi-modal arrays inside `server.py` to forward native structures to OpenAI/Groq standards. | ✅ **Stayed** | Multi-Modal Capable |

## 🧠 Key Learnings
1.  **Complexity is a Debt**: Every "Smart" feature (RAG, Semantic Router) adds a failure point. In high-pressure engineering, **Cascading Fallbacks** beat **Complex Classification**.
2.  **Environment is Fragile**: Git commands can wipe logic faster than you can write it. The `start_all.bat` and `retrospective.md` are the ONLY permanent anchors.
3.  **Vendor Lock-in is Real**: AWS and Gemini can block you instantly. A multi-provider, multi-key rotational pool is the only way to guarantee 99.9% uptime on free tiers.
4.  **System-Prompt Governance is an SRE Primitive**: Without an enforced grounding message, downstream models produce inconsistent personas across cascade tiers. Ephemeral injection at the router layer is the cheapest, most reliable fix — zero extra latency, zero persistence overhead.
5.  **Measure Before You Optimize**: Compaction without telemetry is guessing. DuckDB-backed metrics on every request give you the hard data to prove token savings and justify architectural decisions.
6.  **Guard the Event Loop**: Never run blocking synchronous database or file system calls (like DuckDB file connections) inside an `async def` handler. In high-throughput ASGI environments like FastAPI, synchronous reads will freeze the event loop, causing severe latency spikes and connection resets (WinError 10054). Offload them to background threadpools using standard `def` endpoints.


---

## 📜 Archived: The "Battle for Stability" (30+ Errors)

We have navigated through a dense minefield of infrastructure and API failures. Below is the list of the last 30 major errors and the "surgeries" performed to fix them.

### 🌩️ Cloud & Provider Failures (The "429/404" Cycle)
1. **Google 429 (Rate Limit)**: Gemini Flash hitting free-tier limits.
   - **FIX**: Implemented a **10-minute Circuit Breaker** and automatic failover.
2. **NVIDIA 404 (Model Not Found)**: Incorrect model identifiers for the new Llama 3.1 series.
   - **FIX**: Ran diagnostic scripts to verify the specific Meta IDs and updated `config.py`.
3. **NVIDIA API Timeout (30s)**: Free-tier endpoints becoming saturated and timing out.
   - **FIX**: Promoted **AWS Bedrock** to the Primary reasoning tier to bypass slow endpoints.
4. **Bedrock "Malformed Request"**: Older `invoke_model` payloads failing on Claude 3.
   - **FIX**: Migrated the entire cloud client to the official **Amazon Bedrock Converse API**.
5. **Gemini Truncation**: Responses cutting off mid-sentence.
   - **FIX**: Added explicit `generationConfig` with `maxOutputTokens: 4096`.
6. **Anthropic 401 (Invalid Key)**: Key missing or improperly loaded from secrets.
   - **FIX**: Standardized the `secrets/` loading logic in `config.py`.

### 🏠 Local & Infrastructure Failures (The "500/Memory" Cycle)
7. **Ollama 500 (Internal Server Error)**: Local embeddings failing due to memory pressure.
   - **FIX**: Fully decommissioned local embeddings; migrated to **Google Cloud Embeddings**.
8. **Local Latency (25s Response)**: Gemma 2 taking too long to generate text.
   - **FIX**: **Decommissioned all Local LLMs**; moved to a Pure Cloud architecture for speed.
9. **Ollama 404 (Model Not Found)**: Moondream or Gemma not being pulled in the background.
   - **FIX**: Added startup checks that verify model presence before booting the server.
10. **Local Truncation (128 Tokens)**: Ollama defaulting to short answers.
    - **FIX**: Manually set `num_predict: 4096` in the request payload.

### 🧠 Logic & Architecture Failures (The "Blind Router" Cycle)
11. **Semantic Cache Poisoning**: Old, short answers being served from memory.
    - **FIX**: Successive migrations from `v1` ➔ `v2` ➔ `v3` ➔ **`v4`** of the ChromaDB database.
12. **Blind Routing**: Router defaulting to "General" when embeddings failed.
    - **FIX**: Switched to **Google Embeddings** to ensure the router's "brain" is always online.
13. **Stateless Follow-ups**: "I don't know" answers because the model forgot history.
    - **FIX**: Increased history window to **5 messages** and added `Domain Persistence` logic.
14. **SyntaxError (f-string backslash)**: Code crashing on restart due to Python 3.10 limitations.
    - **FIX**: Refactored debug logging to move logic outside of f-string curly braces.
15. **Git Merge Conflicts**: Conflict markers (`<<<<<<<`) left in `router.py`.
    - **FIX**: Manually cleaned the source code to restore a clean production state.

### 📊 Current Status
The "errors" you see in the logs now are **External Outages** (Google 429s or NVIDIA Timeouts). Your code is now doing exactly what it was designed to do: **Survive them.**

When you see a log like `WARNING | router | Gemini failed... trying NVIDIA...`, that is **SUCCESS**. It means your code just prevented a total system crash.
