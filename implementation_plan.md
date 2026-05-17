# Multi-Modal Vision Routing Cascade

The main `/v1/chat/completions` endpoint currently flattens multimodal arrays into plain text and routes them to text-only models. We will fix this by preserving the image payload and intelligently routing it to vision-capable models across our providers.

## Proposed Changes

### 1. Ingress Preservation (`src/server.py`)
- **[MODIFY]** `src/server.py`: Update the message serialization loop. If `image_data` is detected, we will keep the original multimodal dictionary structure (`{"type": "image_url", ...}`) intact instead of flattening it to text. We will pass `image_data` explicitly to `classify_and_route`.

### 2. Router Propagation (`src/router.py`)
- **[MODIFY]** `src/router.py`: Update `classify_and_route` to accept the `image_data` parameter and pass it downstream to `query_cloud`.

### 3. Vision Fallback Cascade (`src/llm_cloud.py`)
- **[MODIFY]** `src/llm_cloud.py`: Update `query_cloud` to accept `image_data`.
- If `image_data` is present, the cascade will **dynamically switch** from text models to vision models using the exact same standard OpenAI multimodal payload structure.
- **The Vision Cascade Tier:**
  1. **Groq**: Switch to `llama-3.2-11b-vision-preview`
  2. **OpenRouter**: Switch to `google/gemini-1.5-flash`
  3. **NVIDIA**: Switch to `meta/llama-3.2-90b-vision-instruct`
  4. **Gemini API**: Native REST endpoint using `gemini-1.5-flash`
  5. **Ollama**: Switch to `llava:13b` or `minicpm-v`

## Verification Plan
1. Restart the FastAPI server.
2. Upload a test image through the Open WebUI (`http://localhost:8080`).
3. Verify that the Uvicorn logs show the request successfully routing to a vision model (e.g. `llama-3.2-11b-vision-preview`) and returning OCR/transcribed text instead of ignoring the image.
