import logging
from src.llm_cloud import query_cloud
from src.vector_store import add_logic_trace
from src.config import CLOUD_MODEL_LIGHT

logger = logging.getLogger("distiller")

DISTILL_PROMPT = """
[TASK: DECONSTRUCT REASONING]
You are a Teacher model. Provide a high-quality, step-by-step reasoning trace for the user query, followed by the final answer.
Format:
REASONING: <step-by-step logic>
ANSWER: <final concise answer>

QUERY: {query}
"""

def harvest_logic(query, embedding):
    logger.info(f"🔬 Harvesting logic from Teacher (Flash) for query: {query[:50]}...")
    prompt = DISTILL_PROMPT.format(query=query)
    
    try:
        raw_response = query_cloud(prompt, model=CLOUD_MODEL_LIGHT)
        
        reasoning = ""
        answer = ""
        if "REASONING:" in raw_response and "ANSWER:" in raw_response:
            parts = raw_response.split("ANSWER:")
            reasoning = parts[0].replace("REASONING:", "").strip()
            answer = parts[1].strip()
        else:
            reasoning = "Direct Answer"
            answer = raw_response
            
        add_logic_trace(query, reasoning, answer, embedding)
        logger.info("📦 Logic trace saved to ChromaDB Logic Library.")
        return answer
    except Exception as e:
        logger.error(f"Logic harvesting failed: {e}")
        return None