import sqlite3
import time
import json
import uuid
import os
import functools
import logging

logger = logging.getLogger("observability")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "traces.db")

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Table for Traces (Full Request)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                query TEXT,
                response TEXT,
                model_used TEXT,
                total_latency REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                faithfulness_score REAL,
                relevance_score REAL,
                flagged INTEGER DEFAULT 0
            )
        ''')
        # Table for Spans (Individual Steps)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT,
                name TEXT,
                input_data TEXT,
                output_data TEXT,
                latency REAL,
                start_time REAL,
                FOREIGN KEY (trace_id) REFERENCES traces (trace_id)
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to init Tracing DB: {e}")

class Tracer:
    _current_trace_id = None

    @classmethod
    def start_trace(cls, query):
        cls._current_trace_id = str(uuid.uuid4())
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO traces (trace_id, query) VALUES (?, ?)", (cls._current_trace_id, query))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to start trace: {e}")
        return cls._current_trace_id

    @classmethod
    def end_trace(cls, response, model, latency, scores=None):
        if not cls._current_trace_id: return
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            f_score = scores.get("faithfulness", 0) if scores else 0
            r_score = scores.get("relevance", 0) if scores else 0
            # Flag if score is low but exists
            flagged = 1 if (0 < f_score < 3) or (0 < r_score < 3) else 0
            
            cursor.execute("UPDATE traces SET response=?, model_used=?, total_latency=?, faithfulness_score=?, relevance_score=?, flagged=? WHERE trace_id=?",
                           (response, model, latency, f_score, r_score, flagged, cls._current_trace_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to end trace: {e}")
        finally:
            cls._current_trace_id = None

def trace_span(name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not Tracer._current_trace_id:
                return func(*args, **kwargs)
            
            span_id = str(uuid.uuid4())
            start_time = time.time()
            # Capture input (simplified)
            input_summary = str(args)[:500] if args else ""
            if kwargs: input_summary += f" | kwargs: {str(kwargs)[:500]}"
            
            result = func(*args, **kwargs)
            
            latency = time.time() - start_time
            output_data = str(result)[:1000] # Cap output size
            
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO spans (span_id, trace_id, name, input_data, output_data, latency, start_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (span_id, Tracer._current_trace_id, name, input_summary, output_data, latency, start_time))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to log span {name}: {e}")
            
            return result
        return wrapper
    return decorator

# Auto-init on import
init_db()
def score_trace_faithfulness(query, response, context):
    if not context: return 5.0
    from src.llm_local import query_local
    judge_prompt = f'[TASK: FAITHFULNESS AUDIT]\nContext: {context}\nQuestion: {query}\nAnswer: {response}\nScore 1-5:'
    try:
        score_raw = query_local(judge_prompt).strip()
        import re
        match = re.search(r'\d', score_raw)
        return float(match.group()) if match else 3.0
    except Exception: return 0.0
