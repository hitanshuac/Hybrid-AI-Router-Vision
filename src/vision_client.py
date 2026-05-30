"""
Cascade-Based Vision Extraction Client.

Converts raw Base64 image payloads into structured JSON by routing
through the centralized 4-Tier Vision Cascade (Groq, Gemini, OpenRouter, NVIDIA).

Integrates Structural Layout Cache for zero-cost classification bypass
on recurring document structures.

SRE Safeguard: The synchronous SDK call is wrapped in asyncio.to_thread()
to keep the ASGI event loop completely unblocked (HANDOVER.md §3).
"""

import os
import json
import asyncio
import logging

from src.schemas import ExtractedInvoice, ExtractedLetter, DocumentType
from src.circuit_breaker import CircuitBreakerOpenException
from src.layout_cache import compute_layout_hash, lookup_cached_layout, cache_layout
from src.router import cascade_sync

logger = logging.getLogger("vision_client")

# ── DB Path (for layout cache lookups) ────────────────────────────
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.environ.get("TEST_DB_PATH", os.path.join(_DB_DIR, "pipeline_metrics.db"))

async def classify_and_extract_document(base64_image: str, api_key: str = None) -> tuple[DocumentType, dict]:
    """
    Two-stage execution abstraction wrapper. Classifies incoming asset geometry 
    off the main thread and enforces targeted structural text mappings.
    """
    return await asyncio.to_thread(_sync_pipeline_execution, base64_image)

def _sync_pipeline_execution(base64_data: str) -> tuple[DocumentType, dict]:
    # Construct the multimodal message format
    def build_message(prompt: str) -> list:
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"}}
                ]
            }
        ]

    # ── Stage 0: Structural Layout Cache Check ────────────────
    layout_hash = compute_layout_hash(base64_data)
    cached_type = lookup_cached_layout(_DB_PATH, layout_hash)

    determined_type = DocumentType.UNKNOWN

    if cached_type and cached_type in [DocumentType.INVOICE, DocumentType.LETTER]:
        # CACHE HIT — bypass LLM classification entirely ($0 cost)
        determined_type = cached_type
        logger.info(
            "[VISION] Layout cache HIT — skipping LLM classification. Type: %s",
            determined_type,
        )
    else:
        # CACHE MISS — proceed to LLM zero-shot classification via Cascade
        classification_prompt = (
            "Analyze this document image layout. Classify its primary structural taxonomy rules.\n"
            "Return strictly one word of these choices: 'INVOICE' if it contains pricing vectors, totals, grids;\n"
            " or 'LETTER' if it represents unstructured text documents, correspondence, or notification prose."
        )
        
        messages = build_message(classification_prompt)
        response_text, tier = cascade_sync(messages, eligible_tiers=set(range(1, 5)))
        
        if not response_text or response_text == "ALL_EXHAUSTED":
            raise RuntimeError(f"Vision Cascade exhausted during classification. {tier}")

        determined_type = response_text.strip().upper()
        
        # Normalize structural exceptions safely
        if determined_type not in [DocumentType.INVOICE, DocumentType.LETTER]:
            determined_type = DocumentType.UNKNOWN

        # Persist to layout cache for future zero-cost lookups
        if determined_type in [DocumentType.INVOICE, DocumentType.LETTER]:
            cache_layout(_DB_PATH, layout_hash, determined_type)

    # ── Stage 2: Target Schema Generation Matrix ────────────────
    if determined_type == DocumentType.INVOICE:
        schema_json = json.dumps(ExtractedInvoice.model_json_schema())
        extraction_prompt = (
            "Extract accounting details accurately per data definition targets. "
            f"You MUST return valid JSON matching this exact schema: {schema_json}"
        )
    elif determined_type == DocumentType.LETTER:
        schema_json = json.dumps(ExtractedLetter.model_json_schema())
        extraction_prompt = (
            "Perform semantic prose extraction, tracking entities, intent metrics, and text arrays. "
            f"You MUST return valid JSON matching this exact schema: {schema_json}"
        )
    else:
        raise ValueError(f"Document categorization execution failure. Unrecognized taxonomy framework: {determined_type}")

    # ── Stage 3: Direct JSON Extraction via Cascade ────────────────
    messages = build_message(extraction_prompt)
    response_text, tier = cascade_sync(messages, eligible_tiers=set(range(1, 5)), json_mode=True)
    
    if not response_text or response_text == "ALL_EXHAUSTED":
            raise RuntimeError(f"Vision Cascade exhausted during JSON extraction. {tier}")

    try:
        extracted_data = json.loads(response_text)
        return DocumentType(determined_type), extracted_data
    except json.JSONDecodeError as e:
        logger.error(f"[VISION] Failed to parse JSON from tier {tier}: {response_text}")
        raise RuntimeError(f"Vision model returned invalid JSON: {str(e)}")


