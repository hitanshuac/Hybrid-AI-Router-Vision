# 🚀 Hybrid-AI-Router-Vision: The Autonomous Multi-Modal AI Gateway

![Hybrid AI Router Vision Banner](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)
![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Uptime](https://img.shields.io/badge/Uptime-99.9%25%20(Target)-success)

---

## 🌟 Overview

The **Hybrid-AI-Router-Vision** is a next-generation, low-overhead, and high-availability multi-modal AI gateway designed for critical enterprise workflows. It intelligently routes complex vision and text payloads across a dynamic network of LLM providers, ensuring maximum uptime, cost efficiency, and performance. Beyond simple routing, it features an integrated Challan (Delivery Note) Ingest Engine for automated document inspection and validation, critical for supply chain and logistics operations.

Built with SRE principles at its core, this system is a testament to resilience, operational rigor, and adaptive architecture, forged through rigorous production challenges and continuous optimization. It's engineered to not just process requests, but to **survive** API outages, rate limits, and service degradations with graceful, cascading fallbacks.

---

## ✨ Key Features & Capabilities

*   **Autonomous Multi-Modal Routing:** Dynamically detects image payloads and intelligently routes to vision-capable models across multiple providers (Groq, OpenRouter, NVIDIA NIM, Gemini, Ollama).
*   **High-Availability Cascade Fallback:** Implements a robust, real-time fallback mechanism across provider tiers to guarantee service continuity even during external API outages or rate limits.
*   **Delivery Challan Inspection Pipeline:** A dedicated 4-stage engine for structured OCR, deterministic arithmetic validation, grand total balancing, and duplicate invoice detection.
*   **Advanced SRE Telemetry & Optimization:** Leverages DuckDB for real-time request analytics, context compaction metrics, and efficiency tracking, all within a minimal memory footprint (256MB capped).
*   **Ephemeral Context Grounding:** Enforces consistent model persona and behavior by injecting system prompts at the router layer, ensuring zero latency overhead.
*   **Adaptive Token Management:** Features an intelligent token estimator with a dynamic `+1024` token proxy for Base64 image data, protecting against silent token inflation and ensuring circuit breaker accuracy.
*   **Event Loop Guarding:** Protects FastAPI's `async` event loop by offloading synchronous file I/O to Starlette's background threadpool, eliminating latency spikes.
*   **Zero-Downtime Provider Pivoting:** Seamlessly switches between free and paid tiers, and between different model versions, to maintain cost efficiency and performance.
*   **Security-First Design:** Strict isolation of API keys within `secrets/*.txt` with standardized loading logic.

---

## 🏛️ Core Architecture: The Hybrid AI Router Vision System

At its heart, the system operates as a dual-engine architecture, each optimized for its specific domain while sharing a common, resilient infrastructure.

```mermaid
graph TD
    A[Client Request] --> B{API Gateway /v1/chat/completions};
    B -- Multi-Modal Payload (Text/Image) --> C{Router Logic src/router.py};
    C -- Text Only --> D[Text Cascade: Groq, OpenRouter, NVIDIA, Gemini, Ollama];
    C -- Image Data Detected --> E[Vision Cascade: Groq-Vision, OpenRouter-Vision, NVIDIA-Vision, Gemini-Vision, Ollama-Vision];
    D --> F[LLM Provider A (e.g., Groq)];
    E --> G[LLM Provider B (e.g., Gemini Vision)];
    F -- Fallback --> H[LLM Provider C (e.g., OpenRouter)];
    G -- Fallback --> I[LLM Provider D (e.g., NVIDIA NIM)];
    H -- Fallback --> J[LLM Provider E (e.g., Ollama Local)];
    I -- Fallback --> J;
    J --> K[Response];

    B -- Challan Ingest Payload --> L{API Gateway /api/v1/pipeline/ingest};
    L --> M[Challan Ingest Engine src/fms_normalizer.py];
    M -- Stage 1: Structured OCR --> N[Gemini 1.5 Flash Vision];
    N -- Stage 2: Data Extraction & Validation --> O[Deterministic Python Logic];
    O -- Stage 3: Arithmetic & Dupe Check --> P[DuckDB (Background Thread)];
    P -- Stage 4: Output --> Q[Validated Challan Data];
    Q --> K;

    subgraph Core Services
        C -- Context Grounding v2.3.0 --> R[System Prompt Injection];
        C -- Context Compaction v2.4.0 --> S[Sliding Window & Boilerplate Stripping];
        S -- Telemetry Tracking --> T[DuckDB (WAL Mode, 256MB Cap)];
        C -- Token Estimation --> U[Dynamic +1024 Vision Token Proxy];
        T --- U;
    end

    subgraph Operational Excellence
        X[Secrets Management (secrets/*.txt)]
        Y[RateLimitManager (Circuit Breaker)]
        Z[Event Loop Guarding (Sync I/O Offload)]
    end

    R --> D; R --> E;
    S --> D; S --> E;
    U --> D; U --> E;
    X --> F; X --> G; X --> H; X --> I; X --> J; X --> N;
    Y --> F; Y --> G; Y --> H; Y --> I;
    Z --> P;

```

### 1. 🌐 Gateway Engine (`POST /v1/chat/completions`)

This endpoint serves as the primary multi-modal AI chat interface, intelligently routing incoming requests to the most suitable LLM provider and model.

*   **Dynamic Vision Cascade Fallback Network:**
    The moment `image_data` is detected within an OpenAI-style payload, the gateway dynamically switches from text-only models to a dedicated Vision Tier. This cascade ensures high availability and cost optimization by attempting providers in a predefined order:
    1.  **Groq Engine:** `llama-3.2-11b-vision-preview` (high-speed, cost-effective vision)
    2.  **OpenRouter Engine:** `google/gemini-1.5-flash` (diverse model access, robust fallback)
    3.  **NVIDIA NIM:** `meta/llama-3.2-90b-vision-instruct` (powerful, enterprise-grade vision)
    4.  **Gemini Engine:** `gemini-1.5-flash` (native multi-modal support, reliable)
    5.  **Ollama Local:** `llava:13b` (local fallback for extreme resilience or specific use cases)

    > [!TIP] How we accomplished dynamic multi-modal routing:
    > In `src/server.py`, complex multi-modal arrays are no longer flattened; the entire `[{"type": "image_url", ...}]` structure is preserved. In `src/llm_cloud.py`, Python ternary operators (`active_groq = VISION_GROQ_MODEL if image_data else ...`) hot-swap API targets without introducing complex duplicate logic, ensuring agility and maintainability.

*   **Pre-Flight Admission Controls:**
    *   **Base64 Token Inflation Bypass:** Recognizing that Base64 encoding inflates token counts for images, we've decoupled character loops from the calculation engine. A fixed `+1024` token weight proxy is dynamically applied when an `image_url` block is detected, preventing silent token overruns and safeguarding the circuit breaker.
    *   **RateLimitManager:** A robust `10-minute Circuit Breaker` is active per provider, automatically failing over to the next available tier upon detection of `429` (Rate Limit) or `404` errors. This crucial mechanism prevents vendor lock-in and ensures continuous operation, even under sustained external pressure.

*   **Context Grounding & Compaction:**
    *   **Ephemeral Context Grounding v2.3.0:** To combat "Context Drift" and ensure consistent model behavior, a robust system prompt is injected at index 0 of every outbound payload. This router-layer enforcement adds zero latency and incurs no persistence overhead, guaranteeing reliable persona adherence.
    *   **Context Compaction v2.4.0:** Actively reduces token wastage through intelligent boilerplate stripping and a 10-message sliding window. This mechanism is meticulously backed by DuckDB telemetry for verifiable token savings and data-driven architectural validation.

### 2. 📝 Challan Ingest Engine (`POST /api/v1/pipeline/ingest`)

This specialized engine provides a high-throughput pipeline for the automated inspection and validation of delivery challans or similar structured documents, critical for supply chain logistics.

*   **4-Stage Document Validation Pipeline:**
    1.  **Stage 1: Structured OCR (Gemini 1.5 Flash Vision):** The initial step leverages Gemini 1.5 Flash for advanced multi-modal OCR, extracting key-value pairs and tabular data from submitted challan images with high accuracy.
    2.  **Stage 2: Deterministic Python Arithmetic Loop:** Extracted data is fed into a pure Python logic layer that performs rigorous, deterministic arithmetic checks on line items, subtotals, taxes, and grand totals. This ensures mathematical integrity.
    3.  **Stage 3: Grand Total Balance & Duplicate Detection:** Further validation ensures the entire document balances correctly and checks against a historical database (DuckDB) for potential duplicate challan IDs, preventing data integrity issues and redundant processing.
    4.  **Stage 4: Starlette Background Thread Offloading:** Crucially, any blocking synchronous database or file I/O operations (like writing to DuckDB) are explicitly offloaded from the `async def` FastAPI handler to Starlette's background threadpool. This design choice safeguards the main event loop, preventing blocking and maintaining zero-latency LLM routing capabilities.

    > [!IMPORTANT] Guarding the Event Loop:
    > Running blocking synchronous database or file system calls within an `async def` handler in high-throughput ASGI environments like FastAPI will freeze the event loop, leading to severe latency spikes and connection resets (`WinError 10054`). Our architecture explicitly mitigates this by using standard `def` endpoints for I/O-heavy operations and leveraging Starlette's threadpool, restoring crucial baseline performance.

---

## 🛡️ SRE & Operational Excellence

Our commitment to Site Reliability Engineering is deeply embedded in every layer of this system, reflecting a hard-won understanding of production realities.

*   **Unwavering Resilience & Uptime:**
    The system is engineered to **"Survive"** external outages, not merely avoid them. When you observe a log entry like `WARNING | router | Gemini failed... trying NVIDIA...`, that is a **SUCCESS** notification. It signifies the autonomous fallback mechanism actively preventing a total system crash, thereby guaranteeing our 99.9% uptime target, even when operating on dynamic, often volatile, free-tier services. This resilience is fundamentally achieved through a multi-provider, multi-key rotational pool and intelligent circuit breakers.

*   **Resource Optimization & Telemetry:**
    *   **DuckDB Integration:** Central to our SRE telemetry strategy, DuckDB meticulously tracks every request's token usage, latency, and chosen routing path in real-time. It's configured in WAL (Write-Ahead Logging) mode for optimal durability and performance, all while adhering to a strict memory cap of **256MB** to maintain an exceptionally low operational footprint.
    *   **Real-time Compaction Statistics:** Provides immediate, actionable insights into the token savings achieved by the `Context Compaction` module. This empirical data is vital for validating architectural decisions and proving tangible efficiency gains.

*   **Security Posture:**
    All sensitive API keys are rigorously secured. They are never hardcoded or exposed in configuration files, instead residing in isolated `secrets/*.txt` files. A standardized loading logic implemented in `config.py` ensures secure and consistent key retrieval across the application.

*   **Performance Engineering:**
    Through aggressive refactoring and learnings derived from previous event loop blocking issues, we ensure that all critical paths are inherently non-blocking. The strategic conversion of high-I/O endpoints like `/dashboard` and `/api/v1/metrics/efficiency` from `async def` to standard `def` to explicitly offload synchronous file I/O has critically restored zero-latency LLM routing and enabled a flawless pass on all 9 baseline performance tests.

---

## 🧠 Project Resilience: Forensic Audit & Key Learnings

This project's exceptional robustness is a direct consequence of confronting and overcoming numerous complex production challenges. Our "Hard Memory" of critical failures and their meticulously documented resolutions is a cornerstone of our operational rigor.

### 🔴 Failure Logs (Last 100 Cycles)

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

### 💡 Key Learnings from the Trenches

Our journey through a dense minefield of infrastructure and API failures has yielded invaluable operational wisdom, directly shaping the resilient design of this router:

1.  **Complexity is a Debt:** Every "Smart" feature (e.g., RAG, Semantic Router) inherently adds a failure point. In high-pressure engineering, **Cascading Fallbacks** consistently outperform **Complex Classification**, proving that simplicity directly correlates with reliability.
2.  **Environment is Fragile:** Git operations can wipe critical logic faster than development. Establishing robust "Working Baseline" protocols and maintaining immutable anchors (like `start_all.bat` and `retrospective.md`) is paramount for preserving system integrity.
3.  **Vendor Lock-in is Real:** Cloud providers (e.g., AWS, Google) can enforce instant blocks or rate limits. A multi-provider, multi-key rotational pool is the only reliable way to guarantee resilience and cost-efficiency, especially when leveraging dynamic free-tier services.
4.  **System-Prompt Governance is an SRE Primitive:** Without an enforced grounding message, downstream models inevitably produce inconsistent personas. Ephemeral injection at the router layer is the most reliable, zero-latency fix for maintaining consistent model behavior.
5.  **Measure Before You Optimize:** Compaction and optimization efforts without concrete telemetry are speculative. DuckDB-backed metrics on every request provide the irrefutable data needed to validate architectural decisions and objectively prove efficiency gains.
6.  **Guard the Event Loop:** Never run blocking synchronous database or file system calls within an `async def` handler in high-throughput ASGI environments. Offloading these operations to background threadpools using standard `def` endpoints is critical for maintaining responsiveness and preventing severe latency spikes and `WinError 10054` (connection resets).

---

## 🛠️ Getting Started

Follow these steps to get your Hybrid-AI-Router-Vision up and running.

### Prerequisites

*   Python 3.10+
*   `pip` (Python package installer)
*   `ollama` (required if you plan to utilize local models like `llava:13b`)

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/hybrid-ai-router-vision.git
cd hybrid-ai-router-vision
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `secrets/` directory in the root of your project and place your API keys there as individual `.txt` files. Each file should contain only the key.
Example directory structure:

```
hybrid-ai-router-vision/
├── src/
├── secrets/
│   ├── groq_api_key.txt
│   ├── openrouter_api_key.txt
│   ├── nvidia_api_key.txt
│   ├── gemini_api_key.txt
│   └── ollama_host.txt (e.g., http://localhost:11434)
└── requirements.txt
└── ...
```

These keys will be automatically loaded by `config.py`. Ensure your `ollama_host.txt` points to your running local Ollama instance if you intend to use it.

### 4. Pull Local Ollama Models (Optional)

If you plan to utilize the local Ollama fallback in your cascade, pull the required vision models:

```bash
ollama pull llava:13b
ollama pull minicpm-v # An alternative vision model if llava is not preferred
```

### 5. Run the FastAPI Server with Uvicorn

```bash
uvicorn src.server:app --host 0.0.0.0 --port 8080 --reload
```
The server will now be accessible at `http://localhost:8080`. The interactive Swagger UI for API documentation can be found at `http://localhost:8080/docs`.

### 6. Verification and Diagnostics

*   **Test Multi-Modal Routing:**
    Restart your Uvicorn server, then use a compatible frontend like Open WebUI (typically configured to `http://localhost:8080`) to send an image alongside text. Monitor your Uvicorn console logs to verify that the request successfully routes to a vision model (e.g., `llama-3.2-11b-vision-preview`) and processes the image content.

*   **Challan Ingest Test:**
    Send a `POST` request to `/api/v1/pipeline/ingest` with a structured document image (e.g., a sample delivery challan) in the payload body. Observe the logs to trace the execution of the 4-stage validation pipeline and the resulting processed data.

---

## 🤝 Contributing

We welcome contributions from the community! Please refer to our `CONTRIBUTING.md` (to be created) for detailed guidelines on how to submit issues, propose features, and make pull requests. Your insights and efforts help fortify this system.

---

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

---