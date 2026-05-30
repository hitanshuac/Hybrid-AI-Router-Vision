"""
Hybrid AI Router — 4-Tier Vision-Only Cascade Engine
=====================================================
Strict fallback waterfall using async HTTP clients.
Integrates SRE Centipede Guardrails (circuit breaker + token preflight).
Every tier is a unique vision-capable model+provider combination.
Zero duplicate endpoints. Zero rate limit waste.

v3.0.0 — Offsite Deployment Edition
"""

import copy
import logging
import time
import httpx
import asyncio
from typing import Optional, Tuple, Dict, Any, List

from src.config import (
    GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS, GEMINI_API_KEYS
)
from src.circuit_breaker import (
    estimate_tokens_from_messages,
    get_eligible_tiers,
    is_circuit_open,
    record_success,
    record_failure,
)

logger = logging.getLogger("router")

# ============================================================
# TIER DEFINITIONS
# ============================================================
TIERS = [
    {
        "tier": 1,
        "name": "Groq/Llama-3.2-Vision",
        "provider": "groq",
        "model": "llama-3.2-11b-vision-preview",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "timeout": 15,
        "format": "openai",
    },
    {
        "tier": 2,
        "name": "Gemini/2.5-Flash-Vision",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "timeout": 30,
        "format": "openai",
    },
    {
        "tier": 3,
        "name": "OpenRouter/Gemma-4-Vision",
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "timeout": 20,
        "format": "openai",
    },
    {
        "tier": 4,
        "name": "NVIDIA/Llama-3.2-90B-Vision",
        "provider": "nvidia",
        "model": "meta/llama-3.2-90b-vision-instruct",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "timeout": 15,
        "format": "openai",
    },
]

# ============================================================
# KEY POOL MAPPING
# ============================================================
_KEY_POOL = {
    "groq": GROQ_API_KEYS,
    "openrouter": OPENROUTER_API_KEYS,
    "nvidia": NVIDIA_API_KEYS,
    "gemini": GEMINI_API_KEYS,
}

# ============================================================
# EPHEMERAL CONTEXT GROUNDING — v2.3.0 (preserved)
# ============================================================
SYSTEM_GROUNDING_PROMPT = (
    "You are a helpful assistant powered by the Hybrid AI Router. "
    "Respond accurately, concisely, and professionally. "
    "If you are unsure about something, say so rather than guessing."
)

# ============================================================
# CONTEXT COMPACTION — v2.4.0 (preserved)
# ============================================================
MAX_WINDOW_SIZE = 10

BOILERPLATE_PREFIXES = [
    "I'd be happy to help you with that! ",
    "That's a great question! ",
    "I'd be happy to help! ",
    "Let me help you with that. ",
    "Great question! ",
    "Of course! ",
    "Of course, ",
    "Absolutely! ",
    "Certainly! ",
    "Sure! ",
    "Sure, ",
]


def ground_messages(messages: list) -> list:
    """Prepend the system grounding prompt at index 0 of a messages array."""
    system_msg = {"role": "system", "content": SYSTEM_GROUNDING_PROMPT}
    messages.insert(0, system_msg)
    logger.info(f"[CONTEXT GROUNDING] Injected system prompt. Payload now contains {len(messages)} messages.")
    return messages


def strip_boilerplate(messages: list) -> tuple:
    """Strip verbose AI filler prefixes from role: assistant messages."""
    strip_count = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        for prefix in BOILERPLATE_PREFIXES:
            if content.startswith(prefix):
                stripped = content[len(prefix):]
                if stripped:
                    msg["content"] = stripped
                    strip_count += 1
                break
    return messages, strip_count


def apply_sliding_window(messages: list, max_window: int = MAX_WINDOW_SIZE) -> tuple:
    """Enforce a hard cap on outbound message count."""
    if len(messages) <= max_window:
        return messages, 0
    before_count = len(messages)
    system_msg = messages[0]
    recent = messages[-(max_window - 1):]
    compacted = [system_msg] + recent
    drop_count = before_count - len(compacted)
    return compacted, drop_count


