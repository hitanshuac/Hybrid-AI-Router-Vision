import sqlite3
import os
import json
import logging

logger = logging.getLogger("state_provider")

STATE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state.db")

def init_state():
    try:
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()
        # User Session Storage
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                last_sync DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Cross-Device Conversation History (Multi-Device State Sync)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conv_id TEXT PRIMARY KEY,
                user_id TEXT,
                history_json TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to init State DB: {e}")

class StateProvider:
    @staticmethod
    def sync_history(user_id, conv_id, history):
        try:
            conn = sqlite3.connect(STATE_DB)
            cursor = conn.cursor()
            history_str = json.dumps(history)
            cursor.execute("INSERT OR REPLACE INTO conversations (conv_id, user_id, history_json, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                           (conv_id, user_id, history_str))
            conn.commit()
            conn.close()
            logger.info(f"🔄 Sync complete for User {user_id} | Conv {conv_id}")
        except Exception as e:
            logger.error(f"Sync failed: {e}")

    @staticmethod
    def get_history(user_id, conv_id):
        try:
            conn = sqlite3.connect(STATE_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT history_json FROM conversations WHERE user_id=? AND conv_id=?", (user_id, conv_id))
            row = cursor.fetchone()
            conn.close()
            return json.loads(row[0]) if row else []
        except Exception:
            return []

init_state()