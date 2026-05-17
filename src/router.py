import copy
import logging
from src.llm_cloud import query_cloud, estimate_tokens_from_messages

logger = logging.getLogger("router")

# ============================================================
# EPHEMERAL CONTEXT GROUNDING — v2.3.0
# ============================================================
SYSTEM_GROUNDING_PROMPT = (
    "You are a helpful assistant powered by the Hybrid AI Router. "
    "Respond accurately, concisely, and professionally. "
    "If you are unsure about something, say so rather than guessing."
)

# ============================================================
# CONTEXT COMPACTION — v2.4.0
# ============================================================
MAX_WINDOW_SIZE = 10

BOILERPLATE_PREFIXES = [
    # Longest-first ordering for greedy match
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
    """
    Prepend the system grounding prompt at index 0 of a messages array.
    """
    system_msg = {"role": "system", "content": SYSTEM_GROUNDING_PROMPT}
    messages.insert(0, system_msg)
    logger.info(f"[CONTEXT GROUNDING] Injected system prompt. Payload now contains {len(messages)} messages.")
    return messages


def strip_boilerplate(messages: list) -> tuple:
    """
    Strip verbose AI filler prefixes from role: assistant messages.
    Returns (messages, strip_count).
    """
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
                if stripped:  # Only strip if result is non-empty
                    msg["content"] = stripped
                    strip_count += 1
                break  # Only strip the first (longest) match
    return messages, strip_count


def apply_sliding_window(messages: list, max_window: int = MAX_WINDOW_SIZE) -> tuple:
    """
    Enforce a hard cap on outbound message count.
    Pins the system message at index 0, retains only the most recent (max_window - 1) conversation messages.
    Returns (messages, drop_count).
    """
    if len(messages) <= max_window:
        return messages, 0

    before_count = len(messages)
    # Pin system message (index 0), take most recent (max_window - 1) from the rest
    system_msg = messages[0]
    recent = messages[-(max_window - 1):]
    compacted = [system_msg] + recent
    drop_count = before_count - len(compacted)
    return compacted, drop_count


def classify_and_route(prompt, image_data=None, messages=None):
    """
    Routing logic with the v2.4.0 5-step pipeline:
    1. Deep Copy  2. Grounding  3. Prefix Stripping  4. Sliding Window  5. Cascade

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

        # Observability: log only if compaction actually occurred
        if messages_dropped > 0 or prefixes_stripped > 0:
            logger.info(
                f"[CONTEXT COMPACTION] Compacted {before_count} → {len(working)} messages. "
                f"Stripped {prefixes_stripped} filler prefixes. "
                f"Tokens: {raw_tokens} → {compact_tokens} (saved {compaction_metrics['tokens_saved']})"
            )

        # === Step 5: Cascade ===
        response = query_cloud(messages=working)
        return response, "CLOUD_CASCADE", compaction_metrics

    except Exception as e:
        logger.error(f"Cloud cascade failed: {e}")
        return "All cloud providers failed. Please check your keys.", "ERROR", compaction_metrics
