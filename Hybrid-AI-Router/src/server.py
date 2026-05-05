"""
Hybrid AI Router — API Server
=============================
Wraps the Semantic Router in an OpenAI-compatible REST API.
This allows tools like Open WebUI to talk to our router seamlessly.
"""

import time
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from src.router import classify_and_route
from src.config import run_startup_checks

logger = logging.getLogger("server")

app = FastAPI(title="Hybrid AI Router API")

# Run startup checks when server boots
run_startup_checks()

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = None

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Extract the last user message
    if not request.messages:
        return JSONResponse(status_code=400, content={"error": "No messages provided"})
        
    prompt = request.messages[-1].content
    
    # Send through our semantic router
    start_time = time.time()
    response_text, model_label = classify_and_route(prompt)
    elapsed = time.time() - start_time
    
    # Prepend a visual tag so the user knows which model was chosen
    if "Pro" in model_label:
        tag = "[🧠 Pro]"
    elif "Flash" in model_label:
        tag = "[⚡ Flash]"
    elif "Local" in model_label:
        tag = "[🏠 Local]"
    else:
        tag = "[⚠️ Error]"
        
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
    """Mock the models endpoint so Open WebUI knows we exist."""
    return {
        "object": "list",
        "data": [
            {
                "id": "hybrid-router",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "antigravity"
            }
        ]
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}
