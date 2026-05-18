# Walkthrough: Dynamic Vision Cascade Architecture

We have fundamentally upgraded the main Hybrid AI Router gateway (`/v1/chat/completions`) to be fully multi-modal aware. It will no longer discard images sent from frontends like **Open WebUI**. 

Instead, it intelligently switches its underlying model tier the split second it detects an image payload!

---

## The Vision Cascade Fallback Network

When the gateway identifies `image_data` inside the OpenAI-style payload, it bypasses the standard text-only models and dynamically mounts the **Vision Tier**:

1. **Groq Engine:** Switches from `llama-3.3-70b-versatile` to `llama-3.2-11b-vision-preview`
2. **OpenRouter Engine:** Switches from `gemma-4-31b-it` to `google/gemini-1.5-flash`
3. **NVIDIA NIM:** Switches from `llama-3.1-8b-instruct` to `meta/llama-3.2-90b-vision-instruct`
4. **Gemini Engine:** Retains `gemini-1.5-flash` since it is natively multi-modal
5. **Local Engine:** Switches from `gemma2:9b` to `llava:13b`

## How We Accomplished This

### 1. Stopping Data Loss at Ingress
Previously in **`src/server.py`**, any complex multimodal array was flattened into a single text string before it hit the router:
```python
# Old Behavior
text_parts = "".join(p.get("text", "") for p in msg.content if p.get("type") == "text")
messages_plain.append({"role": msg.role, "content": text_parts})
```
**New Behavior:** We now specifically trap requests with `image_data` and preserve the entire dictionary structure `[{"type": "image_url", ...}]`.

### 2. Upgrading the Token Estimator
In **`src/llm_cloud.py`**, the `estimate_tokens_from_messages` function was rewritten to recursively calculate text token lengths inside arrays, whilst dynamically appending a flat `+4000` base token penalty whenever an `image_url` block is detected.

### 3. Dynamic Model Hydration
Inside `query_cloud()`, we utilize python ternary operators to hot-swap the API targets without adding complex duplicate functions or classes:
```python
active_groq = VISION_GROQ_MODEL if image_data else "llama-3.3-70b-versatile"
active_openrouter = VISION_OPENROUTER_MODEL if image_data else "google/gemma-4-31b-it:free"
# ... cascades natively down
```

### 4. SRE Guardrails and Egress Formatting
In **`src/server.py`**, we added robust protections and quality-of-life formatting:
- **Telemetry De-Poisoning**: A heuristic (`_should_log_telemetry`) now isolates phantom frontend auto-title generation requests, stopping them from artificially deflating our DuckDB latency metrics.
- **Nested Table Extraction**: Replaced raw comma-separated JSON dumps in the vision output with a `dict_to_markdown_table` utility that gracefully unrolls nested list-of-dicts into discrete, spreadsheet-ready Markdown tables.
- **Port Isolation**: Shifted the entire Vision ecosystem to Port `8001` to guarantee it can run synchronously alongside legacy text routers without port clashes.

> [!SUCCESS]
> The server boot test passed flawlessly, and all changes have been committed.

To see it in action, just restart your **Uvicorn** server and drop an image straight into your Open WebUI dashboard. The router will instantly pick it up and query the Vision Cascade!
