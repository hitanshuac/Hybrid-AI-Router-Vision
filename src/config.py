import os
import sys
import logging

# Force UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("config")

def get_secrets_list(prefix):
    keys = []
    try:
        secrets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'secrets')
        if os.path.exists(secrets_dir):
            for f in os.listdir(secrets_dir):
                if f.startswith(prefix) and f.endswith('.txt'):
                    with open(os.path.join(secrets_dir, f), 'r') as file:
                        key = file.read().strip()
                        if key: keys.append(key)
    except: pass
    return keys

def run_startup_checks():
    """Stub for backward compatibility."""
    return {"api_key": True, "ollama": True, "cloud_models": True}

# Secret Loading
GROQ_API_KEYS = get_secrets_list('groq_api_key')
OPENROUTER_API_KEYS = get_secrets_list('openrouter_api_key')
NVIDIA_API_KEYS = get_secrets_list('nvidia_api_key')
GEMINI_API_KEYS = get_secrets_list('gemini_api_key')

# Simplified Defaults
PRIMARY_CLOUD_MODEL = "llama-3.3-70b-versatile"
SECONDARY_CLOUD_MODEL = "google/gemma-4-31b-it:free"
SAFETY_NET_MODEL = "meta/llama-3.1-8b-instruct"
GEMINI_MODEL = "gemini-2.5-flash"
LOCAL_MODEL_PRIMARY = "gemma2:9b"

# Ollama (Local) Configuration
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
LOCAL_TIMEOUT = (5, 120)  # (connect_timeout, read_timeout) in seconds
MAX_LOCAL_RETRIES = 3

# Telegram Bot
TELEGRAM_BOT_TOKEN = ""
_telegram_keys = get_secrets_list("telegram_bot_token")
if _telegram_keys:
    TELEGRAM_BOT_TOKEN = _telegram_keys[0]
