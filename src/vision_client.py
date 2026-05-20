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

from src.schemas import ExtractedInvoice, ExtractedLetter, DocumentType
from src.circuit_breaker import vision_circuit_breaker

logger = logging.getLogger("vision_client")

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
            vision_circuit_breaker.record_failure()
            logger.warning("[VISION] Upstream rate limit/outage detected: %s", e)
        raise

