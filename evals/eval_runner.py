import json
import time
import os
import logging
import sys

# Add project root to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.router import classify_and_route
from src.llm_local import query_local

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("eval_runner")

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reports", f"report_{int(time.time())}.md")

def run_judge(query, response):
    """Uses local model to judge the quality of the response."""
    judge_prompt = f"""
### TASK: Evaluate the following AI Response.
Query: {query}
Response: {response}

### CRITERIA (Rate 1-5):
1. Accuracy: Is the answer correct?
2. Helpful: Does it address the user's intent?
3. Depth: Is it appropriately detailed for the complexity?

Return ONLY a JSON object: {{"accuracy": int, "helpfulness": int, "depth": int, "explanation": "string"}}
"""
    try:
        judge_raw = query_local(judge_prompt)
        # Attempt to parse JSON from the judge's response
        start = judge_raw.find("{")
        end = judge_raw.rfind("}") + 1
        if start != -1 and end != -1:
            return json.loads(judge_raw[start:end])
        else:
            return {"accuracy": 3, "helpfulness": 3, "depth": 3, "explanation": "Could not parse judge JSON"}
    except Exception as e:
        logger.error(f"Judge failed: {e}")
        return {"accuracy": 0, "helpfulness": 0, "depth": 0, "explanation": f"Judge Error: {e}"}

def run_evals():
    logger.info("?? Starting Hybrid Router Evaluation...")
    if not os.path.exists(DATASET_PATH):
        logger.error(f"Dataset not found at {DATASET_PATH}")
        return

    with open(DATASET_PATH, "r", encoding="utf-8-sig") as f:
        dataset = json.load(f)

    results = []
    total_latency = 0
    correct_routing = 0

    for item in dataset:
        query = item["query"]
        expected = item["expected_tier"]
        
        logger.info(f"Testing: {item['description']}...")
        
        start_time = time.time()
        # image_data is None for these text-only evals
        response, model_label = classify_and_route(query)
        latency = time.time() - start_time
        
        # Check routing accuracy
        actual_tier = "TIER_0_LOCAL"
        if "Pro" in model_label: actual_tier = "TIER_2_PRO"
        elif "Flash" in model_label: actual_tier = "TIER_1_FLASH"
        
        is_correct = (actual_tier == expected)
        if is_correct: correct_routing += 1
        
        # Run LLM-as-a-Judge
        logger.info("Grading response with AI Judge...")
        judge_scores = run_judge(query, response)
        
        results.append({
            "query": query,
            "expected": expected,
            "actual": actual_tier,
            "model": model_label,
            "latency": latency,
            "scores": judge_scores
        })
        total_latency += latency

    # Generate Report
    accuracy_pct = (correct_routing / len(dataset)) * 100
    avg_latency = total_latency / len(dataset)
    
    report_content = f"""# Hybrid Router Evaluation Report
**Date:** {time.strftime("%Y-%m-%d %H:%M:%S")}
**Overall Routing Accuracy:** {accuracy_pct:.1f}%
**Average Latency:** {avg_latency:.2f}s

## Detailed Results
| Query | Expected Tier | Actual Tier | Latency | Judge Score (Avg) |
|-------|---------------|-------------|---------|-------------------|
"""
    for r in results:
        avg_score = (r['scores'].get('accuracy', 0) + r['scores'].get('helpfulness', 0) + r['scores'].get('depth', 0)) / 3
        report_content += f"| {r['query'][:40]}... | {r['expected']} | {r['actual']} | {r['latency']:.1f}s | {avg_score:.1f}/5 |\n"

    report_content += "\n## Individual Scores\n"
    for r in results:
        report_content += f"### Query: {r['query']}\n"
        report_content += f"- **Model Used:** {r['model']}\n"
        report_content += f"- **Judge Explanation:** {r['scores'].get('explanation', 'N/A')}\n\n"

    with open(REPORT_PATH, "w") as f:
        f.write(report_content)
    
    logger.info(f"? Evaluation Complete! Report saved to {REPORT_PATH}")

if __name__ == "__main__":
    run_evals()
