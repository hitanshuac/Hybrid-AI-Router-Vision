import json
import os
import logging
from src.llm_local import query_local

logger = logging.getLogger("context_manager")

SESSIONS_DIR = "sessions"

if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)

class ContextManager:
    """
    Manages conversational state to avoid hitting Cloud API rate limits.
    Uses 'State Externalization' to save history to disk, and uses the 
    free local model to summarize long histories into a compressed prompt.
    """
    def __init__(self, max_history_messages=5):
        self.max_history_messages = max_history_messages

    def _get_session_file(self, user_id):
        return os.path.join(SESSIONS_DIR, f"{user_id}.json")

    def load_session(self, user_id):
        file_path = self._get_session_file(user_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load session for {user_id}: {e}")
        
        return {"summary": "", "messages": []}

    def save_session(self, user_id, session_data):
        file_path = self._get_session_file(user_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session for {user_id}: {e}")

    def add_message(self, user_id, role, text):
        """Add a message to the user's history and trigger summarization if needed."""
        session = self.load_session(user_id)
        session["messages"].append({"role": role, "content": text})
        
        # If history gets too long, summarize it using the LOCAL model to save cloud tokens
        if len(session["messages"]) > self.max_history_messages * 2: # *2 for user/assistant pairs
            self._summarize_history(session)
            
        self.save_session(user_id, session)

    def _summarize_history(self, session):
        """Uses the free local Gemma model to compress conversation history."""
        logger.info("Conversation history long. Summarizing via local model to save cloud quota...")
        
        history_text = ""
        for msg in session["messages"][:-2]: # Keep the last exchange raw
            history_text += f"{msg['role'].upper()}: {msg['content']}\n"
            
        prompt = f"Summarize the following conversation context briefly so an AI can remember the state of the task:\n\nPast Summary:\n{session['summary']}\n\nRecent History:\n{history_text}"
        
        try:
            # We explicitly use local to avoid burning cloud tokens on meta-tasks
            summary, _ = query_local(prompt) 
            session["summary"] = summary
            # Keep only the last 2 messages (1 exchange) raw
            session["messages"] = session["messages"][-2:]
        except Exception as e:
            logger.error(f"Failed to summarize history: {e}")

    def build_prompt(self, user_id, new_message):
        """Constructs a highly token-efficient prompt for the router."""
        session = self.load_session(user_id)
        
        prompt = ""
        if session["summary"]:
            prompt += f"[SYSTEM NOTE: Previous Conversation Summary]\n{session['summary']}\n\n"
            
        if session["messages"]:
            prompt += "[Recent Conversation]\n"
            for msg in session["messages"]:
                prompt += f"{msg['role'].upper()}: {msg['content']}\n"
                
        prompt += f"\nUSER: {new_message}\n"
        
        return prompt

# Global instance
context_manager = ContextManager()
