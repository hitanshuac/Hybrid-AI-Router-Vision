import time
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

from src.router import classify_and_route

from fastapi.responses import JSONResponse, HTMLResponse

logger = logging.getLogger("server")

app = FastAPI(title="Hybrid AI Router API")

# --- PREMIUM DASHBOARD ---
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    from src.config import GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hybrid AI Router | Dashboard</title>
        <style>
            :root {{
                --bg: #0f172a;
                --card: #1e293b;
                --primary: #38bdf8;
                --accent: #818cf8;
                --text: #f8fafc;
            }}
            body {{
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
            }}
            .container {{
                background: var(--card);
                padding: 2rem;
                border-radius: 1.5rem;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                border: 1px solid rgba(255,255,255,0.1);
                width: 90%;
                max-width: 600px;
                text-align: center;
            }}
            .status-badge {{
                display: inline-block;
                padding: 0.5rem 1rem;
                background: rgba(34, 197, 94, 0.2);
                color: #4ade80;
                border-radius: 2rem;
                font-weight: 600;
                margin-bottom: 1rem;
            }}
            h1 {{ font-size: 2rem; margin-bottom: 0.5rem; background: linear-gradient(to right, var(--primary), var(--accent)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; margin-top: 2rem; }}
            .stat-card {{ background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 1rem; }}
            .stat-val {{ font-size: 1.5rem; font-weight: bold; color: var(--primary); }}
            .stat-label {{ font-size: 0.8rem; opacity: 0.7; }}
            footer {{ margin-top: 2rem; opacity: 0.5; font-size: 0.8rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="status-badge">🟢 SYSTEM ACTIVE</div>
            <h1>Hybrid AI Router</h1>
            <p>Minimalist Waterfall Engine v2.0</p>
            <div class="grid">
                <div class="stat-card"><div class="stat-val">{len(GROQ_API_KEYS)}</div><div class="stat-label">Groq Keys</div></div>
                <div class="stat-card"><div class="stat-val">{len(OPENROUTER_API_KEYS)}</div><div class="stat-label">OR Keys</div></div>
                <div class="stat-card"><div class="stat-val">{len(NVIDIA_API_KEYS)}</div><div class="stat-label">NIM Keys</div></div>
            </div>
        </div>
        <footer>End-to-End Resilience | Port 8000</footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    if not request.messages:
        return JSONResponse(status_code=400, content={"error": "No messages provided"})
        
    last_msg = request.messages[-1]
    prompt_text = ""
    image_data = None

    # Handle standard text or multimodal payload
    if isinstance(last_msg.content, str):
        prompt_text = last_msg.content
    elif isinstance(last_msg.content, list):
        for part in last_msg.content:
            if part.get("type") == "text":
                prompt_text += part.get("text", "")
            elif part.get("type") == "image_url":
                # Expecting base64 image data in OpenAI format
                image_url = part.get("image_url", {}).get("url", "")
                if "base64," in image_url:
                    image_data = image_url.split("base64,")[1]
                else:
                    image_data = image_url # Assume raw base64 or URL

    # 10 LPA Optimization: Validate Input Schema
    if not prompt_text and not image_data:
        return JSONResponse(status_code=422, content={"error": "Malformed request: No text or image found in last message."})

    # Send through our semantic router
    start_time = time.time()
    try:
        response_text, model_label = classify_and_route(prompt_text, image_data=image_data)
        elapsed = time.time() - start_time
    except Exception as e:
        logger.error(f"Routing logic failure: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal System Error in routing logic."})
    
    # Prepend a visual tag so the user knows which model was chosen
    tag = "[🏠 Local]"
    if "Pro" in model_label: tag = "[🧠 Pro]"
    elif "Flash" in model_label: tag = "[⚡ Flash]"
    elif "ERROR" in model_label: tag = "[⚠️ Error]"
        
    formatted_response = f"{tag} {response_text}"
    
    # Format as an OpenAI-compatible JSON response
    response_json = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "hybrid-router",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": formatted_response,
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }
    
    logger.info(f"API Request completed in {elapsed:.1f}s -> {tag}")
    return response_json

@app.get("/v1/models")
async def get_models():
    return {
        "object": "list",
        "data": [{"id": "hybrid-router", "object": "model", "created": int(time.time()), "owned_by": "antigravity"}]
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}