# 🏁 STABLE BASELINE: Minimalist Waterfall v2.0.0

**Snapshot Date**: 2026-05-11
**Engine Status**: 🟢 PRODUCTION-READY
**Latency**: <200ms (Routing) / Variable (Cloud)

## 🏗️ Architecture Snapshot
This baseline represents the **Complexity Pivot**. We have moved from a semantic classification engine to a high-reliability waterfall cascade.

### Core Components
1.  **[src/config.py](file:///d:/Projects/Hybrid-AI-Router/src/config.py)**: Rotational secret loader for Groq, OpenRouter, and NVIDIA NIM.
2.  **[src/llm_cloud.py](file:///d:/Projects/Hybrid-AI-Router/src/llm_cloud.py)**: Deterministic Waterfall Cascade (Groq -> OR -> NIM).
3.  **[src/router.py](file:///d:/Projects/Hybrid-AI-Router/src/router.py)**: Simplified gateway router.
4.  **[src/server.py](file:///d:/Projects/Hybrid-AI-Router/src/server.py)**: OpenAI-compatible FastAPI server with built-in Dashboard.
5.  **[start_all.bat](file:///d:/Projects/Hybrid-AI-Router/start_all.bat)**: Single-click orchestration for Router + Open WebUI.

### 🛡️ Governance Rules
- **Strictly Free Models**: Only free-tier endpoints are pre-configured to prevent billing surprises.
- **Key Rotation**: Every provider supports multiple keys to bypass individual rate limits.
- **Failover**: Instant pivot to the next provider on 429, 500, or Timeout errors.

### 🔌 Verified Integration
- **Open WebUI**: Successfully connected at `http://localhost:8000/v1`
- **Dashboard**: Accessible at `http://localhost:8000/dashboard`

**DO NOT MODIFY THE CORE ROUTING LOGIC WITHOUT CREATING A NEW BASELINE SNAPSHOT.**
