import time
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

from src.router import classify_and_route
from src.health import provider_statuses, stats, health_ping_loop

logger = logging.getLogger("server")

app = FastAPI(title="Hybrid AI Router API")


# --- STARTUP: Launch background health pings ---
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(health_ping_loop())
    logger.info("Background health monitor started.")


# --- PREMIUM DASHBOARD ---
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    from src.config import GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS

    # Build provider status cards
    provider_cards = ""
    for pid, ps in provider_statuses.items():
        if ps.status == "up":
            badge_bg = "rgba(34, 197, 94, 0.2)"
            badge_color = "#4ade80"
            icon = "&#x2705;"
            status_text = f"{ps.latency_ms}ms"
        elif ps.status == "down":
            badge_bg = "rgba(239, 68, 68, 0.2)"
            badge_color = "#f87171"
            icon = "&#x274C;"
            status_text = ps.error or "Down"
        else:
            badge_bg = "rgba(234, 179, 8, 0.2)"
            badge_color = "#fbbf24"
            icon = "&#x23F3;"
            status_text = "Checking..."

        ago = ""
        if ps.last_checked > 0:
            secs = int(time.time() - ps.last_checked)
            if secs < 60:
                ago = f"{secs}s ago"
            else:
                ago = f"{secs // 60}m ago"

        provider_cards += f"""
            <div class="provider-card">
                <div class="provider-header">
                    <span class="provider-icon">{icon}</span>
                    <span class="provider-name">{ps.name}</span>
                </div>
                <div class="provider-status" style="background:{badge_bg}; color:{badge_color};">{status_text}</div>
                <div class="provider-ago">{ago}</div>
            </div>
        """

    # Stats
    success_rate = 0
    if stats.total_requests > 0:
        success_rate = round((stats.successful / stats.total_requests) * 100, 1)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hybrid AI Router | Dashboard</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0a0e1a;
                --surface: #111827;
                --card: #1e293b;
                --border: rgba(255,255,255,0.08);
                --primary: #38bdf8;
                --accent: #818cf8;
                --success: #4ade80;
                --danger: #f87171;
                --warn: #fbbf24;
                --text: #f1f5f9;
                --text-muted: #94a3b8;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', -apple-system, sans-serif;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 2rem;
            }}
            .dashboard {{
                width: 100%;
                max-width: 720px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 2rem;
            }}
            .status-pill {{
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0.4rem 1rem;
                background: rgba(34, 197, 94, 0.15);
                color: var(--success);
                border-radius: 2rem;
                font-size: 0.8rem;
                font-weight: 600;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                margin-bottom: 1rem;
            }}
            .status-pill .dot {{
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success);
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.4; }}
            }}
            h1 {{
                font-size: 2rem;
                font-weight: 700;
                background: linear-gradient(135deg, var(--primary), var(--accent));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 0.25rem;
            }}
            .subtitle {{
                color: var(--text-muted);
                font-size: 0.9rem;
            }}

            /* Stats Row */
            .stats-row {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1rem;
                margin-bottom: 1.5rem;
            }}
            .stat-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 1rem;
                padding: 1.25rem;
                text-align: center;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .stat-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }}
            .stat-val {{
                font-size: 1.75rem;
                font-weight: 700;
                color: var(--primary);
                line-height: 1;
                margin-bottom: 0.35rem;
            }}
            .stat-label {{
                font-size: 0.75rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}

            /* Section */
            .section-title {{
                font-size: 0.75rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.1em;
                margin-bottom: 0.75rem;
                padding-left: 0.25rem;
            }}

            /* Provider Grid */
            .provider-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 0.75rem;
                margin-bottom: 1.5rem;
            }}
            .provider-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 0.875rem;
                padding: 1rem;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .provider-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            }}
            .provider-header {{
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 0.5rem;
            }}
            .provider-icon {{ font-size: 1rem; }}
            .provider-name {{
                font-weight: 600;
                font-size: 0.9rem;
            }}
            .provider-status {{
                display: inline-block;
                padding: 0.2rem 0.6rem;
                border-radius: 1rem;
                font-size: 0.75rem;
                font-weight: 600;
            }}
            .provider-ago {{
                font-size: 0.7rem;
                color: var(--text-muted);
                margin-top: 0.4rem;
            }}

            /* Key Pool */
            .key-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 0.75rem;
                margin-bottom: 2rem;
            }}
            .key-card {{
                background: var(--card);
                border: 1px solid var(--border);
                border-radius: 0.875rem;
                padding: 1rem;
                text-align: center;
            }}
            .key-val {{
                font-size: 1.5rem;
                font-weight: 700;
                color: var(--accent);
            }}
            .key-label {{
                font-size: 0.7rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-top: 0.2rem;
            }}

            footer {{
                text-align: center;
                color: var(--text-muted);
                font-size: 0.75rem;
                opacity: 0.6;
            }}

            /* Auto-refresh animation */
            .refresh-bar {{
                height: 2px;
                background: linear-gradient(90deg, transparent, var(--primary), transparent);
                border-radius: 1px;
                margin-bottom: 1.5rem;
                animation: sweep 30s linear infinite;
            }}
            @keyframes sweep {{
                0% {{ background-position: -200% center; }}
                100% {{ background-position: 200% center; }}
            }}
        </style>
        <meta http-equiv="refresh" content="30">
    </head>
    <body>
        <div class="dashboard">
            <div class="header">
                <div class="status-pill"><span class="dot"></span> System Active</div>
                <h1>Hybrid AI Router</h1>
                <p class="subtitle">Minimalist Waterfall Engine v2.0</p>
            </div>

            <div class="refresh-bar"></div>

            <div class="section-title">Request Statistics</div>
            <div class="stats-row">
                <div class="stat-card">
                    <div class="stat-val">{stats.total_requests}</div>
                    <div class="stat-label">Total Requests</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">{success_rate}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-val">{stats.last_latency:.1f}s</div>
                    <div class="stat-label">Last Latency</div>
                </div>
            </div>

            <div class="section-title">Provider Health</div>
            <div class="provider-grid">
                {provider_cards}
            </div>

            <div class="section-title">Key Pool</div>
            <div class="key-grid">
                <div class="key-card">
                    <div class="key-val">{len(GROQ_API_KEYS)}</div>
                    <div class="key-label">Groq Keys</div>
                </div>
                <div class="key-card">
                    <div class="key-val">{len(OPENROUTER_API_KEYS)}</div>
                    <div class="key-label">OpenRouter Keys</div>
                </div>
                <div class="key-card">
                    <div class="key-val">{len(NVIDIA_API_KEYS)}</div>
                    <div class="key-label">NVIDIA Keys</div>
                </div>
            </div>

            <footer>End-to-End Resilience &bull; Port 8000 &bull; Auto-refreshes every 30s</footer>
        </div>
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

    # Validate Input Schema
    if not prompt_text and not image_data:
        return JSONResponse(status_code=422, content={"error": "Malformed request: No text or image found in last message."})

    # Send through our router
    start_time = time.time()
    try:
        response_text, model_label = classify_and_route(prompt_text, image_data=image_data)
        elapsed = time.time() - start_time

        # Track stats
        stats.total_requests += 1
        stats.successful += 1
        stats.last_provider = model_label
        stats.last_latency = elapsed
    except Exception as e:
        stats.total_requests += 1
        stats.failed += 1
        logger.error(f"Routing logic failure: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal System Error in routing logic."})
    
    # Tag the response so the user knows the source
    if "ERROR" in model_label:
        tag = "[⚠️ Error]"
    else:
        tag = "[🌊 Cascade]"
        
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

@app.get("/health/providers")
async def health_providers():
    """Detailed provider health status for programmatic consumption."""
    result = {}
    for pid, ps in provider_statuses.items():
        result[pid] = {
            "name": ps.name,
            "status": ps.status,
            "latency_ms": ps.latency_ms,
            "last_checked": ps.last_checked,
            "error": ps.error,
        }
    return result