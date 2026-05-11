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

## 🧠 Key Learnings
1.  **Complexity is a Debt**: Every "Smart" feature (RAG, Semantic Router) adds a failure point. In high-pressure engineering, **Cascading Fallbacks** beat **Complex Classification**.
2.  **Environment is Fragile**: Git commands can wipe logic faster than you can write it. The `start_all.bat` and `retrospective.md` are the ONLY permanent anchors.
3.  **Vendor Lock-in is Real**: AWS and Gemini can block you instantly. A multi-provider, multi-key rotational pool is the only way to guarantee 99.9% uptime on free tiers.