# ============================================================
# ASYNC CASCADE ENGINE — 9-Tier Waterfall
# ============================================================
async def _call_openai_format(
    client: httpx.AsyncClient, tier_def: dict, messages: list, api_key: str, image_data: str = None, json_mode: bool = False
) -> Optional[str]:
    """Call an OpenAI-compatible endpoint. Returns response text or None."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    # Select model based on whether image_data is present
    active_model = tier_def["model"]  # Every tier IS a vision model — no switching needed

    payload = {"model": active_model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = await client.post(
            tier_def["url"],
            headers=headers,
            json=payload,
            timeout=tier_def["timeout"],
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            record_failure(tier_def["tier"], resp.status_code)
            logger.warning(
                f"[CASCADE] Tier {tier_def['tier']} ({tier_def['name']}) — HTTP {resp.status_code}"
            )
            return None
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
        logger.warning(f"[CASCADE] Tier {tier_def['tier']} ({tier_def['name']}) — {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.error(f"[CASCADE] Tier {tier_def['tier']} ({tier_def['name']}) — Unexpected: {e}")
        return None


async def _try_tier(
    client: httpx.AsyncClient, tier_def: dict, messages: list, image_data: str = None, json_mode: bool = False
) -> Optional[str]:
    """Attempt a single tier. Handles key rotation for cloud providers."""
    tier_num = tier_def["tier"]
    provider = tier_def["provider"]

    # Circuit breaker gate
    if is_circuit_open(tier_num):
        logger.info(f"[CASCADE] Tier {tier_num} ({tier_def['name']}) — Circuit OPEN, skipping.")
        return None

    # OpenAI-format: rotate through available keys
    keys = _KEY_POOL.get(provider, [])
    if not keys:
        logger.debug(f"[CASCADE] Tier {tier_num} ({tier_def['name']}) — No API keys configured, skipping.")
        return None

    for key in keys:
        result = await _call_openai_format(client, tier_def, messages, key, image_data, json_mode)
        if result:
            record_success(tier_num)
            return result

    return None


async def cascade_async(messages: list, eligible_tiers: set, image_data: str = None, json_mode: bool = False) -> Tuple[Optional[str], str]:
    """
    Execute the 9-tier waterfall cascade asynchronously.
    Returns (response_text, tier_label) or (None, "EXHAUSTED").
    """
    async with httpx.AsyncClient() as client:
        for tier_def in TIERS:
            if tier_def["tier"] not in eligible_tiers:
                logger.info(
                    f"[CASCADE] Tier {tier_def['tier']} ({tier_def['name']}) — "
                    f"Skipped (not in eligible set)."
                )
                continue

            logger.info(f"[CASCADE] Trying Tier {tier_def['tier']}: {tier_def['name']}...")
            result = await _try_tier(client, tier_def, messages, image_data, json_mode)
            if result:
                logger.info(f"[CASCADE] ✅ Tier {tier_def['tier']} ({tier_def['name']}) responded.")
                return result, f"T{tier_def['tier']}_{tier_def['name']}"

    return None, "EXHAUSTED"


def cascade_sync(messages: list, eligible_tiers: set, image_data: str = None, json_mode: bool = False) -> Tuple[Optional[str], str]:
    """Synchronous wrapper for the async cascade — safe to call from sync code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context (e.g., FastAPI) — create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, cascade_async(messages, eligible_tiers, image_data, json_mode))
            return future.result()
    else:
        # No running loop, just use asyncio.run directly
        return asyncio.run(cascade_async(messages, eligible_tiers, image_data, json_mode))


# ============================================================
# PUBLIC API — classify_and_route (backward compatible)
# ============================================================
def classify_and_route(prompt, image_data=None, messages=None):
    """
    Routing logic with the v3.0.0 vision-only pipeline:
    1. Deep Copy  2. Grounding  3. Prefix Stripping  4. Sliding Window
    5. Preflight Token Check  6. Cascade

    Returns (response_text, tier_label, compaction_metrics).
    """
    compaction_metrics = {
        "raw_tokens": 0,
        "compact_tokens": 0,
        "tokens_saved": 0,
        "savings_pct": 0.0,
        "messages_dropped": 0,
        "prefixes_stripped": 0,
    }

    try:
        # === Step 1: Deep Copy ===
        if messages is not None:
            working = copy.deepcopy(messages)
        else:
            working = [{"role": "user", "content": prompt}]

        # Measure raw tokens BEFORE any mutation
        raw_tokens = estimate_tokens_from_messages(working)
        compaction_metrics["raw_tokens"] = raw_tokens

        # === Step 2: Grounding ===
        working = ground_messages(working)

        # === Step 3: Prefix Stripping ===
        working, prefixes_stripped = strip_boilerplate(working)
        compaction_metrics["prefixes_stripped"] = prefixes_stripped

        # === Step 4: Sliding Window ===
        before_count = len(working)
        working, messages_dropped = apply_sliding_window(working)
        compaction_metrics["messages_dropped"] = messages_dropped

        # Measure compact tokens AFTER all compaction
        compact_tokens = estimate_tokens_from_messages(working)
        compaction_metrics["compact_tokens"] = compact_tokens
        compaction_metrics["tokens_saved"] = raw_tokens - compact_tokens
        compaction_metrics["savings_pct"] = round(
            ((raw_tokens - compact_tokens) / raw_tokens) * 100, 2
        ) if raw_tokens > 0 else 0.0

        # Observability
        if messages_dropped > 0 or prefixes_stripped > 0:
            logger.info(
                f"[CONTEXT COMPACTION] Compacted {before_count} → {len(working)} messages. "
                f"Stripped {prefixes_stripped} filler prefixes. "
                f"Tokens: {raw_tokens} → {compact_tokens} (saved {compaction_metrics['tokens_saved']})"
            )

        # === Step 5: Preflight Token Check (Centipede Guardrail) ===
        eligible = get_eligible_tiers(compact_tokens)

        # === Step 6: 9-Tier Cascade ===
        response, tier_label = cascade_sync(working, eligible, image_data)

        if response is None:
            return (
                "All 4 vision tiers exhausted. Check API keys and cloud endpoints.",
                "ALL_EXHAUSTED",
                compaction_metrics,
            )

        return response, tier_label, compaction_metrics

    except Exception as e:
        logger.error(f"Cascade failure: {e}")
        return (
            "All cloud providers failed. Please check your keys.",
            "ERROR",
            compaction_metrics,
        )
