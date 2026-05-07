"""
Hybrid AI Router — Local LLM Client (Ollama)
=============================================
Handles all communication with the local Ollama server.
Includes:
  - Retry logic for connection drops and cold-start timeouts
  - Slow response detection with GPU memory warnings
  - Environment-aware host configuration for Docker

TROUBLESHOOTING:
  - "Connection Refused": Ollama app is not running.
    FIX (Windows): Open Start menu > search "Ollama" > click to launch.
    FIX (Terminal): Open a NEW terminal and run 'ollama serve'.
  - "Read Timeout": The model is taking too long. Common causes:
    1. Cold start — Ollama is loading the model into GPU VRAM (~30s first time).
    2. Long prompt — Gemma needs more time for complex queries.
    3. GPU busy — Another app is using your RTX 4060 VRAM.
    FIX: Check GPU usage with 'nvidia-smi' in terminal.
    FIX: Close other GPU-heavy apps (games, other AI tools).
  - "Model not found": Run 'ollama pull gemma2:9b' to download it.
"""

import logging
import time
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)
from src.config import LOCAL_MODEL_PRIMARY, OLLAMA_HOST, LOCAL_TIMEOUT, MAX_LOCAL_RETRIES

logger = logging.getLogger("local")


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================
class LocalUnavailableException(Exception):
    """Raised when the local Ollama server cannot be reached after retries."""
    pass


class LocalTransientError(Exception):
    """Raised for errors that should be retried (timeouts, temp connection drops)."""
    pass


# ============================================================
# CORE LOCAL QUERY — With retry logic
# ============================================================
@retry(
    retry=retry_if_exception_type(LocalTransientError),
    stop=stop_after_attempt(MAX_LOCAL_RETRIES),
    wait=wait_fixed(3),  # Wait 3 seconds between retries (for VRAM loading)
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _query_local_with_retry(prompt, model):
    """
    Internal function that makes the actual Ollama API call.
    Tenacity will retry on LocalTransientError (timeouts, connection drops).
    """
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096
        }
    }

    try:
        start_time = time.time()
        response = requests.post(url, json=payload, timeout=LOCAL_TIMEOUT)
        elapsed = time.time() - start_time

        # --- Slow response warning ---
        if elapsed > 30:
            logger.warning(f"Local model took {elapsed:.1f}s to respond (>30s threshold).")
            logger.warning("This may indicate GPU memory pressure.")
            logger.warning("FIX: Run 'nvidia-smi' to check VRAM usage.")
            logger.warning("FIX: Run 'ollama ps' to see loaded models.")
        else:
            logger.info(f"Local model responded in {elapsed:.1f}s")

        response.raise_for_status()
        data = response.json()

        # --- Safe response extraction ---
        result = data.get('response', '')
        if not result:
            error = data.get('error', 'Empty response from Ollama')
            logger.warning(f"Ollama returned empty response: {error}")
            return f"(Local model returned empty response: {error})"

        return result

    except requests.exceptions.ConnectionError:
        raise LocalTransientError(
            f"Cannot connect to Ollama at {OLLAMA_HOST}. "
            "FIX: Make sure Ollama is running. "
            "Windows: Open Start menu > search 'Ollama' > click to launch. "
            "Terminal: Run 'ollama serve' in a new window."
        )
    except requests.exceptions.ReadTimeout:
        raise LocalTransientError(
            f"Ollama timed out after {LOCAL_TIMEOUT[1]}s. "
            "This usually means the model is loading into GPU VRAM (cold start). "
            "Retrying..."
        )
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else 'unknown'
        body = e.response.text[:200] if e.response else 'no body'

        if status == 404 or 'not found' in body.lower():
            raise LocalUnavailableException(
                f"Model '{model}' not found on Ollama server. "
                f"FIX: Run 'ollama pull {model}' in your terminal."
            )
        else:
            raise LocalTransientError(f"Ollama HTTP error ({status}): {body}")
    except (LocalTransientError, LocalUnavailableException):
        raise  # Let these propagate
    except Exception as e:
        raise LocalUnavailableException(f"Unexpected local error: {type(e).__name__}: {e}")


# ============================================================
# PUBLIC API — Called by router.py
# ============================================================
def query_local(prompt, model=None):
    """
    Query the local Ollama server with retry and error handling.
    
    Returns: response text (str)
    Raises: LocalUnavailableException if Ollama can't be reached
    """
    if model is None:
        model = LOCAL_MODEL_PRIMARY

    try:
        return _query_local_with_retry(prompt, model)
    except RetryError as e:
        logger.error(f"Local model failed after {MAX_LOCAL_RETRIES} retries.")
        raise LocalUnavailableException(
            f"Local Ollama failed after {MAX_LOCAL_RETRIES} retries. "
            f"Last error: {e.last_attempt.exception()}"
        )
    except LocalUnavailableException:
        raise


def get_embedding(text, model="nomic-embed-text"):
    """
    Get the vector embedding for a piece of text using Ollama.
    """
    url = f"{OLLAMA_HOST}/api/embeddings"
    payload = {
        "model": model,
        "prompt": text,
    }
    try:
        response = requests.post(url, json=payload, timeout=LOCAL_TIMEOUT)
        response.raise_for_status()
        return response.json().get('embedding', [])
    except Exception as e:
        logger.error(f"Failed to get embedding from Ollama: {e}")
        return []

