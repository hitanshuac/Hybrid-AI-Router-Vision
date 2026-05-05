"""
Hybrid AI Router — Terminal Chat Interface
===========================================
Entry point for the application. Runs an interactive chat loop
with startup health checks and bulletproof error handling.

USAGE:
  python -m src.main

TROUBLESHOOTING:
  - Startup shows ❌ for Cloud: API key missing or internet down.
    FIX: Paste key into secrets/gemini_api_key.txt, check internet.
  - Startup shows ❌ for Local: Ollama not running.
    FIX: Open Start menu > search "Ollama" > click to launch.
  - Chat freezes: The model may be doing a cold start (~30s).
    Just wait. If it takes >2 minutes, press Ctrl+C to cancel that query.
"""

import sys
import logging
from src.config import (
    run_startup_checks,
    CLOUD_MODEL_LIGHT,
    CLOUD_MODEL_PRO,
    LOCAL_MODEL_PRIMARY,
    OLLAMA_HOST,
)
from src.router import classify_and_route

logger = logging.getLogger("main")


def print_banner(status):
    """Print startup banner with system health status."""
    # Re-read config values AFTER discovery has run
    import src.config as cfg
    
    print("\n" + "=" * 50)
    print("   🚀 HYBRID AI ROUTER — Terminal Chat")
    print("=" * 50)
    print()

    # Cloud status
    if status["api_key"] and status["cloud_models"]:
        print(f"  ☁️  Cloud  : ✅ Ready")
        print(f"       Flash : {cfg.CLOUD_MODEL_LIGHT}")
        print(f"       Pro   : {cfg.CLOUD_MODEL_PRO}")
    elif status["api_key"]:
        print(f"  ☁️  Cloud  : ⚠️  Key loaded, but model discovery failed")
    else:
        print(f"  ☁️  Cloud  : ❌ No API key (all queries → Local)")

    # Local status
    if status["ollama"]:
        print(f"  🏠 Local  : ✅ Ollama running ({cfg.LOCAL_MODEL_PRIMARY})")
    else:
        print(f"  🏠 Local  : ❌ Ollama not reachable ({cfg.OLLAMA_HOST})")

    print()

    # Warnings
    if not status["api_key"] and not status["ollama"]:
        print("  ⚠️  WARNING: NO MODELS AVAILABLE!")
        print("  You won't get any responses until you fix one of the above.")
        print()

    print("  Type 'exit' or 'quit' to stop.")
    print("  Type 'status' to re-check system health.")
    print("-" * 50)


def start_chat():
    """Main chat loop. Never crashes — handles every exception."""

    # --- Startup health checks ---
    print("\n⏳ Running startup checks...")
    status = run_startup_checks()
    print_banner(status)

    # --- Chat loop ---
    while True:
        try:
            user_input = input("\nYou: ")

            # --- Special commands ---
            if user_input.strip().lower() in ['exit', 'quit', 'q']:
                print("👋 Exiting. Goodbye!")
                break

            if user_input.strip().lower() == 'status':
                print("\n⏳ Re-checking system health...")
                status = run_startup_checks()
                print_banner(status)
                continue

            if not user_input.strip():
                continue

            # --- Route the prompt ---
            response, model_used = classify_and_route(user_input)

            print(f"\n[{model_used}]:")
            print(response)
            print("-" * 50)

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Exiting...")
            break

        except EOFError:
            # Happens when stdin is closed (Docker restart, pipe breakage)
            logger.warning("stdin closed (EOFError). Exiting gracefully.")
            break

        except Exception as e:
            # LAST RESORT — catch absolutely everything so the loop never dies
            logger.error(f"Unexpected error in chat loop: {type(e).__name__}: {e}")
            print(f"\n⚠️  An unexpected error occurred: {e}")
            print("The chat loop is still running. You can keep typing.")
            print("If this keeps happening, try restarting with: python -m src.main")


if __name__ == "__main__":
    try:
        start_chat()
    except Exception as e:
        # Absolute last resort — should never reach here
        print(f"\n💀 FATAL ERROR: {e}")
        print("The application has crashed. Please report this error.")
        print("Restarting: python -m src.main")
        sys.exit(1)
