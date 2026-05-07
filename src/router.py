import time
"""
Hybrid AI Router ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â Semantic RAG-based Routing Brain
===================================================
This module calculates vector embeddings of the user's prompt and compares
them against "Anchor Vectors" for each tier. This provides an intelligent,
context-aware weighting system for routing decisions.

FALLBACK CHAIN:
  Tier 2 (Gemini Pro) ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ fails ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ Tier 1 (Gemini Flash) ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ fails ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ Tier 0 (Local Gemma)
"""

import logging
import json
import os
import numpy as np
from src.llm_local import query_local, LocalUnavailableException, get_embedding
from src.llm_cloud import query_cloud, CloudExhaustedException, CloudPermanentError
from src.config import CLOUD_MODEL_LIGHT, CLOUD_MODEL_PRO
from src.quota import quota_tracker
from src.prompt_registry import prompt_registry
from src.observability import Tracer, trace_span
from src.distiller import harvest_logic
from src.vector_store import get_logic_trace
from src.vector_store import check_cache, add_to_cache, search_rag

logger = logging.getLogger("router")

# ============================================================
# SEMANTIC ROUTER
# ============================================================
class SemanticRouter:
    def __init__(self):
        # Anchor texts define the "ideal" query for each tier.
        self.anchors = {
            "TIER_2_PRO": [
                "Design a scalable microservice architecture for a high-traffic e-commerce platform.",
                "Refactor this legacy monolith into a modern serverless application.",
                "Analyze the time and space complexity of this distributed algorithm.",
                "What are the trade-offs between eventual consistency and strong consistency in this database schema?",
                "Create a comprehensive production deployment plan and CI/CD pipeline strategy."
            ],
            "TIER_1_FLASH": [
                "Write a Python script to parse this JSON file and extract the email addresses.",
                "How do I fix this React useEffect hook infinite loop error?",
                "Create a Dockerfile for a Node.js Express application.",
                "Write a SQL query to join the users table with the orders table.",
                "Explain how this regular expression works."
            ],
            "TIER_0_LOCAL": [
                "Hello, how are you today?",
                "What is the capital of France?",
                "Write a short, funny poem about a cat.",
                "Summarize this short paragraph.",
                "Who was the 16th president of the United States?"
            ]
        }
        
        # Cache for embedded anchors to avoid recomputing them
        self.anchor_embeddings = {}
        self._initialize_anchors()

    def _initialize_anchors(self):
        """Pre-compute embeddings for all anchors."""
        logger.info("Initializing Semantic Router anchors...")
        for tier, texts in self.anchors.items():
            embeddings = []
            for text in texts:
                emb = get_embedding(text)
                if emb:
                    embeddings.append(emb)
            if embeddings:
                self.anchor_embeddings[tier] = np.array(embeddings)
            else:
                logger.error(f"Failed to initialize anchors for {tier}")

    def cosine_similarity(self, v1, v2):
        """Calculate cosine similarity between two vectors."""
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    def calculate_weights(self, prompt):
        """
        Embeds the prompt and compares it to the anchors.
        Returns a dictionary of max similarity weights for each tier.
        """
        prompt_emb = get_embedding(prompt)
        if not prompt_emb:
            logger.warning("Failed to get embedding for prompt. Falling back to Tier 0.")
            return {"TIER_2_PRO": 0.0, "TIER_1_FLASH": 0.0, "TIER_0_LOCAL": 1.0}
            
        prompt_vec = np.array(prompt_emb)
        weights = {}
        
        for tier, anchors in self.anchor_embeddings.items():
            if len(anchors) == 0:
                weights[tier] = 0.0
                continue
                
            # Calculate similarity against all anchors in this tier
            similarities = [self.cosine_similarity(prompt_vec, anchor) for anchor in anchors]
            # Use the max similarity score as the weight for this tier
            weights[tier] = max(similarities)
            
        return weights

    def route(self, prompt):
        """Determine the winning tier based on weights and thresholds."""
        weights = self.calculate_weights(prompt)
        logger.info(f"Router Weights: Pro={weights.get('TIER_2_PRO', 0):.2f}, Flash={weights.get('TIER_1_FLASH', 0):.2f}, Local={weights.get('TIER_0_LOCAL', 0):.2f}")
        
        # Thresholds
        if weights.get("TIER_2_PRO", 0) > 0.65:
            return "TIER_2_PRO"
        if weights.get("TIER_1_FLASH", 0) > 0.60:
            return "TIER_1_FLASH"
            
        return "TIER_0_LOCAL"

# Initialize global router instance
semantic_router = SemanticRouter()


