import json
import os
import sys
import numpy as np

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.router import semantic_router
from src.llm_local import get_embedding

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")
REGISTRY_V1 = os.path.join(os.path.dirname(__file__), "..", "prompts", "router_v1.json")
REGISTRY_V2 = os.path.join(os.path.dirname(__file__), "..", "prompts", "router_v2.json")

def calibrate():
    print("🚀 Starting Dynamic Threshold Calibration...")
    if not os.path.exists(DATASET_PATH):
        print(f"Error: Dataset not found at {DATASET_PATH}")
        return

    with open(DATASET_PATH, "r", encoding="utf-8-sig") as f:
        dataset = json.load(f)

    # Pre-calculate weights for all queries in dataset
    test_data = []
    for item in dataset:
        weights = semantic_router.calculate_weights(item["query"])
        test_data.append({
            "expected": item["expected_tier"],
            "weights": weights
        })

    best_acc = 0
    best_thresholds = {"TIER_2_PRO": 0.65, "TIER_1_FLASH": 0.60}

    # Grid search for optimal thresholds
    for pro_t in np.arange(0.3, 0.8, 0.02):
        for flash_t in np.arange(0.3, 0.8, 0.02):
            correct = 0
            for item in test_data:
                actual = "TIER_0_LOCAL"
                # Evaluate routing logic
                if item["weights"].get("TIER_2_PRO", 0) > pro_t:
                    actual = "TIER_2_PRO"
                elif item["weights"].get("TIER_1_FLASH", 0) > flash_t:
                    actual = "TIER_1_FLASH"
                
                if actual == item["expected"]:
                    correct += 1
            
            acc = correct / len(dataset)
            # We prefer higher thresholds if accuracy is the same (less cloud usage)
            if acc > best_acc:
                best_acc = acc
                best_thresholds = {"TIER_2_PRO": float(pro_t), "TIER_1_FLASH": float(flash_t)}
            elif acc == best_acc:
                if pro_t + flash_t > best_thresholds["TIER_2_PRO"] + best_thresholds["TIER_1_FLASH"]:
                    best_thresholds = {"TIER_2_PRO": float(pro_t), "TIER_1_FLASH": float(flash_t)}

    print(f"✅ Calibration Complete! Best Accuracy: {best_acc*100:.1f}%")
    print(f"📊 Optimized Thresholds: Pro={best_thresholds['TIER_2_PRO']:.2f}, Flash={best_thresholds['TIER_1_FLASH']:.2f}")

    # Save to router_v2.json (Prompt Version Control)
    if os.path.exists(REGISTRY_V1):
        with open(REGISTRY_V1, "r", encoding="utf-8-sig") as f:
            v1_data = json.load(f)
        
        v1_data["thresholds"] = best_thresholds
        
        with open(REGISTRY_V2, "w", encoding="utf-8") as f:
            json.dump(v1_data, f, indent=4)
        
        print(f"📦 Version Control: Optimized settings saved to prompts/router_v2.json")
    else:
        print("Error: router_v1.json not found.")

if __name__ == "__main__":
    calibrate()