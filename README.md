# 🚀 Hybrid AI Router: Minimalist Cascade (v2.0)

A high-performance, zero-complexity API Gateway that maximizes cloud resilience using a multi-provider waterfall and rotational key pool.

---

## 🛠️ Minimalist Architecture
This system is designed for **Bulletproof Reliability**. It eliminates complex semantic routing in favor of a robust failover cascade:

**Waterfall Path:**
1.  **Groq (Primary)**: Ultra-fast inference (`llama-3.3-70b`).
2.  **OpenRouter (Fallback)**: Diverse provider safety net (`gemma-4-free`).
3.  **NVIDIA NIM (Safety Net)**: High-reliability fallback (`llama-3.1-8b`).
4.  **Ollama (Offline)**: Local private execution (`gemma2:9b`).

---

## 🚀 First-Run Setup (The "Login")

To get the system running, follow these steps:

### 1. Configure Secrets
The system uses a **Rotational Key Pool**. Add your API keys to the `secrets/` directory:
- `secrets/groq_api_key_1.txt` (and `_2.txt`, `_3.txt` for rotation)
- `secrets/openrouter_api_key_1.txt`
- `secrets/nvidia_api_key_1.txt`

### 2. Launch System
Double-click:
- **`start_all.bat`**: Boots the Production Server and Dashboard.

### 3. Verify Dashboard
Visit **[http://localhost:8000/dashboard](http://localhost:8000/dashboard)** in your browser to see your active key pools and system status.

---

## 🔌 Integration (Connect Your IDE/WebUI)

The Router exposes an **OpenAI-compatible API**. You can use it as a custom provider in:

- **Open WebUI**: Set Base URL to `http://localhost:8000/v1`
- **Cursor / VSCode**: Use as an OpenAI API provider with the above URL.
- **Python/JS**: Point your OpenAI client to `http://localhost:8000/v1`

---

## 🧠 Governance & Failover
- **Key Rotation**: Automatically cycles through all keys in `secrets/` to maximize bandwidth and bypass rate limits.
- **Waterfall Resilience**: If Groq fails (429/500), the system instantly pivots to OpenRouter, then NVIDIA, then Local.
- **Zero Cost**: Pre-configured to use **Strictly FREE** models by default.

---

**Built for Engineering Resilience. No Complexity. No Hallucinations. Just Uptime.**
