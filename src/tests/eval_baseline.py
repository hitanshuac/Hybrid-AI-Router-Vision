"""
Hybrid AI Router - Baseline Performance Evaluation Suite
=========================================================
Runs Context Overflow and Failover tests against the active router,
measuring latency and success rates, logging results to a flat JSON file.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime

# Add workspace root to sys.path to allow clean imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT_DIR)

# Configure quiet logging to avoid stdout clutter
logging.basicConfig(level=logging.WARNING)

from src.router import classify_and_route
import src.llm_cloud
import requests

# Enable ANSI escape sequences on Windows
if os.name == 'nt':
    os.system('')

# Colors for premium CLI reporting
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_MAGENTA = "\033[95m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

def print_header(title):
    print(f"\n{C_CYAN}{C_BOLD}{'='*70}{C_RESET}")
    print(f"{C_CYAN}{C_BOLD} 🚀 {title}{C_RESET}")
    print(f"{C_CYAN}{C_BOLD}{'='*70}{C_RESET}\n")

def make_mock_post(scenario):
    """
    Creates a mock requests.post function to simulate various failure and latency scenarios.
    """
    def mock_post(url, headers=None, json_data=None, json=None, timeout=None):
        # Handle both json and json_data arguments
        payload = json or json_data
        
        class MockResponse:
            def __init__(self, status_code, data):
                self.status_code = status_code
                self.data = data
            def json(self):
                return self.data

        url_str = str(url)
        
        # 1. GROQ
        if "api.groq.com" in url_str:
            if scenario in ["groq_fail", "groq_openrouter_fail", "groq_or_nv_fail", "all_cloud_fail", "total_failure"]:
                # Simulate 429 Rate Limit
                time.sleep(0.1) # small simulated network delay
                return MockResponse(429, {"error": "Rate limit exceeded (Simulated)"})
            else:
                return MockResponse(200, {
                    "choices": [{"message": {"content": "Groq successful response (Simulated)"}}]
                })
        
        # 2. OpenRouter
        elif "openrouter.ai" in url_str:
            if scenario in ["groq_openrouter_fail", "groq_or_nv_fail", "all_cloud_fail", "total_failure"]:
                # Simulate 500 Internal Server Error
                time.sleep(0.1)
                return MockResponse(500, {"error": "Internal Server Error (Simulated)"})
            else:
                return MockResponse(200, {
                    "choices": [{"message": {"content": "OpenRouter successful response (Simulated)"}}]
                })
                
        # 3. NVIDIA NIM
        elif "integrate.api.nvidia.com" in url_str:
            if scenario in ["groq_or_nv_fail", "all_cloud_fail", "total_failure"]:
                # Simulate 504 Gateway Timeout
                time.sleep(0.2)
                return MockResponse(504, {"error": "Gateway Timeout (Simulated)"})
            else:
                return MockResponse(200, {
                    "choices": [{"message": {"content": "NVIDIA NIM successful response (Simulated)"}}]
                })
                
        # 4. GEMINI FLASH
        elif "generativelanguage.googleapis.com" in url_str:
            if scenario in ["all_cloud_fail", "total_failure"]:
                time.sleep(0.2)
                return MockResponse(500, {"error": "Internal Server Error (Simulated)"})
            else:
                return MockResponse(200, {
                    "choices": [{"message": {"content": "Gemini Flash successful response (Simulated)"}}]
                })
                
        # 5. Ollama (Local)
        elif "api/chat" in url_str or "11434" in url_str:
            if scenario in ["total_failure"]:
                # Simulate Offline / Connection Error
                raise requests.exceptions.ConnectionError("Connection refused (Simulated)")
            else:
                return MockResponse(200, {
                    "message": {"content": "Ollama local GPU successful response (Simulated)"}
                })
        
        # Default fallback
        return MockResponse(200, {
            "choices": [{"message": {"content": "Default mock response"}}]
        })
        
    return mock_post

def run_context_overflow_tests():
    """
    Runs Context Overflow tests against the active router with actual API keys/Ollama.
    """
    print(f"{C_BOLD}{C_BLUE}[1/2] RUNNING CONTEXT OVERFLOW TESTS (LIVE RUN){C_RESET}")
    print(f"{'-'*70}")
    
    # Define sizes to evaluate
    sizes = [
        {"name": "Baseline (100 chars)", "len": 100},
        {"name": "Medium Prompt (4,000 chars)", "len": 4000},
        {"name": "Large Prompt (16,000 chars)", "len": 16000},
        {"name": "Massive Prompt (65,000 chars)", "len": 65000}
    ]
    
    results = []
    
    for size in sizes:
        print(f"👉 Testing {C_BOLD}{size['name']}{C_RESET}...", end="", flush=True)
        
        # Generate payload
        prefix = f"Summarize this text in 5 words:\n"
        prompt = prefix + ("A" * (size["len"] - len(prefix)))
        
        start_time = time.time()
        try:
            response, tier, *_ = classify_and_route(prompt)
            elapsed = time.time() - start_time
            success = tier != "ERROR"
            
            status_color = C_GREEN if success else C_RED
            status_text = "SUCCESS" if success else "FAILED"
            print(f" {status_color}{status_text}{C_RESET} in {elapsed:.2f}s (Resolved by: {C_BOLD}{tier}{C_RESET})")
            
            results.append({
                "test_name": size["name"],
                "prompt_length_chars": size["len"],
                "success": success,
                "latency_sec": round(elapsed, 4),
                "resolved_tier": tier,
                "response_snippet": response[:100] + "..." if response else "",
                "error": None if success else response
            })
        except Exception as e:
            elapsed = time.time() - start_time
            print(f" {C_RED}CRASHED{C_RESET} in {elapsed:.2f}s: {e}")
            results.append({
                "test_name": size["name"],
                "prompt_length_chars": size["len"],
                "success": False,
                "latency_sec": round(elapsed, 4),
                "resolved_tier": "CRASH",
                "response_snippet": "",
                "error": str(e)
            })
            
    print(f"{'-'*70}\n")
    return results

def run_failover_tests():
    """
    Runs failover simulations by monkeypatching requests.post to verify the cascade waterfall.
    """
    print(f"{C_BOLD}{C_BLUE}[2/2] RUNNING FAILOVER SIMULATION TESTS (MONKEYPATCHED){C_RESET}")
    print(f"{'-'*70}")
    
    scenarios = [
        {
            "name": "Groq Outage -> OpenRouter handles",
            "scenario_id": "groq_fail",
            "expected_tier": "CLOUD_CASCADE"
        },
        {
            "name": "Groq + OpenRouter Outage -> NVIDIA NIM handles",
            "scenario_id": "groq_openrouter_fail",
            "expected_tier": "CLOUD_CASCADE"
        },
        {
            "name": "Groq + OR + NV Outage -> Gemini Flash handles",
            "scenario_id": "groq_or_nv_fail",
            "expected_tier": "CLOUD_CASCADE"
        },
        {
            "name": "All Cloud Outages -> Local Ollama handles",
            "scenario_id": "all_cloud_fail",
            "expected_tier": "CLOUD_CASCADE" # Note: in current query_cloud, ollama returns content directly, router labels CLOUD_CASCADE or error
        },
        {
            "name": "Total Outage (Cloud + Local) -> Graceful Error",
            "scenario_id": "total_failure",
            "expected_tier": "ERROR"
        }
    ]
    
    # Save original functions & keys
    orig_post = requests.post
    orig_groq = list(src.llm_cloud.GROQ_API_KEYS)
    orig_openrouter = list(src.llm_cloud.OPENROUTER_API_KEYS)
    orig_nvidia = list(src.llm_cloud.NVIDIA_API_KEYS)
    orig_gemini = list(src.llm_cloud.GEMINI_API_KEYS)
    
    # Force mock keys so that all cascade tiers are processed in testing
    src.llm_cloud.GROQ_API_KEYS = ["mock_groq_key"]
    src.llm_cloud.OPENROUTER_API_KEYS = ["mock_openrouter_key"]
    src.llm_cloud.NVIDIA_API_KEYS = ["mock_nvidia_key"]
    src.llm_cloud.GEMINI_API_KEYS = ["mock_gemini_key"]
    
    results = []
    
    for s in scenarios:
        print(f"👉 Testing {C_BOLD}{s['name']}{C_RESET}...", end="", flush=True)
        
        # Monkeypatch requests.post
        requests.post = make_mock_post(s["scenario_id"])
        
        start_time = time.time()
        try:
            prompt = "Simulated request prompt."
            response, tier, *_ = classify_and_route(prompt)
            elapsed = time.time() - start_time
            
            # A test is successful if the tier matches our expected outcome
            success = tier == s["expected_tier"]
            
            status_color = C_GREEN if success else C_RED
            status_text = "PASS" if success else "FAIL"
            
            print(f" {status_color}{status_text}{C_RESET} in {elapsed:.2f}s (Resolved by: {C_BOLD}{tier}{C_RESET})")
            
            results.append({
                "test_name": s["name"],
                "scenario": s["scenario_id"],
                "success": success,
                "latency_sec": round(elapsed, 4),
                "resolved_tier": tier,
                "response_snippet": response[:100] + "..." if response else "",
                "error": None if success else f"Unexpected resolving tier: expected {s['expected_tier']}, got {tier}"
            })
            
        except Exception as e:
            elapsed = time.time() - start_time
            print(f" {C_RED}CRASHED{C_RESET} in {elapsed:.2f}s: {e}")
            results.append({
                "test_name": s["name"],
                "scenario": s["scenario_id"],
                "success": False,
                "latency_sec": round(elapsed, 4),
                "resolved_tier": "CRASH",
                "response_snippet": "",
                "error": str(e)
            })
            
    # Restore original functions & keys
    requests.post = orig_post
    src.llm_cloud.GROQ_API_KEYS = orig_groq
    src.llm_cloud.OPENROUTER_API_KEYS = orig_openrouter
    src.llm_cloud.NVIDIA_API_KEYS = orig_nvidia
    src.llm_cloud.GEMINI_API_KEYS = orig_gemini
    
    print(f"{'-'*70}\n")
    return results

def main():
    print_header("Hybrid AI Router - Baseline Performance Evaluator")
    
    start_time = datetime.now()
    
    # 1. Run Context Overflow Tests (Live)
    context_overflow_results = run_context_overflow_tests()
    
    # 2. Run Failover Tests (Mocked)
    failover_results = run_failover_tests()
    
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()
    
    # Calculate statistics
    all_results = context_overflow_results + failover_results
    total_tests = len(all_results)
    successful_tests = sum(1 for r in all_results if r["success"])
    failed_tests = total_tests - successful_tests
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    avg_latency = sum(r["latency_sec"] for r in all_results) / total_tests if total_tests > 0 else 0
    
    # Structure output JSON
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate_pct": round(success_rate, 2),
            "average_latency_sec": round(avg_latency, 4),
            "total_duration_sec": round(total_duration, 2)
        },
        "context_overflow_tests": context_overflow_results,
        "failover_tests": failover_results
    }
    
    # Write to flat data file
    data_dir = os.path.join(ROOT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    output_file = os.path.join(data_dir, "eval_baseline_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
        
    # Print high-fidelity report
    print_header("Evaluation Results Summary")
    print(f"{C_BOLD}📁 Results saved to:{C_RESET} [eval_baseline_results.json](file:///{output_file.replace(os.sep, '/')})")
    print(f"{C_BOLD}⏱️  Total Duration:{C_RESET} {total_duration:.2f} seconds")
    print(f"{C_BOLD}📈 Success Rate:{C_RESET} {C_GREEN if success_rate == 100 else C_YELLOW}{success_rate:.1f}%{C_RESET} ({successful_tests}/{total_tests} passed)")
    print(f"{C_BOLD}⚡ Average Latency:{C_RESET} {avg_latency:.3f}s")
    
    # Beautiful table overview
    print(f"\n{C_BOLD}{'Test Name':<45} | {'Status':<8} | {'Latency':<8} | {'Resolved Tier':<15}{C_RESET}")
    print(f"{'='*82}")
    
    for r in all_results:
        status_str = f"{C_GREEN}PASS{C_RESET}" if r["success"] else f"{C_RED}FAIL{C_RESET}"
        name = r["test_name"]
        if len(name) > 42:
            name = name[:39] + "..."
        print(f"{name:<45} | {status_str:<17} | {r['latency_sec']:>7.3f}s | {r['resolved_tier']:<15}")
        
    print(f"{'='*82}\n")

if __name__ == "__main__":
    main()