# ============================================================
# CIRCUIT BREAKER ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â Graceful fallback chain
# ============================================================
@trace_span("classify_and_route")
def classify_and_route(prompt, image_data=None):
    Tracer.start_trace(prompt)
    start_time_total = time.time()

    # 1. Check for Image (Multimodal Bypass)
    if image_data:
        logger.info("Ã°Å¸â€œÂ¸ Vision request detected. Routing to Gemini Flash (Vision Tier)...")
        try:
            response = query_cloud(prompt, model=CLOUD_MODEL_LIGHT, image_data=image_data)
            elapsed_total = time.time() - start_time_total
            Tracer.end_trace(response, f"Gemini Flash [{CLOUD_MODEL_LIGHT}] (Cloud Vision)", elapsed_total)
            return response, f"Gemini Flash [{CLOUD_MODEL_LIGHT}] (Cloud Vision)"
        except Exception as e:
            logger.error(f"Vision routing failed: {e}")
            Tracer.end_trace("Ã¢Å¡Â Ã¯Â¸Â Vision processing failed.", "ERROR - Vision", 0)
            return "Ã¢Å¡Â Ã¯Â¸Â Vision processing failed.", "ERROR - Vision"

    prompt_emb = get_embedding(prompt)
    
    # 2. Check Semantic Cache (ChromaDB)
    if prompt_emb:
        cached_result = check_cache(prompt_emb)
        if cached_result:
            response, model = cached_result
            logger.info("Ã°Å¸Å¸Â¢ SEMANTIC CACHE HIT - Zero Cost Routing.")
            elapsed_total = time.time() - start_time_total
            Tracer.end_trace(response, model, elapsed_total)
            return response, model

    # 3. Retrieve RAG Context
    rag_context = ""
    if prompt_emb:
        rag_chunks = search_rag(prompt_emb)
        if rag_chunks:
            logger.info(f"Ã°Å¸â€œÅ¡ Retrieved {len(rag_chunks)} RAG chunks. Injecting into prompt...")
            rag_context = "\n\n[SYSTEM NOTE: Retrieved Context]\n" + "\n---\n".join(rag_chunks)

    final_prompt = prompt + rag_context
    tier = semantic_router.route(prompt)
    response = ""
    model_used = ""

    # ---- TIER 2: Gemini Pro ----
    if tier == "TIER_2_PRO":
        logger.info("Ã°Å¸Â§Â  High complexity detected. Routing to Gemini Pro...")
        try:
            response = query_cloud(final_prompt, model=CLOUD_MODEL_PRO)
            model_used = f"Gemini Pro [{CLOUD_MODEL_PRO}] (Cloud)"
        except (CloudPermanentError, CloudExhaustedException) as e:
            logger.warning(f"Gemini Pro failed: {e}")
            tier = "TIER_1_FLASH" # Fallback

    # ---- TIER 1: Gemini Flash ----
    if tier == "TIER_1_FLASH" and not response:
        logger.info("Ã¢Å¡Â¡ Technical task detected. Routing to Gemini Flash...")
        try:
            # TEACHER-STUDENT LOOP: Harvest reasoning while cloud is active
            response = harvest_logic(prompt, prompt_emb)
            if not response:
                response = query_cloud(final_prompt, model=CLOUD_MODEL_LIGHT)
            model_used = f"Gemini Flash [{CLOUD_MODEL_LIGHT}] (Cloud - Logic Harvested)"
        except (CloudPermanentError, CloudExhaustedException) as e:
            logger.warning(f"Gemini Flash failed: {e}")
            # Fallback to local handled below

    # ---- TIER 0: Local Gemma ----
    if not response:
        logger.info("Ã°Å¸ÂÂ  General task detected. Routing to Local Gemma...")
        response, model_used = _try_local(final_prompt, fallback_reason=None)

    # Save to ChromaDB cache before returning
    if prompt_emb and not "ERROR" in model_used:
        add_to_cache(prompt, response, model_used, prompt_emb)

    elapsed_total = time.time() - start_time_total
    Tracer.end_trace(response, model_used, elapsed_total)
    return response, model_used


def _try_local(prompt, fallback_reason=None):
    """Attempt to query the local Ollama model."""
    try:
        response = query_local(prompt)
        model_label = "Gemma 2 9B (Local)"
        if fallback_reason:
            model_label += f" ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â FALLBACK ({fallback_reason})"
        return response, model_label
    except LocalUnavailableException as e:
        logger.error(f"Local model also failed: {e}")
        error_msg = "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã¢â‚¬Â¦Ãƒâ€šÃ‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¯ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¸ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â  ALL MODELS ARE CURRENTLY UNAVAILABLE."
        return error_msg, "ERROR ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â No models available"
