"""
Gemini 1.5 Flash Vision Extraction Client.

Converts raw Base64 image payloads into structured JSON using the
google-generativeai SDK's native multimodal + JSON schema mode.

SRE Safeguard: The synchronous SDK call is wrapped in asyncio.to_thread()
to keep the ASGI event loop completely unblocked (HANDOVER.md §3).
"""

import os
import json
import asyncio
import logging
from google import generativeai as genai

logger = logging.getLogger("vision_client")

# System grounding: ephemerally injected at execution time
VISION_SYSTEM_PROMPT = (
    "You are the Core Vision Extraction Node for the Hybrid AI Router Pipeline. "
    "Analyze the provided invoice image and extract all elements with perfect textual fidelity. "
    "Do not perform rounding or compute totals yourself—extract the exact values printed on the paper. "
    "Return a JSON object with keys: invoice_number, vendor_name, date, line_items (array of "
    "{item_code, description, quantity, unit_price, total_price}), tax_amount, grand_total."
)


def _sync_extract(base64_data: str, api_key: str) -> dict:
    """
    Synchronous extraction call. Isolated from the event loop by the
    async wrapper below.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Pack image matrix payload natively
    image_payload = {
        "mime_type": "image/jpeg",
        "data": base64_data,
    }

    response = model.generate_content(
        [VISION_SYSTEM_PROMPT, image_payload],
        generation_config={
            "response_mime_type": "application/json",
        },
    )

    extracted = json.loads(response.text)
    logger.info("[VISION] Extraction complete — invoice_number=%s", extracted.get("invoice_number", "N/A"))
    return extracted


async def extract_invoice_data(base64_data: str) -> dict:
    """
    Async entry point. Resolves the Gemini API key from the existing
    secrets key pool (config.py) and offloads the synchronous SDK call
    to a background thread via asyncio.to_thread().
    """
    from src.config import GEMINI_API_KEYS

    if not GEMINI_API_KEYS:
        raise RuntimeError("No Gemini API key found in secrets/. Vision extraction unavailable.")

    api_key = GEMINI_API_KEYS[0]

    # SRE: push synchronous SDK work off the ASGI event loop
    return await asyncio.to_thread(_sync_extract, base64_data, api_key)
