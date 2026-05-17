import sys
import logging
from src.router import classify_and_route

logger = logging.getLogger("main")

def start_chat():
    print("\n" + "=" * 50)
    print("   🚀 HYBRID AI ROUTER (Minimalist)")
    print("=" * 50)
    print("  Type 'exit' to stop.")
    
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.strip().lower() in ['exit', 'quit']:
                break
            
            response, model_used, *_ = classify_and_route(user_input)
            print(f"\n[{model_used}]:\n{response}\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    start_chat()
