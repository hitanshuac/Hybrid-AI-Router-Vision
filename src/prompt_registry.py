import json
import os
import logging

logger = logging.getLogger("prompt_registry")

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts")

class PromptRegistry:
    def __init__(self, version="v1"):
        self.version = version
        self.anchors = {}
        self.thresholds = {"TIER_2_PRO": 0.65, "TIER_1_FLASH": 0.60}
        self._load_data()

    def _load_data(self):
        filename = f"router_{self.version}.json"
        path = os.path.join(PROMPTS_DIR, filename)
        
        if not os.path.exists(path):
            logger.error(f"Prompt version {self.version} not found at {path}")
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                logger.info(f"Loaded Prompt Registry: {filename}")
                self.anchors = data.get("anchors", {})
                self.thresholds = data.get("thresholds", self.thresholds)
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")

    def get_anchors(self):
        return self.anchors
    
    def get_thresholds(self):
        return self.thresholds

# Global instance
prompt_registry = PromptRegistry(version="v2")