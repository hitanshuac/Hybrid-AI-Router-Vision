"""
Circuit Breaker — 3-State Canary System with Adaptive Backoff.

Monitors upstream Vision LLM (Gemini) responses and implements a
CLOSED → OPEN → HALF_OPEN state machine to prevent thundering herd
stampedes against free-tier rate limits.

Features:
  - Retry-After header parsing (respects upstream cooldown hints)
  - Exponential backoff with decorrelated random jitter (no header fallback)
  - HALF_OPEN canary gating: only 1 probe request allowed through
  - DuckDB WAL checkpoint on trip

Implements: .agents/workflows/error-recovery.md
"""

import time
import random
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
_STATE_HALF_OPEN = "HALF_OPEN"

# ── Configuration ─────────────────────────────────────────────────
_FAILURE_THRESHOLD = 3
_DEFAULT_COOLDOWN_SECONDS = 60
_BASE_BACKOFF_SECONDS = 15
_MAX_BACKOFF_SECONDS = 300  # 5-minute cap


class CircuitBreaker:
    """
    3-State Canary Circuit Breaker for upstream Vision LLM protection.

    State Machine:
      CLOSED  → (N failures)        → OPEN
      OPEN    → (cooldown expires)   → HALF_OPEN
      HALF_OPEN → (canary succeeds)  → CLOSED
      HALF_OPEN → (canary fails)     → OPEN (with increased backoff)

    Thread-safe via threading.Lock (called from worker threads via to_thread).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.failure_count: int = 0
        self.consecutive_trips: int = 0  # Tracks how many times we've tripped for backoff
        self.last_failure_time: float = 0.0
        self.cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS
        self.state: str = _STATE_CLOSED
        self._canary_in_flight: bool = False

    def record_failure(self, retry_after: float = None) -> None:
        """
        Increment failure counter. Trip OPEN at threshold and checkpoint DuckDB.

        Args:
            retry_after: Optional cooldown hint from upstream Retry-After header.
                         If provided, overrides the computed backoff duration.
        """
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.warning(
                "[CIRCUIT BREAKER] Failure %d/%d recorded.",
                self.failure_count,
                _FAILURE_THRESHOLD,
            )

            # If we were in HALF_OPEN and the canary failed, go straight back to OPEN
            if self.state == _STATE_HALF_OPEN:
                self._canary_in_flight = False
                self.consecutive_trips += 1
                self.cooldown_seconds = self._compute_cooldown(retry_after)
                self.state = _STATE_OPEN
                logger.critical(
                    "[CIRCUIT BREAKER] Canary probe FAILED. Re-tripping OPEN with %ds backoff.",
                    int(self.cooldown_seconds),
                )
                self._trigger_checkpoint()
                return

            if self.failure_count >= _FAILURE_THRESHOLD and self.state == _STATE_CLOSED:
                self.consecutive_trips += 1
                self.cooldown_seconds = self._compute_cooldown(retry_after)
                self.state = _STATE_OPEN
                logger.critical(
                    "[CIRCUIT BREAKER] TRIPPED OPEN — %d consecutive upstream failures. "
                    "Halting outbound requests for %ds cooldown.",
                    self.failure_count,
                    int(self.cooldown_seconds),
                )
                self._trigger_checkpoint()

    def record_success(self) -> None:
        """Reset failure count and consecutive trips on successful upstream response."""
        with self._lock:
            was_canary = self.state == _STATE_HALF_OPEN
            if self.failure_count > 0 or was_canary:
                logger.info(
                    "[CIRCUIT BREAKER] %s. Resetting to CLOSED.",
                    "Canary probe SUCCEEDED" if was_canary else "Success recorded",
                )
            self.failure_count = 0
            self.consecutive_trips = 0
            self.cooldown_seconds = _DEFAULT_COOLDOWN_SECONDS
            self.state = _STATE_CLOSED
            self._canary_in_flight = False

    def check_state(self) -> bool:
        """
        Gate check before making an upstream request.

        Returns:
            True  — this is a canary probe (HALF_OPEN). Caller should proceed
                    with caution and report result.
            False — normal operation (CLOSED). Caller proceeds normally.

        Raises:
            CircuitBreakerOpenException — if OPEN and cooldown has not elapsed.
        """
        with self._lock:
            if self.state == _STATE_CLOSED:
                return False

            if self.state == _STATE_HALF_OPEN:
                if self._canary_in_flight:
                    # Another canary is already testing — block this request
                    raise CircuitBreakerOpenException(
                        "Circuit Breaker HALF_OPEN. Canary probe in flight. "
                        "Waiting for probe result."
                    )
                # Allow exactly one canary request through
                self._canary_in_flight = True
                logger.info("[CIRCUIT BREAKER] HALF_OPEN — releasing single canary probe.")
                return True

            if self.state == _STATE_OPEN:
                elapsed = time.time() - self.last_failure_time
                if elapsed < self.cooldown_seconds:
                    remaining = self.cooldown_seconds - elapsed
                    raise CircuitBreakerOpenException(
                        f"Circuit Breaker OPEN. Upstream rate limit exceeded. "
                        f"Cooling down ({remaining:.0f}s remaining)."
                    )
                else:
                    # Cooldown expired — transition to HALF_OPEN for canary probe
                    self.state = _STATE_HALF_OPEN
                    self._canary_in_flight = True
                    self.failure_count = 0
                    logger.info(
                        "[CIRCUIT BREAKER] Cooldown expired. Transitioning to HALF_OPEN. "
                        "Releasing single canary probe."
                    )
                    return True

        return False

    def _compute_cooldown(self, retry_after: float = None) -> float:
        """
        Compute the cooldown duration.

        Priority:
          1. Upstream Retry-After header (if provided and valid)
          2. Exponential backoff with decorrelated random jitter

        Backoff formula: min(MAX, base * 2^trips + random(0, base))
        """
        if retry_after is not None and retry_after > 0:
            capped = min(retry_after, _MAX_BACKOFF_SECONDS)
            logger.info("[CIRCUIT BREAKER] Using upstream Retry-After: %ds", int(capped))
            return capped

        # Exponential backoff with decorrelated jitter
        exponential = _BASE_BACKOFF_SECONDS * (2 ** self.consecutive_trips)
        jitter = random.uniform(0, _BASE_BACKOFF_SECONDS)
        computed = min(exponential + jitter, _MAX_BACKOFF_SECONDS)
        logger.info(
            "[CIRCUIT BREAKER] Computed backoff: %ds (attempt %d, jitter %.1fs)",
            int(computed),
            self.consecutive_trips,
            jitter,
        )
        return computed

    def _trigger_checkpoint(self) -> None:
        """Synchronous DuckDB checkpoint — called from within worker threads."""
        try:
            from src.sre_persistence import force_checkpoint_sync
            force_checkpoint_sync()
        except Exception as e:
            logger.error("[CIRCUIT BREAKER] Failed to trigger DuckDB checkpoint: %s", e)


# ── Singleton Instance ────────────────────────────────────────────
vision_circuit_breaker = CircuitBreaker()
