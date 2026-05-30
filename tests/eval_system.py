"""
Hybrid AI Router - Comprehensive Evaluation Suite

Runs end-to-end integration tests on:
1. Layout Cache (Structural Hashing & Zero-Cost Bypass)
2. SRE Persistence (Async Queue & Single-Writer Actor)
3. Circuit Breaker (3-State Canary & Retry-After logic)
4. CQRS Read Layer

Usage:
  python tests/eval_system.py
"""

import os
import sys
import time
import base64
import unittest
import asyncio
from unittest.mock import patch, MagicMock

# --- Environment Mocking (MUST happen before local imports) ---
os.environ["OPENAI_API_KEY"] = "test_key"
os.environ["GEMINI_API_KEY"] = "test_key"
os.environ["PYTHONIOENCODING"] = "utf-8"

# Isolate database for tests
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

TEST_DB_DIR = os.path.join(PROJECT_ROOT, "data")
TEST_DB_PATH = os.path.join(TEST_DB_DIR, "test_pipeline_metrics.db")
os.environ["TEST_DB_PATH"] = TEST_DB_PATH

from fastapi.testclient import TestClient

import src.config
src.config.GEMINI_API_KEYS = ["test_key"]
src.config.GROQ_API_KEYS = ["test_key"]

from src.server import app, startup_event, shutdown_event
from src.circuit_breaker import is_circuit_open, record_success, record_failure, _get_circuit, RECOVERY_WINDOW_SEC, STRIKE_LIMIT
from src.layout_cache import compute_layout_hash, lookup_cached_layout
import duckdb

class TestHybridRouterSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare the test database and FastAPI TestClient."""
        for ext in ["", ".wal", ".tmp"]:
            path = TEST_DB_PATH + ext
            if os.path.exists(path):
                os.remove(path)
            
        # Re-initialize the test DB with the required tables
        from src.server import _init_metrics_db, _init_unstructured_ledger
        from src.layout_cache import init_layout_cache_table
        
        _init_metrics_db()
        _init_unstructured_ledger()
        init_layout_cache_table(TEST_DB_PATH)
            
    def test_01_layout_cache_determinism(self):
        """Verify structural hashing is deterministic and targets anchors."""
        print("\n[EVAL] Running Layout Cache Determinism Test...")
        # Create a dummy base64 invoice
        # Contains anchors: "invoice no", "total", "tax"
        text1 = "Invoice No: 12345\nDescription: Server Rack\nTotal: 500\nTax: 50"
        b64_1 = base64.b64encode(text1.encode('utf-8')).decode('utf-8')
        
        hash1 = compute_layout_hash(b64_1)
        hash2 = compute_layout_hash(b64_1)
        
        self.assertEqual(hash1, hash2, "Hashing must be deterministic")
        self.assertTrue(len(hash1) == 64, "Must be a SHA-256 hash")
        print("  ✓ Deterministic SHA-256 hashing passed.")

    @patch("src.vision_client.cascade_sync")
    def test_02_layout_cache_hit_bypass(self, mock_cascade_sync):
        """Verify the pipeline bypasses the LLM on a layout cache hit."""
        print("\n[EVAL] Running Zero-Cost Classification Bypass Test...")
        # Setup mock Cascade response for the initial MISS
        # cascade_sync returns (response_text, tier)
        mock_cascade_sync.return_value = ("INVOICE", "T1_MockProvider")

        text = "Invoice No: 999\nVendor: EvalCorp\nGrand Total: 1000\nTax: 100"
        b64_img = base64.b64encode(text.encode('utf-8')).decode('utf-8')
        
        payload = {
            "document_id": "eval-doc-001",
            "base64_image": b64_img,
            "metadata": {}
        }

        # First pass - Cache MISS
        with TestClient(app) as client:
            try:
                client.post("/api/v1/pipeline/ingest", json=payload)
            except Exception:
                pass # Ignore extraction errors, we just want the cache to populate
                
            # Wait a moment for the async writer to persist the cache to DuckDB
            time.sleep(0.5)
            
            # Force a DuckDB checkpoint so read_only=True connections see the new data
            from src.sre_persistence import force_checkpoint
            asyncio.run(force_checkpoint())
            time.sleep(0.5)
            
            # Verify it was written to DuckDB
            layout_hash = compute_layout_hash(b64_img)
            cached_type = lookup_cached_layout(TEST_DB_PATH, layout_hash)
            self.assertEqual(cached_type, "INVOICE", "Cache must store the document type")
            
            print("  ✓ Cache populated on MISS.")
            
            # Wait for the async UPDATE from the test script lookup to commit,
            # so the DuckDB index is stable for the next point lookup.
            time.sleep(1.0)
            from src.sre_persistence import force_checkpoint
            asyncio.run(force_checkpoint())
            time.sleep(0.5)

            # Reset the mock
            mock_cascade_sync.reset_mock()
            
            # Second pass - Cache HIT
            try:
                client.post("/api/v1/pipeline/ingest", json=payload)
            except Exception:
                pass
                
            # Ensure cascade_sync was NOT called for classification because of the cache hit
            # (It will be called for extraction, so call count should be 1, not 2)
            self.assertEqual(mock_cascade_sync.call_count, 1, "LLM classification must be bypassed on HIT")
            print("  ✓ LLM classification bypassed on cache HIT ($0 cost).")

    def test_03_circuit_breaker_transitions(self):
        """Verify the 3-strike Centipede Guardrail handles failures and recovery."""
        print("\n[EVAL] Running 3-Strike Centipede Guardrail Test...")
        # Reset circuit breaker for tier 3
        record_success(3)
        self.assertFalse(is_circuit_open(3))
        
        # 1. Trip the breaker (3 strikes = OPEN)
        record_failure(3, 503)
        record_failure(3, 429)
        record_failure(3, 503)
        
        self.assertTrue(is_circuit_open(3))
        print("  ✓ Circuit Breaker tripped to OPEN.")
        
        # 2. Mock time to test recovery window
        circuit = _get_circuit(3)
        circuit.last_failure = time.time() - RECOVERY_WINDOW_SEC - 1
        
        # 3. Verify auto-recovery
        self.assertFalse(is_circuit_open(3))
        print("  ✓ Cooldown expired, auto-recovered to CLOSED.")
        
        # 4. Verify success resets strikes
        record_failure(3, 503)
        record_success(3)
        circuit = _get_circuit(3)
        self.assertEqual(circuit.strikes, 0)
        print("  ✓ Success resets strike counter.")

    def test_04_cqrs_read_layer(self):
        """Verify the CQRS read layer endpoints execute without errors against the test DB."""
        print("\n[EVAL] Running CQRS Read Layer Test...")
        with TestClient(app) as client:
            response = client.get("/api/v1/pipeline/invoices")
            self.assertEqual(response.status_code, 200)
            
            response = client.get("/api/v1/pipeline/invoices/lines")
            self.assertEqual(response.status_code, 200)
            
            response = client.get("/api/v1/pipeline/anomalies/duplicates")
            self.assertEqual(response.status_code, 200)
            print("  ✓ CQRS Silver Layer endpoints are healthy.")

if __name__ == "__main__":
    unittest.main(verbosity=2)
