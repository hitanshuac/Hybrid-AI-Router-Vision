"""
Hybrid AI Router — Cloud LLM Client (Gemini API)
=================================================
Handles all communication with the Google Gemini API.
Includes:
  - Connection pooling via requests.Session
  - Exponential backoff with jitter via tenacity
  - Specific exception handling for every known API error
  - CloudExhaustedException for circuit breaker fallback

TROUBLESHOOTING:
  - "429 Too Many Requests": You hit the free-tier rate limit.
    The code will automatically retry up to 4 times with increasing waits.
    If it still fails, it falls back to your local Gemma model.
    FIX (permanent): Wait for your quota to refresh, or enable billing.
  - "404 Not Found": The model name is wrong/deprecated.
    FIX: This should be auto-fixed by config.py model discovery.
    If not, check https://ai.google.dev/gemini-api/docs/models
  - "401/403 Unauthorized": Your API key is invalid.
    FIX: Get a new key at https://aistudio.google.com/apikey
  - "ConnectionError": No internet connection.
    FIX: Check your Wi-Fi. Cloud routing will fallback to Local.
"""

import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)
from src.config import GEMINI_API_KEY, CLOUD_MODEL_LIGHT, CLOUD_TIMEOUT, MAX_CLOUD_RETRIES
from src.quota import quota_tracker

logger = logging.getLogger("cloud")


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================
class CloudExhaustedException(Exception):
    """Raised when all retry attempts to the cloud API have failed."""
    pass


class CloudPermanentError(Exception):
    """Raised for errors that should NOT be retried (401, 403, 404)."""
    pass


class CloudTransientError(Exception):
    """Raised for errors that SHOULD be retried (429, 500, 502, 503, 504)."""
    pass


# ============================================================
# SESSION WITH CONNECTION POOLING
# ============================================================
_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=5,
    pool_maxsize=5,
)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


# ============================================================
# CORE CLOUD QUERY — With retry logic
# ============================================================
@retry(
    retry=retry_if_exception_type(CloudTransientError),
    stop=stop_after_attempt(MAX_CLOUD_RETRIES),
    wait=wait_exponential_jitter(initial=2, max=16, jitter=2),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _query_cloud_with_retry(prompt, model, image_data=None):
    """
    Internal function that makes the actual API call.
    Tenacity will automatically retry this on CloudTransientError.
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        start_time = time.time()
        response = _session.post(
            url,
            json=payload,
            timeout=CLOUD_TIMEOUT,
        )
        elapsed = time.time() - start_time
        logger.info(f"Cloud API responded in {elapsed:.1f}s (status: {response.status_code})")

        if response.status_code == 200:
            quota_tracker.increment()

        # --- Handle specific HTTP status codes ---
        
        # Permanent errors — do NOT retry
        if response.status_code == 401 or response.status_code == 403:
            raise CloudPermanentError(
                f"API key is invalid or expired ({response.status_code}). "
                f"FIX: Get a new key at https://aistudio.google.com/apikey"
            )

        if response.status_code == 404:
            raise CloudPermanentError(
                f"Model '{model}' not found (404). Google may have deprecated it. "
                f"FIX: Restart the router to trigger auto-discovery of new model names."
            )

        # Transient errors — DO retry
        if response.status_code == 429:
            raise CloudTransientError(
                f"Rate limited (429). Free tier limit reached. Retrying with backoff..."
            )

        if response.status_code in (500, 502, 503, 504):
            raise CloudTransientError(
                f"Google server error ({response.status_code}). Retrying..."
            )

        # Other 4xx errors — permanent
        if response.status_code >= 400:
            raise CloudPermanentError(
                f"Unexpected client error ({response.status_code}): {response.text[:200]}"
            )

        # --- Parse the successful response safely ---
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            error_info = data.get("error", {}).get("message", "No candidates in response")
            raise CloudPermanentError(f"Empty response from API: {error_info}")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise CloudPermanentError("Response has no content parts.")

        return parts[0].get("text", "")

    except requests.exceptions.ConnectionError:
        raise CloudTransientError(
            "Cannot reach Google servers (ConnectionError). "
            "FIX: Check your internet connection."
        )
    except requests.exceptions.Timeout:
        raise CloudTransientError(
            f"Google API timed out after {CLOUD_TIMEOUT[1]}s. "
            "FIX: Try again in a moment, or the API may be overloaded."
        )
    except requests.exceptions.SSLError as e:
        raise CloudPermanentError(
            f"SSL certificate error: {e}. "
            "FIX: Update Python packages: pip install --upgrade certifi requests"
        )
    except (CloudTransientError, CloudPermanentError):
        raise  # Let these propagate to tenacity
    except Exception as e:
        raise CloudPermanentError(f"Unexpected cloud error: {type(e).__name__}: {e}")


# ============================================================
# PUBLIC API — Called by router.py
# ============================================================
def query_cloud(prompt, model=None, image_data=None):
    """
    Query the Gemini cloud API with full retry and error handling.
    
    Returns: response text (str)
    Raises: CloudExhaustedException if all retries fail
            CloudPermanentError if the error is not retryable
    """
    if model is None:
        model = CLOUD_MODEL_LIGHT

    if not GEMINI_API_KEY:
        raise CloudPermanentError(
            "API key not configured. "
            "FIX: Paste your Gemini API key into secrets/gemini_api_key.txt"
        )

    try:
        return _query_cloud_with_retry(prompt, model, image_data=image_data)
    except RetryError as e:
        # All retries exhausted (tenacity wraps the last exception)
        logger.error(f"Cloud API exhausted after {MAX_CLOUD_RETRIES} attempts.")
        logger.error("Triggering fallback to local model...")
        raise CloudExhaustedException(
            f"Cloud API failed after {MAX_CLOUD_RETRIES} retries. "
            f"Last error: {e.last_attempt.exception()}"
        )
    except CloudTransientError as e:
        # Tenacity re-raises the last exception with reraise=True
        logger.error(f"Cloud API exhausted (re-raised transient): {e}")
        logger.error("Triggering fallback to local model...")
        raise CloudExhaustedException(
            f"Cloud API failed after retries. Last transient error: {e}"
        )
    except CloudPermanentError:
        raise  # Permanent errors bubble up immediately


if __name__ == "__main__":
    # Quick standalone test
    print(f"Testing cloud model: {CLOUD_MODEL_LIGHT}")
    try:
        result = query_cloud("Say hello in one word.")
        print(f"SUCCESS: {result}")
    except (CloudExhaustedException, CloudPermanentError) as e:
        print(f"FAILED: {e}")
