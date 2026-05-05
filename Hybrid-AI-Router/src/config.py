"""
Hybrid AI Router — Centralized Configuration & Startup Validation
=================================================================
This module handles:
  - Reading API keys from the secrets/ folder
  - Logging configuration for the entire application
  - Auto-discovering available Gemini cloud model names
  - Validating that all dependencies are reachable at startup

TROUBLESHOOTING:
  - "API key missing": Paste your Gemini key into secrets/gemini_api_key.txt
  - "Ollama not reachable": Run 'ollama serve' or start the Ollama app
  - "No cloud models found": Check internet connection or API key validity
"""

import os
import sys
import logging
import requests

# Force UTF-8 encoding for Windows terminals (fixes cp1252 emoji crash)
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# LOGGING SETUP — Structured, timestamped, Docker-compatible
# ============================================================
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,  # Force stdout for Docker log capture
)
logger = logging.getLogger("config")


# ============================================================
# SECRET MANAGEMENT
# ============================================================
def get_secret(secret_name):
    """
    Read a secret from the secrets/ folder.
    
    TROUBLESHOOTING:
      - FileNotFoundError: The secrets/ folder or the .txt file is missing.
        FIX: Create secrets/<secret_name>.txt and paste your key inside.
      - Empty string returned: The file exists but has no content.
        FIX: Open the file and paste the key (just the alphanumeric code, no quotes).
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        secrets_dir = os.path.join(project_root, 'secrets')
        file_path = os.path.join(secrets_dir, f"{secret_name}.txt")

        if not os.path.exists(file_path):
            logger.warning(f"Secret file not found: {file_path}")
            return None

        with open(file_path, 'r') as f:
            content = f.read().strip()
            if not content:
                logger.warning(f"Secret file is empty: {file_path}")
                return None
            return content
    except PermissionError:
        logger.error(f"Permission denied reading secret: {file_path}")
        logger.error("FIX: Right-click the file > Properties > Security > Allow Read")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading secret '{secret_name}': {e}")
        return None


# ============================================================
# API KEYS
# ============================================================
GEMINI_API_KEY = get_secret('gemini_api_key')
TELEGRAM_BOT_TOKEN = get_secret('telegram_bot_token')


# ============================================================
# MODEL CONFIGURATION — Defaults (may be overridden by auto-discovery)
# ============================================================
LOCAL_MODEL_PRIMARY = "gemma2:9b"
LOCAL_MODEL_SECONDARY = "gemma4:latest"

# These are fallback defaults. Auto-discovery below will try to find
# the actual model names available on your API key.
CLOUD_MODEL_LIGHT = "gemini-2.0-flash"
CLOUD_MODEL_PRO = "gemini-2.5-pro"

# Ollama host — reads from environment variable for Docker compatibility
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Timeouts (connect_seconds, read_seconds)
CLOUD_TIMEOUT = (5, 30)
LOCAL_TIMEOUT = (5, 120)

# Retry configuration
MAX_CLOUD_RETRIES = 4
MAX_LOCAL_RETRIES = 2


# ============================================================
# AUTO-DISCOVERY — Find valid Gemini model names from Google API
# ============================================================
def discover_cloud_models():
    """
    Query the Gemini API to find currently available model names.
    This prevents 404 errors caused by Google deprecating old model IDs.
    
    TROUBLESHOOTING:
      - "No internet": Falls back to hardcoded defaults above.
      - "API key invalid (401/403)": Check your key at https://aistudio.google.com/
      - "Timeout": Google servers may be slow. Defaults will be used.
    """
    global CLOUD_MODEL_LIGHT, CLOUD_MODEL_PRO

    if not GEMINI_API_KEY:
        logger.warning("Skipping model discovery — no API key found.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"

    try:
        response = requests.get(url, timeout=(5, 10))
        if response.status_code == 401 or response.status_code == 403:
            logger.error("API key is invalid or expired (401/403).")
            logger.error("FIX: Get a new key at https://aistudio.google.com/apikey")
            return
        response.raise_for_status()
        data = response.json()
        models = data.get('models', [])

        # Extract model names (only actual Gemini models, not experimental/test)
        model_names = [m.get('name', '').replace('models/', '') for m in models]
        gemini_models = [n for n in model_names if n.startswith('gemini-')]

        # Find Flash models: must start with 'gemini-' and contain 'flash'
        # Exclude 'thinking' variants (they use a different API flow)
        # Prefer stable models (no 'preview', 'exp', 'latest' suffix)
        flash_candidates = [n for n in gemini_models if 'flash' in n and 'thinking' not in n and 'lite' not in n]
        
        # Find Pro models: must start with 'gemini-' and contain 'pro'
        pro_candidates = [n for n in gemini_models if 'pro' in n and 'thinking' not in n]

        # Prefer models with version numbers (e.g., gemini-2.0-flash) over aliases (e.g., gemini-flash-latest)
        def score_model(name):
            """Higher score = more preferred."""
            score = 0
            if 'latest' in name: score += 1   # Aliases are okay
            if '2.0' in name: score += 10
            if '2.5' in name: score += 20
            if '3.0' in name: score += 30
            if 'preview' not in name and 'exp' not in name: score += 5  # Prefer stable
            return score

        if flash_candidates:
            flash_candidates.sort(key=score_model, reverse=True)
            CLOUD_MODEL_LIGHT = flash_candidates[0]
            logger.info(f"Auto-discovered Flash model: {CLOUD_MODEL_LIGHT}")
            logger.info(f"  Other Flash candidates: {flash_candidates[1:5]}")
        else:
            logger.warning(f"No Flash model found. Using default: {CLOUD_MODEL_LIGHT}")

        if pro_candidates:
            pro_candidates.sort(key=score_model, reverse=True)
            CLOUD_MODEL_PRO = pro_candidates[0]
            logger.info(f"Auto-discovered Pro model: {CLOUD_MODEL_PRO}")
            logger.info(f"  Other Pro candidates: {pro_candidates[1:5]}")
        else:
            logger.warning(f"No Pro model found. Using default: {CLOUD_MODEL_PRO}")

        logger.info(f"Total models available on your key: {len(model_names)}")

    except requests.exceptions.ConnectionError:
        logger.warning("No internet connection — using default model names.")
        logger.warning("FIX: Check your Wi-Fi/Ethernet connection.")
    except requests.exceptions.Timeout:
        logger.warning("Google API timed out during model discovery — using defaults.")
    except Exception as e:
        logger.warning(f"Model discovery failed: {e} — using defaults.")


# ============================================================
# OLLAMA HEALTH CHECK
# ============================================================
def check_ollama_health():
    """
    Verify that the local Ollama server is running and the target model is pulled.
    
    TROUBLESHOOTING:
      - "Connection refused": Ollama is not running.
        FIX (Windows): Open Start menu, search for "Ollama", click to launch it.
        FIX (Terminal): Run 'ollama serve' in a separate terminal window.
      - "Model not found": The model hasn't been downloaded yet.
        FIX: Run 'ollama pull gemma2:9b' in your terminal.
    """
    try:
        tags_url = f"{OLLAMA_HOST}/api/tags"
        response = requests.get(tags_url, timeout=(3, 5))
        response.raise_for_status()
        data = response.json()
        available_models = [m.get('name', '') for m in data.get('models', [])]

        if LOCAL_MODEL_PRIMARY in available_models:
            logger.info(f"Ollama health check PASSED — {LOCAL_MODEL_PRIMARY} is ready.")
            return True
        else:
            # Check for partial match (e.g., "gemma2:9b" might be listed as "gemma2:9b-instruct")
            partial_matches = [m for m in available_models if LOCAL_MODEL_PRIMARY.split(':')[0] in m]
            if partial_matches:
                logger.info(f"Ollama health check PASSED — Found: {partial_matches[0]}")
                return True
            else:
                logger.error(f"Model '{LOCAL_MODEL_PRIMARY}' NOT found on Ollama server.")
                logger.error(f"Available models: {available_models}")
                logger.error(f"FIX: Run 'ollama pull {LOCAL_MODEL_PRIMARY}' in your terminal.")
                return False

    except requests.exceptions.ConnectionError:
        logger.error("Ollama server is NOT running (Connection Refused).")
        logger.error(f"Attempted to reach: {OLLAMA_HOST}")
        logger.error("FIX (Windows): Open Start menu > search 'Ollama' > click to launch.")
        logger.error("FIX (Terminal): Run 'ollama serve' in a new terminal window.")
        return False
    except requests.exceptions.Timeout:
        logger.error("Ollama server is not responding (Timeout).")
        logger.error("FIX: Ollama may be loading a model. Wait 30 seconds and try again.")
        return False
    except Exception as e:
        logger.error(f"Ollama health check failed unexpectedly: {e}")
        return False


# ============================================================
# STARTUP VALIDATION — Run all checks when this module is imported
# ============================================================
def run_startup_checks():
    """Run all validation checks. Returns a status dict."""
    status = {
        "api_key": False,
        "ollama": False,
        "cloud_models": False,
    }

    # 1. Check API Key
    if GEMINI_API_KEY:
        logger.info(f"Gemini API key loaded (ends in ...{GEMINI_API_KEY[-4:]})")
        status["api_key"] = True
    else:
        logger.warning("Gemini API key NOT found.")
        logger.warning("FIX: Paste your key into secrets/gemini_api_key.txt")
        logger.warning("Cloud routing will be DISABLED. All queries go to Local Gemma.")

    # 2. Check Ollama
    status["ollama"] = check_ollama_health()

    # 3. Discover cloud models (only if key exists)
    if status["api_key"]:
        discover_cloud_models()
        status["cloud_models"] = True

    return status
