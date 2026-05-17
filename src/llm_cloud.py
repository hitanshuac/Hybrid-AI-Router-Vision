import logging
import os
import time
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)
from src.config import (
    GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS, GEMINI_API_KEYS,
    PRIMARY_CLOUD_MODEL, SECONDARY_CLOUD_MODEL, SAFETY_NET_MODEL, GEMINI_MODEL,
    LOCAL_MODEL_PRIMARY, OLLAMA_HOST
)

logger = logging.getLogger("cloud")

class CloudExhaustedException(Exception): pass
class CloudPermanentError(Exception): pass
class CloudTransientError(Exception): pass

def estimate_tokens(prompt: str) -> int:
    return len(prompt) // 4

def estimate_tokens_from_messages(messages: list) -> int:
    """Estimate total token count across all messages in a conversation."""
    total_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str))
    return total_chars // 4

MODEL_CONSTRAINTS = {
    "groq": 8000,
    "openrouter": 8000,
    "nvidia": 4000,
    "gemini": 1000000,
    "ollama": 8000
}

# ============================================================
# SIMPLE CASCADE ENGINE
# ============================================================
def query_cloud(prompt=None, messages=None):
    """
    Tries providers in sequence: Groq -> OpenRouter -> NVIDIA -> Gemini -> Ollama.
    Stops at the first successful response.
    Accepts either a prompt string (backward compat) or a full messages list.
    """
    # Resolve the messages payload
    if messages is not None:
        msg_payload = messages
        est_tokens = estimate_tokens_from_messages(messages)
    elif prompt is not None:
        msg_payload = [{"role": "user", "content": prompt}]
        est_tokens = estimate_tokens(prompt)
    else:
        raise ValueError("query_cloud requires either 'prompt' or 'messages'.")
    
    # 1. GROQ (Primary)
    if GROQ_API_KEYS:
        if est_tokens > MODEL_CONSTRAINTS["groq"]:
            logger.warning(f"[PRE-FLIGHT BYPASS] Payload estimated at {est_tokens} tokens exceeds groq limit of {MODEL_CONSTRAINTS['groq']}. Bypassing.")
        else:
            for key in GROQ_API_KEYS:
                try:
                    resp = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": "llama-3.3-70b-versatile", "messages": msg_payload},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        return resp.json()['choices'][0]['message']['content']
                except: continue

    # 2. OPENROUTER (Secondary)
    if OPENROUTER_API_KEYS:
        if est_tokens > MODEL_CONSTRAINTS["openrouter"]:
            logger.warning(f"[PRE-FLIGHT BYPASS] Payload estimated at {est_tokens} tokens exceeds openrouter limit of {MODEL_CONSTRAINTS['openrouter']}. Bypassing.")
        else:
            for key in OPENROUTER_API_KEYS:
                try:
                    resp = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": "google/gemma-4-31b-it:free", "messages": msg_payload},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        return resp.json()['choices'][0]['message']['content']
                except: continue

    # 3. NVIDIA (Safety Net)
    if NVIDIA_API_KEYS:
        if est_tokens > MODEL_CONSTRAINTS["nvidia"]:
            logger.warning(f"[PRE-FLIGHT BYPASS] Payload estimated at {est_tokens} tokens exceeds nvidia limit of {MODEL_CONSTRAINTS['nvidia']}. Bypassing.")
        else:
            for key in NVIDIA_API_KEYS:
                try:
                    resp = requests.post(
                        "https://integrate.api.nvidia.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": "meta/llama-3.1-8b-instruct", "messages": msg_payload},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        return resp.json()['choices'][0]['message']['content']
                except: continue

    # 4. GEMINI FLASH (High-Context Tier)
    if GEMINI_API_KEYS:
        if est_tokens > MODEL_CONSTRAINTS["gemini"]:
            logger.warning(f"[PRE-FLIGHT BYPASS] Payload estimated at {est_tokens} tokens exceeds gemini limit of {MODEL_CONSTRAINTS['gemini']}. Bypassing.")
        else:
            for key in GEMINI_API_KEYS:
                try:
                    resp = requests.post(
                        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": GEMINI_MODEL, "messages": msg_payload},
                        timeout=15
                    )
                    if resp.status_code == 200:
                        return resp.json()['choices'][0]['message']['content']
                except: continue

    # 5. OLLAMA (Offline Safety Net — Local GPU)
    if est_tokens > MODEL_CONSTRAINTS["ollama"]:
        logger.warning(f"[PRE-FLIGHT BYPASS] Payload estimated at {est_tokens} tokens exceeds ollama limit of {MODEL_CONSTRAINTS['ollama']}. Bypassing.")
    else:
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": LOCAL_MODEL_PRIMARY, "messages": msg_payload, "stream": False},
                timeout=60
            )
            if resp.status_code == 200:
                return resp.json()['message']['content']
        except:
            pass

    raise CloudExhaustedException("All providers failed (cloud + local).")
