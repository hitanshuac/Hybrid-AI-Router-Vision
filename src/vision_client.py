"""
Gemini 2.5 Flash Vision Extraction Client.

Converts raw Base64 image payloads into structured JSON using the
google-generativeai SDK's native multimodal + JSON schema mode.

Integrates Structural Layout Cache for zero-cost classification bypass
on recurring document structures.

SRE Safeguard: The synchronous SDK call is wrapped in asyncio.to_thread()
to keep the ASGI event loop completely unblocked (HANDOVER.md §3).
"""

import re
import os
import json
import asyncio
import logging
from google import generativeai as genai

from src.schemas import ExtractedInvoice, ExtractedLetter, DocumentType
from src.circuit_breaker import vision_circuit_breaker
from src.layout_cache import compute_layout_hash, lookup_cached_layout, cache_layout

logger = logging.getLogger("vision_client")

# ── DB Path (for layout cache lookups) ────────────────────────────
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DB_PATH = os.environ.get("TEST_DB_PATH", os.path.join(_DB_DIR, "pipeline_metrics.db"))


async def classify_and_extract_document(base64_image: str, api_key: str) -> tuple[DocumentType, dict]:
    """
    Two-stage execution abstraction wrapper. Classifies incoming asset geometry 
    off the main thread and enforces targeted structural text mappings.
    """
    return await asyncio.to_thread(_sync_pipeline_execution, base64_image, api_key)

def _sync_pipeline_execution(base64_data: str, api_key: str) -> tuple[DocumentType, dict]:
    # ── Circuit Breaker Gate ──────────────────────────────────────
    vision_circuit_breaker.check_state()

    if not api_key:
        from src.config import GEMINI_API_KEYS
        api_key = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
        
    if not api_key:
        raise RuntimeError("No Gemini API key found. Vision extraction unavailable.")
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    image_part = {"mime_type": "image/jpeg", "data": base64_data}
    
    try:
        # ── Stage 0: Structural Layout Cache Check ────────────────
        layout_hash = compute_layout_hash(base64_data)
        cached_type = lookup_cached_layout(_DB_PATH, layout_hash)

        if cached_type and cached_type in [DocumentType.INVOICE, DocumentType.LETTER]:
            # CACHE HIT — bypass LLM classification entirely ($0 cost)
            determined_type = cached_type
            logger.info(
                "[VISION] Layout cache HIT — skipping LLM classification. Type: %s",
                determined_type,
            )
        else:
            # CACHE MISS — proceed to LLM zero-shot classification
            # Stage 1: Zero-Shot Document Layout Classification
            classification_prompt = (
                "Analyze this document image layout. Classify its primary structural taxonomy rules.\n"
                "Return strictly one word of these choices: 'INVOICE' if it contains pricing vectors, totals, grids;\n"
                " or 'LETTER' if it represents unstructured text documents, correspondence, or notification prose."
            )
            
            type_response = model.generate_content([classification_prompt, image_part])
            determined_type = type_response.text.strip().upper()
            
            # Normalize structural exceptions safely
            if determined_type not in [DocumentType.INVOICE, DocumentType.LETTER]:
                determined_type = DocumentType.UNKNOWN

            # Persist to layout cache for future zero-cost lookups
            if determined_type in [DocumentType.INVOICE, DocumentType.LETTER]:
                cache_layout(_DB_PATH, layout_hash, determined_type)
            
        # Stage 2: Target Schema Generation Matrix
        if determined_type == DocumentType.INVOICE:
            extraction_prompt = "Extract accounting details accurately per data definition targets."
            target_schema = ExtractedInvoice
        elif determined_type == DocumentType.LETTER:
            extraction_prompt = "Perform semantic prose extraction, tracking entities, intent metrics, and text arrays."
            target_schema = ExtractedLetter
        else:
            raise ValueError(f"Document categorization execution failure. Unrecognized taxonomy framework.")

        # Stage 3: Direct JSON Extraction
        extraction_response = model.generate_content(
            contents=[extraction_prompt, image_part],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=target_schema,
                temperature=0.0
            )
        )
        
        # ── Success: Reset circuit breaker ────────────────────────
        vision_circuit_breaker.record_success()
        return DocumentType(determined_type), json.loads(extraction_response.text)

    except Exception as e:
        error_str = str(e).lower()
        # Detect upstream rate limit or service unavailability
        if "429" in error_str or "503" in error_str or "resource exhausted" in error_str or "too many requests" in error_str:
            # Parse Retry-After hint from upstream error response (if present)
            retry_after = None
            retry_match = re.search(r'retry[\-_ ]?after[:\s]*(\d+)', error_str)
            if retry_match:
                retry_after = float(retry_match.group(1))
                logger.info("[VISION] Parsed Retry-After: %ds", int(retry_after))
            vision_circuit_breaker.record_failure(retry_after=retry_after)
            logger.warning("[VISION] Upstream rate limit/outage detected: %s", e)
        raise


