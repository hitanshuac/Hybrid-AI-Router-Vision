import logging
from src.llm_cloud import query_cloud

logger = logging.getLogger("router")

def classify_and_route(prompt, image_data=None):
    """
    Simplified routing logic. 
    Always attempts the cloud cascade and returns the result.
    """
    try:
        response = query_cloud(prompt)
        return response, "CLOUD_CASCADE"
    except Exception as e:
        logger.error(f"Cloud cascade failed: {e}")
        return "All cloud providers failed. Please check your keys.", "ERROR"
