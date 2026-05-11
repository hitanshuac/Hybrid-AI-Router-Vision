# 🤝 ANTIGRAVITY HANDOVER: Hybrid AI Router (v2.0.0-Minimalist)

**Date**: 2026-05-11
**Status**: 🟢 STABLE BASELINE LOCKED
**Branch**: `main`

## 📋 Context for the Next Session
This project was recently **Extreme-Simplified** to move out of a "Complexity Trap." We purged all Semantic RAG, Vector Stores, and Classifiers. The system is now a high-performance **Waterfall API Proxy**.

### 🏗️ Current Architecture
- **Waterfall Cascade**: Groq -> OpenRouter -> NVIDIA NIM -> Local Ollama.
- **Key Rotation**: Multiple keys stored in `secrets/*.txt` are cycled automatically.
- **Orchestration**: `start_all.bat` launches the Router (8000) and Open WebUI (8080).
- **Dashboard**: High-fidelity dashboard at `http://localhost:8000/dashboard`.

### 📂 Critical Source Files (Read these first)
1.  **[src/config.py](file:///d:/Projects/Hybrid-AI-Router/src/config.py)**: Rotational secret loader and stubs.
2.  **[src/llm_cloud.py](file:///d:/Projects/Hybrid-AI-Router/src/llm_cloud.py)**: The Waterfall Cascade logic.
3.  **[src/router.py](file:///d:/Projects/Hybrid-AI-Router/src/router.py)**: Minimalist entry point for routing.
4.  **[src/server.py](file:///d:/Projects/Hybrid-AI-Router/src/server.py)**: FastAPI server with Dashboard and OpenAI-compatible endpoint.

### 🛡️ Grounding Truths
- **Port 8000**: Router Engine / OpenAI Provider.
- **Port 8080**: Open WebUI.
- **Strictly Free**: All pre-configured models are 100% free-tier.
- **Latency**: Sub-200ms routing overhead.

### 🚀 Next Steps / Pending Ideas
1.  **Cost Monitoring**: Add actual token usage tracking to the Dashboard.
2.  **Health Pings**: Add a background thread to ping providers every 5 mins and mark them "Down" in the Dashboard if they fail.
3.  **Telegram Bot**: Re-integrate the `src/bot.py` into the new waterfall engine.

**Grounded Baseline**: The system is currently working perfectly. Do not re-introduce complexity without a rigorous audit of the `retrospective.md` failure history.
