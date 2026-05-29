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
from src.circuit_breaker import is_circuit_open, record_success, record_failure, CircuitBreakerOpenException
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
    if is_circuit_open(3):
        raise CircuitBreakerOpenException("Circuit Breaker OPEN. Upstream rate limit exceeded.")

    from src.config import GEMINI_API_KEYS
    keys_to_try = [api_key] if api_key else GEMINI_API_KEYS
    
    if not keys_to_try:
        raise RuntimeError("No Gemini API key found. Vision extraction unavailable.")
        
    last_error = None
    for current_key in keys_to_try:
        try:
            genai.configure(api_key=current_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            image_part = {"mime_type": "image/jpeg", "data": base64_data}
            
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
            record_success(3)
            return DocumentType(determined_type), json.loads(extraction_response.text)
            
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Detect upstream rate limit or service unavailability
            if "429" in error_str or "503" in error_str or "resource" in error_str or "too many" in error_str:
                status_code = 429 if "429" in error_str or "resource" in error_str or "too many" in error_str else 503
                record_failure(3, status_code)
                logger.warning(f"[VISION] Upstream rate limit/outage with current key: {e}")
            else:
                logger.warning(f"[VISION] Error with current key: {e}")
            
            # If it's the last key, we raise the error
            continue

    # If all keys failed, raise the final exception
    raise last_error


