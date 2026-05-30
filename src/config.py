import os
import sys
import logging

# Force UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("config")

def get_secrets_list(prefix):
    """
    Load API keys from:
      1. Environment variables (HF Spaces / cloud — comma-separated)
      2. secrets/ directory files (local / docker-compose)
    """
    keys = []

    # === Source 1: Environment variables ===
    # e.g., GROQ_API_KEY="key1,key2"  or  GROQ_API_KEY_1="key1"
    env_name = prefix.upper()
    env_val = os.environ.get(env_name, "").strip()
    if env_val:
        keys.extend([k.strip() for k in env_val.split(",") if k.strip()])

    # Also check numbered variants: GROQ_API_KEY_1, GROQ_API_KEY_2, etc.
    for i in range(1, 11):
        env_val = os.environ.get(f"{env_name}_{i}", "").strip()
        if env_val:
            keys.append(env_val)

    # === Source 2: secrets/ directory (backward compatible) ===
    try:
        secrets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'secrets')
        if os.path.exists(secrets_dir):
            for f in os.listdir(secrets_dir):
                if f.startswith(prefix) and f.endswith('.txt'):
                    with open(os.path.join(secrets_dir, f), 'r') as file:
                        key = file.read().strip()
                        if key and key not in keys:
                            keys.append(key)
    except Exception as e:
        logger.error(f"[CONFIG] Failed to load secrets from directory: {e}")

    return keys

def run_startup_checks():
    """Stub for backward compatibility."""
    return {"api_key": True, "ollama": True, "cloud_models": True}

# Secret Loading
GROQ_API_KEYS = get_secrets_list('groq_api_key')
OPENROUTER_API_KEYS = get_secrets_list('openrouter_api_key')
NVIDIA_API_KEYS = get_secrets_list('nvidia_api_key')
GEMINI_API_KEYS = get_secrets_list('gemini_api_key')

# Vision-Only Cascade Model Defaults (documentation only — TIERS in router.py is authoritative)
PRIMARY_VISION_MODEL = "llama-3.2-11b-vision-preview"
SECONDARY_VISION_MODEL = "gemini-2.5-flash"
SAFETY_NET_VISION_MODEL = "meta/llama-3.2-90b-vision-instruct"
# Startup log — show key counts (never values) for observability
logger.info(
    f"[CONFIG] Keys loaded — Groq:{len(GROQ_API_KEYS)} "
    f"OpenRouter:{len(OPENROUTER_API_KEYS)} NVIDIA:{len(NVIDIA_API_KEYS)} "
    f"Gemini:{len(GEMINI_API_KEYS)}"
)

