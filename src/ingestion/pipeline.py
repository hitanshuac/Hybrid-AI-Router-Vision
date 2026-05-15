import time
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from pydantic import ValidationError
from .models import UsageRecord
from .database import get_duckdb_conn, initialize_tables
import logging

logger = logging.getLogger("ingestion.pipeline")

class IngestionPipeline:
    def __init__(self, db_path: str = "data/usage.db"):
        self.db_path = db_path
        self.consecutive_429s = 0
        self.max_allowed_429s = 3
        self.quarantine_dir = "data"

    def fetch_data(self) -> List[Dict[str, Any]]:
        """
        Simulates fetching data from an external API.
        In a real scenario, this would use 'requests' with exponential backoff.
        """
        # Simulated data with some "bad" records for quarantine testing
        return [
            {
                "request_id": f"req_{int(time.time())}_1",
                "timestamp": datetime.now().isoformat(),
                "model_name": "llama-3.3-70b",
                "provider": "groq",
                "prompt_tokens": 120,
                "completion_tokens": 450,
                "status": "success",
                "latency_ms": 150.5
            },
            {
                "request_id": f"req_{int(time.time())}_2",
                "timestamp": datetime.now().isoformat(),
                "model_name": "gemma-2-9b",
                "provider": "ollama",
                "prompt_tokens": -50,  # BAD DATA: Negative tokens
                "completion_tokens": 100,
                "status": "success",
                "latency_ms": 500.0
            }
        ]

    def validate_records(self, raw_data: List[Dict[str, Any]]):
        valid_records = []
        quarantine_records = []

        for record in raw_data:
            try:
                # Obeying data-validation.md: Non-Blocking Validation
                validated = UsageRecord.model_validate(record)
                valid_records.append(validated.model_dump())
            except ValidationError as e:
                # Obeying data-validation.md: Quarantine Protocol
                logger.warning(f"Validation failed for record {record.get('request_id')}: {e.json()}")
                record["error_msg"] = str(e)
                quarantine_records.append(record)

        return valid_records, quarantine_records

    def quarantine_bad_data(self, records: List[Dict[str, Any]]):
        if not records:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.quarantine_dir}/quarantine_{timestamp}.parquet"
        
        # Using Pandas/Pyarrow for Parquet (DuckDB Optimizer Skill recommendation)
        df = pd.DataFrame(records)
        df.to_parquet(filename)
        logger.info(f"Quarantined {len(records)} records to {filename}")

    def load_to_duckdb(self, records: List[Dict[str, Any]]):
        if not records:
            return
        
        conn = get_duckdb_conn(self.db_path)
        initialize_tables(conn)
        
        # Convert to DataFrame for efficient DuckDB ingestion
        df = pd.DataFrame(records)
        
        # Idempotent Load: INSERT OR REPLACE (SQL Standards Rule)
        conn.execute("INSERT OR REPLACE INTO usage_metrics SELECT * FROM df")
        
        # Explicit Checkpoint (Error Recovery Rule)
        conn.execute("CHECKPOINT")
        conn.close()
        logger.info(f"Successfully loaded {len(records)} records to DuckDB.")

    def run(self):
        logger.info("Starting Daily Ingestion Workflow...")
        
        # 1. Fetch
        try:
            # Simulate fetching with error monitoring (Circuit Breaker Rule)
            raw_data = self.fetch_data()
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
            return

        # 2. Validate
        valid, bad = self.validate_records(raw_data)
        
        # 3. Quarantine
        self.quarantine_bad_data(bad)
        
        # 4. Load
        self.load_to_duckdb(valid)
        
        logger.info(f"Workflow Complete. Fetched: {len(raw_data)}, Ingested: {len(valid)}, Quarantined: {len(bad)}")
