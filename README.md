# 🚀 Hybrid-AI-Router-Vision: The Autonomous Multi-Modal AI Gateway

![Hybrid AI Router Vision Banner](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)
![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Uptime](https://img.shields.io/badge/Uptime-99.9%25%20(Target)-success)

---

## 🌟 Overview

The **Hybrid-AI-Router-Vision** is a next-generation, low-overhead, and high-availability multi-modal AI gateway designed for critical enterprise workflows. It intelligently routes complex vision and text payloads across a dynamic network of LLM providers, ensuring maximum uptime, cost efficiency, and performance. Beyond simple routing, it features an integrated **Invoice Ingest Engine** for automated document inspection, mathematical auditing, and validation.

Built with SRE principles at its core, this system is a testament to resilience, operational rigor, and adaptive architecture. It is engineered to not just process requests, but to **survive** API outages, rate limits, and service degradations with graceful, cascading fallbacks.

---

## ✨ Key Features & Capabilities

*   **Autonomous Multi-Modal Routing:** Dynamically detects image payloads and intelligently routes to vision-capable models across multiple providers (Groq, OpenRouter, NVIDIA NIM, Gemini, Ollama).
*   **High-Availability Cascade Fallback:** Implements a robust, real-time fallback mechanism across provider tiers to guarantee service continuity even during external API outages or rate limits.
*   **Invoice Audit & Validation Pipeline:** A dedicated 4-stage engine for structured OCR, deterministic arithmetic validation, grand total balancing, and duplicate invoice detection.
*   **Advanced SRE Telemetry & Optimization:** Leverages DuckDB for real-time request analytics, context compaction metrics, and efficiency tracking, all within a minimal memory footprint (256MB capped).
*   **Ephemeral Context Grounding:** Enforces consistent model persona and behavior by injecting system prompts at the router layer, ensuring zero latency overhead.
*   **Adaptive Token Management:** Features an intelligent token estimator with a dynamic `+1024` token proxy for Base64 image data, protecting against silent token inflation and ensuring circuit breaker accuracy.
*   **Event Loop Guarding:** Protects FastAPI's `async` event loop by offloading synchronous file I/O and database operations to Starlette's background threadpool, eliminating latency spikes.
*   **Zero-Downtime Provider Pivoting:** Seamlessly switches between free and paid tiers, and between different model versions, to maintain cost efficiency and performance.
*   **Security-First Design:** Strict isolation of API keys within `secrets/*.txt` with standardized loading logic.

---

## 🏛️ Core Architecture

At its heart, the system operates as a dual-engine architecture, each optimized for its specific domain while sharing a common, resilient infrastructure.

![System Architecture](docs/assets/system_architecture.png)

### 1. 🌐 Gateway Engine (`POST /v1/chat/completions`)

This endpoint serves as the primary multi-modal AI chat interface, intelligently routing incoming requests to the most suitable LLM provider and model.
*   **Dynamic Vision Cascade Fallback Network:**
    The moment `image_data` is detected within an OpenAI-style payload, the gateway dynamically switches from text-only models to a dedicated Vision Tier. This cascade ensures high availability and cost optimization by attempting providers in a predefined order:
    1.  **Groq Engine:** `llama-3.2-11b-vision-preview` (high-speed, cost-effective vision)
    2.  **OpenRouter Engine:** `google/gemini-2.5-flash` (diverse model access, robust fallback)
    3.  **NVIDIA NIM:** `meta/llama-3.2-90b-vision-instruct` (powerful, enterprise-grade vision)
    4.  **Gemini Engine:** `gemini-2.5-flash` (native multi-modal support, reliable)
    5.  **Ollama Local:** `llava:13b` (local fallback for extreme resilience or specific use cases)

### 2. 📝 Invoice Ingest Engine (`POST /api/v1/pipeline/ingest`)

This specialized engine provides a high-throughput pipeline for the automated inspection and validation of invoices or similar structured documents, critical for modern finance and supply chain operations.
*   **4-Stage Document Validation Pipeline:**
    1.  **Stage 1: Structured OCR ([src/vision_client.py](src/vision_client.py)):** The initial step leverages `gemini-2.5-flash` for advanced multi-modal OCR, extracting key-value pairs and tabular data from submitted invoice scans with high accuracy.
    2.  **Stage 2: Deterministic Arithmetic Check ([src/anomaly.py](src/anomaly.py)):** Extracted data is fed into a pure Python logic layer that performs rigorous, deterministic arithmetic checks on line items, unit prices, taxes, and grand totals, catching calculation skew or formatting anomalies.
    3.  **Stage 3: Dupe & History Audit ([src/server.py](src/server.py)):** Cross-references the extracted document ID against a historical ledger in DuckDB to prevent double-processing or ledger collisions.
    4.  **Stage 4: Starlette Background Thread Offloading:** Any blocking database writes or logging are immediately offloaded to a Starlette background worker pool. This isolates synchronous file and DuckDB I/O from the main async loop, keeping API round-trip latency at sub-second speeds.

---

## 📑 Deep-Dive Documentation & Logs

To keep the repository clean and avoid massive walls of text, we maintain comprehensive modular documentation. Click the links below for a deep dive into each system:

*   🔍 **[Project Forensic Audit & Retrospective](retrospective.md):** The permanent failure log and key learnings for the last 100+ cycles, documenting every major cloud outage, event loop blockade, and system fix.
*   🗺️ **[Multi-Modal Vision Cascade Blueprint](implementation_plan.md):** The core SRE architecture blueprints and implementation schemas for routing payloads across multi-provider endpoints.
*   🌊 **[Dynamic Vision Cascade Walkthrough](walkthrough.md):** An under-the-hood look at ingress preservation, recursive token estimation, and ternary-based provider hydration.
*   🤝 **[Telemetry & Telemetry Handoff Standards](HANDOVER.md):** Standard guidelines for metrics compaction, DuckDB schemas, and multi-agent governance parameters.

---

## 🛠️ Getting Started

Follow these steps to get your Hybrid-AI-Router-Vision up and running.

### Prerequisites

*   Python 3.10+
*   `pip` (Python package installer)
*   `ollama` (required if you plan to utilize local models like `llava:13b`)

### 1. Clone the Repository

```bash
git clone https://github.com/hitanshuac/Hybrid-AI-Router-Vision.git
cd Hybrid-AI-Router-Vision
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Secrets

Create a `secrets/` directory in the root of your project and place your API keys there as individual `.txt` files. Each file should contain only the key.
Example directory structure:

```
Hybrid-AI-Router-Vision/
├── src/
├── secrets/
│   ├── groq_api_key.txt
│   ├── openrouter_api_key.txt
│   ├── nvidia_api_key.txt
│   ├── gemini_api_key.txt
│   └── ollama_host.txt (e.g., http://localhost:11434)
└── requirements.txt
```

### 4. Run the FastAPI Server with Uvicorn

```bash
uvicorn src.server:app --host 0.0.0.0 --port 8001 --reload
```
The server will now be accessible at `http://localhost:8001`. The interactive Swagger UI for API documentation can be found at `http://localhost:8001/docs`.

### 5. Verification and Diagnostics

*   **Test Multi-Modal Routing:**
    Send an image alongside text via standard chat completition endpoint. Monitor your console logs to verify that the request successfully routes to a vision model (e.g., `llama-3.2-11b-vision-preview`) and returns OCR/transcribed text instead of ignoring the image.
*   **Invoice Ingest Test:**
    Send a `POST` request to `/api/v1/pipeline/ingest` with a structured invoice image inside `InvoiceIngress` payload body. Observe the logs to trace the execution of the 4-stage validation pipeline and the resulting audited data.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🗺️ System Flowchart (Mermaid Source)

The following raw Mermaid diagram governs the visual representation of our gateway and invoice pipeline. It is automatically parsed and compiled by our automation workflows whenever a new version is pushed to GitHub.

```mermaid
graph TD
    A[Client Request] --> B{API Gateway src/server.py};
    
    %% Gateway Flow
    B -- "/v1/chat/completions" --> C{Router Logic src/router.py};
    C -- Text Payload --> D[Text Cascade src/llm_cloud.py];
    C -- Image Payload --> E[Vision Cascade src/llm_cloud.py];
    
    D --> F[Groq / OpenRouter / NVIDIA NIM / Gemini / Ollama];
    E --> G[Groq-Vision / OpenRouter-Vision / NVIDIA-Vision / Gemini-Vision / Ollama-Vision];
    
    %% Invoice Flow
    B -- "/api/v1/pipeline/ingest" --> H[Invoice Ingest Engine];
    H --> I[Stage 1: Structured OCR src/vision_client.py];
    I -- Gemini 2.5 Flash --> J[Stage 2: Deterministic Arithmetic Check src/anomaly.py];
    J -- Pure Python Logic --> K[Stage 3: Dupe & History Audit src/server.py];
    K -- DuckDB Ledger Query --> L[Stage 4: Async Handoff & Telemetry];
    L -- Starlette Threadpool --> M[(DuckDB Telemetry & Ledger)];
    
    %% Subgraphs for Services
    subgraph Core Services
        C -- Context Grounding v2.3.0 --> R[System Prompt Injection];
        C -- Context Compaction v2.4.0 --> S[Sliding Window Compaction];
        C -- Token Estimation --> U[Dynamic +1024 Token Proxy];
    end
    
    subgraph SRE Guardrails
        X[Secrets Manager secrets/*.txt]
        Y[RateLimitManager Circuit Breaker]
        Z[Event Loop Guarding Background tasks]
        W[Port Isolation :8001]
        V[Telemetry Auto-Title Bypass]
    end
    
    subgraph Egress Engine
        T[GFM Table Formatter v2.5.1]
    end

    R --> D; R --> E;
    S --> D; S --> E;
    U --> D; U --> E;
    X --> F; X --> G; X --> I;
    Y --> F; Y --> G;
    Z --> L; Z --> M;
    T --> B;
```