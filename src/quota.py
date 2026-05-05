import json
import os
import datetime
import logging

logger = logging.getLogger("quota")

QUOTA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".quota.json")
DAILY_LIMIT = 1500  # Gemini Free Tier limit

class QuotaTracker:
    def __init__(self):
        self.usage = self._load()
    
    def _load(self):
        today = datetime.date.today().isoformat()
        if os.path.exists(QUOTA_FILE):
            try:
                with open(QUOTA_FILE, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == today:
                        return data.get('count', 0)
            except Exception as e:
                logger.warning(f"Failed to load quota file: {e}")
        return 0
        
    def _save(self):
        today = datetime.date.today().isoformat()
        try:
            with open(QUOTA_FILE, 'w') as f:
                json.dump({'date': today, 'count': self.usage}, f)
        except Exception as e:
            logger.warning(f"Failed to save quota file: {e}")

    def increment(self):
        self.usage += 1
        self._save()
        
    def get_remaining(self):
        return max(0, DAILY_LIMIT - self.usage)

quota_tracker = QuotaTracker()
