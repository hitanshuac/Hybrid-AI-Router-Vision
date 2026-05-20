"""
Circuit Breaker — SRE Rate Limit Protection.

Thread-safe, stateful circuit breaker that monitors upstream Vision LLM
(Gemini) responses. Trips OPEN after 3 consecutive 429/503 failures,
halts outbound requests for a 60-second cooldown, and triggers a
DuckDB WAL checkpoint to secure data state.

Implements: .agents/workflows/error-recovery.md
"""

import time
import asyncio
import logging
import threading

logger = logging.getLogger("circuit_breaker")

# ── Custom Exception ──────────────────────────────────────────────
class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is OPEN and cooldown has not elapsed."""
    pass


# ── Circuit Breaker States ────────────────────────────────────────
_STATE_CLOSED = "CLOSED"
_STATE_OPEN = "OPEN"

# ── Configuration ─────────────────────────────────────────────────
_FAILURE_THRESHOLD = 3
_COOLDOWN_SECONDS = 60


class CircuitBreaker:
    """
    Process-wide circuit breaker for upstream Vision LLM protection.
    Thread-safe via threading.Lock (called from worker threads via to_thread).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0
        self.state: str = _STATE_CLOSED

    def record_failure(self) -> None:
        """Increment failure counter. Trip OPEN at threshold and checkpoint DuckDB."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.warning(
                "[CIRCUIT BREAKER] Failure %d/%d recorded.",
                self.failure_count,
                _FAILURE_THRESHOLD,
            )

            if self.failure_count >= _FAILURE_THRESHOLD and self.state == _STATE_CLOSED:
                self.state = _STATE_OPEN
                logger.critical(
                    "[CIRCUIT BREAKER] TRIPPED OPEN — %d consecutive upstream failures. "
                    "Halting outbound requests for %ds cooldown.",
                    self.failure_count,
                    _COOLDOWN_SECONDS,
                )
                # Fire-and-forget checkpoint in a new thread to avoid blocking
                self._trigger_checkpoint()

    def record_success(self) -> None:
        """Reset failure count on successful upstream response."""
        with self._lock:
            if self.failure_count > 0:
                logger.info("[CIRCUIT BREAKER] Success recorded. Resetting failure count.")
            self.failure_count = 0
            self.state = _STATE_CLOSED

    def check_state(self) -> None:
        """
        Raise CircuitBreakerOpenException if OPEN and cooldown has not elapsed.
        Auto-transitions to CLOSED (half-open probe) after cooldown.
        """
        with self._lock:
            if self.state == _STATE_OPEN:
                elapsed = time.time() - self.last_failure_time
                if elapsed < _COOLDOWN_SECONDS:
                    remaining = _COOLDOWN_SECONDS - elapsed
                    raise CircuitBreakerOpenException(
                        f"Circuit Breaker OPEN. Upstream rate limit exceeded. "
                        f"Cooling down ({remaining:.0f}s remaining)."
                    )
                else:
                    # Cooldown expired — transition to CLOSED for half-open probe
                    logger.info(
                        "[CIRCUIT BREAKER] Cooldown expired. Transitioning to CLOSED for retry probe."
                    )
                    self.state = _STATE_CLOSED
                    self.failure_count = 0

    def _trigger_checkpoint(self) -> None:
        """Synchronous DuckDB checkpoint — called from within worker threads."""
        try:
            from src.sre_persistence import force_checkpoint_sync
            force_checkpoint_sync()
        except Exception as e:
            logger.error("[CIRCUIT BREAKER] Failed to trigger DuckDB checkpoint: %s", e)


# ── Singleton Instance ────────────────────────────────────────────
vision_circuit_breaker = CircuitBreaker()
