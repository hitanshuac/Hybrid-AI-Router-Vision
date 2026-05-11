import logging
import time
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)
from src.config import (
    GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS,
    PRIMARY_CLOUD_MODEL, SECONDARY_CLOUD_MODEL, SAFETY_NET_MODEL
)

logger = logging.getLogger("cloud")

class CloudExhaustedException(Exception): pass
class CloudPermanentError(Exception): pass
class CloudTransientError(Exception): pass

# ============================================================
# SIMPLE CASCADE ENGINE
# ============================================================
def query_cloud(prompt):
    """
    Tries providers in sequence: Groq -> OpenRouter -> NVIDIA.
    Stops at the first successful response.
    """
    
    # 1. GROQ (Primary)
    if GROQ_API_KEYS:
        for key in GROQ_API_KEYS:
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}]},
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json()['choices'][0]['message']['content']
            except: continue

    # 2. OPENROUTER (Secondary)
    if OPENROUTER_API_KEYS:
        for key in OPENROUTER_API_KEYS:
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": "google/gemma-4-31b-it:free", "messages": [{"role": "user", "content": prompt}]},
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json()['choices'][0]['message']['content']
            except: continue

    # 3. NVIDIA (Safety Net)
    if NVIDIA_API_KEYS:
        for key in NVIDIA_API_KEYS:
            try:
                resp = requests.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": "meta/llama-3.1-8b-instruct", "messages": [{"role": "user", "content": prompt}]},
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json()['choices'][0]['message']['content']
            except: continue

    raise CloudExhaustedException("All cloud providers failed.")
