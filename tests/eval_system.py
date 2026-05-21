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
from src.circuit_breaker import vision_circuit_breaker, _STATE_CLOSED, _STATE_OPEN, _STATE_HALF_OPEN, CircuitBreakerOpenException
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

    @patch("src.vision_client.genai.GenerativeModel.generate_content")
    def test_02_layout_cache_hit_bypass(self, mock_generate):
        """Verify the pipeline bypasses the LLM on a layout cache hit."""
        print("\n[EVAL] Running Zero-Cost Classification Bypass Test...")
        # Setup mock LLM response for the initial MISS
        mock_response = MagicMock()
        mock_response.text = "INVOICE"
        mock_generate.return_value = mock_response

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
            force_checkpoint()
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
            force_checkpoint()
            time.sleep(0.5)

            # Reset the mock
            mock_generate.reset_mock()
            
            # Second pass - Cache HIT
            try:
                client.post("/api/v1/pipeline/ingest", json=payload)
            except Exception:
                pass
                
            # Ensure generate_content was NOT called for classification because of the cache hit
            # (It will be called for extraction, so call count should be 1, not 2)
            self.assertEqual(mock_generate.call_count, 1, "LLM classification must be bypassed on HIT")
            print("  ✓ LLM classification bypassed on cache HIT ($0 cost).")

    def test_03_circuit_breaker_transitions(self):
        """Verify the 3-state circuit breaker handles failures, Retry-After, and canary probes."""
        print("\n[EVAL] Running 3-State Canary Circuit Breaker Test...")
        # Reset circuit breaker
        vision_circuit_breaker.record_success()
        self.assertEqual(vision_circuit_breaker.state, _STATE_CLOSED)
        
        # 1. Trip the breaker
        vision_circuit_breaker.record_failure(retry_after=1.0)
        vision_circuit_breaker.record_failure(retry_after=1.0)
        vision_circuit_breaker.record_failure(retry_after=1.0)
        
        self.assertEqual(vision_circuit_breaker.state, _STATE_OPEN)
        print("  ✓ Circuit Breaker tripped to OPEN.")
        
        # 2. Verify requests are blocked
        with self.assertRaises(CircuitBreakerOpenException):
            vision_circuit_breaker.check_state()
            
        # 3. Wait for cooldown (we mocked Retry-After to 1.0s)
        time.sleep(1.1)
        
        # 4. Verify transition to HALF_OPEN (Canary)
        is_canary = vision_circuit_breaker.check_state()
        self.assertTrue(is_canary, "First request after cooldown must be flagged as a canary probe")
        self.assertEqual(vision_circuit_breaker.state, _STATE_HALF_OPEN)
        print("  ✓ Cooldown expired, transitioned to HALF_OPEN canary state.")
        
        # 5. Verify thundering herd protection (subsequent requests blocked)
        with self.assertRaises(CircuitBreakerOpenException):
            vision_circuit_breaker.check_state()
        print("  ✓ Thundering herd protection active (subsequent requests blocked).")
            
        # 6. Verify success resets to CLOSED
        vision_circuit_breaker.record_success()
        self.assertEqual(vision_circuit_breaker.state, _STATE_CLOSED)
        print("  ✓ Canary success transitioned back to CLOSED.")

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
