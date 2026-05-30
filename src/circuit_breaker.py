"""
Hybrid AI Router — SRE Centipede Guardrails
=============================================
- O(1) preflight token estimation: len(prompt) // 4
- Dynamic tier skipping for payloads > 8,000 tokens
- 3-strike circuit breaker per provider (429/503)

v3.0.0 — Offsite Deployment Edition
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Set

logger = logging.getLogger("circuit_breaker")

class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is OPEN and cooldown has not elapsed."""
    pass

# ============================================================
# O(1) PRE-FLIGHT TOKEN ESTIMATOR
# ============================================================
CENTIPEDE_TOKEN_THRESHOLD = 8_000

# Tiers allowed when payload EXCEEDS 8k tokens (high-context capable)
# Tier 2 = Gemini 2.5 Flash (1M context), Tier 3 = OpenRouter/Gemma-4 (high context)
HIGH_CONTEXT_TIERS: Set[int] = {2, 3}

# All tiers (4-tier vision-only cascade)
ALL_TIERS: Set[int] = set(range(1, 5))


def estimate_tokens(prompt: str) -> int:
    """O(1) pre-flight token estimate — industry standard char/4 heuristic."""
    return len(prompt) // 4


def estimate_tokens_from_messages(messages: list) -> int:
    """O(n) over message count, O(1) per message — no tokenizer overhead."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                total += len(part.get("text", ""))
    return total // 4


def get_eligible_tiers(est_tokens: int) -> Set[int]:
    """
    If the centipede payload exceeds 8,000 tokens, skip tiers 1,2,5,7,8,9,10
    and route directly to high-context tiers (3, 4, 6).
    """
    if est_tokens > CENTIPEDE_TOKEN_THRESHOLD:
        logger.warning(
            f"[CENTIPEDE GUARDRAIL] Payload ~{est_tokens} tokens exceeds "
            f"{CENTIPEDE_TOKEN_THRESHOLD} threshold. Restricting to high-context tiers: {sorted(HIGH_CONTEXT_TIERS)}"
        )
        return HIGH_CONTEXT_TIERS.copy()
    return ALL_TIERS.copy()


# ============================================================
# 3-STRIKE CIRCUIT BREAKER (per-provider)
# ============================================================
STRIKE_LIMIT = 3
RECOVERY_WINDOW_SEC = 300  # 5 minutes before resetting strikes


@dataclass
class CircuitState:
    """Per-provider circuit breaker state."""
    strikes: int = 0
    is_open: bool = False
    last_failure: float = 0.0
    last_success: float = 0.0
    total_trips: int = 0  # lifetime counter for telemetry


# Global circuit states keyed by tier number
_circuits: Dict[int, CircuitState] = {}


def _get_circuit(tier: int) -> CircuitState:
    """Lazily initialize circuit state for a tier."""
    if tier not in _circuits:
        _circuits[tier] = CircuitState()
    return _circuits[tier]


def is_circuit_open(tier: int) -> bool:
    """
    Check if a tier's circuit breaker is OPEN (tripped).
    Auto-recovers after RECOVERY_WINDOW_SEC of cooldown.
    """
    circuit = _get_circuit(tier)

    if not circuit.is_open:
        return False

    # Check if recovery window has elapsed
    elapsed = time.time() - circuit.last_failure
    if elapsed >= RECOVERY_WINDOW_SEC:
        logger.info(
            f"[CIRCUIT BREAKER] Tier {tier} — Recovery window elapsed "
            f"({elapsed:.0f}s). Half-opening circuit."
        )
        circuit.is_open = False
        circuit.strikes = 0
        return False

    return True


def record_success(tier: int) -> None:
    """Record a successful request — resets the strike counter."""
    circuit = _get_circuit(tier)
    circuit.strikes = 0
    circuit.is_open = False
    circuit.last_success = time.time()


def record_failure(tier: int, status_code: int) -> None:
    """
    Record a failure. Only 429 (rate limit) and 503 (service unavailable)
    count as circuit-breaker strikes.
    """
    if status_code not in (429, 503):
        return

    circuit = _get_circuit(tier)
    circuit.strikes += 1
    circuit.last_failure = time.time()

    logger.warning(
        f"[CIRCUIT BREAKER] Tier {tier} — Strike {circuit.strikes}/{STRIKE_LIMIT} "
        f"(HTTP {status_code})"
    )

    if circuit.strikes >= STRIKE_LIMIT:
        circuit.is_open = True
        circuit.total_trips += 1
        logger.error(
            f"[CIRCUIT BREAKER] Tier {tier} — TRIPPED! "
            f"({circuit.total_trips} lifetime trips). "
            f"Cooling down for {RECOVERY_WINDOW_SEC}s."
        )


def get_circuit_status() -> Dict[int, dict]:
    """Return all circuit states for telemetry/dashboard consumption."""
    return {
        tier: {
            "strikes": cs.strikes,
            "is_open": cs.is_open,
            "last_failure": cs.last_failure,
            "last_success": cs.last_success,
            "total_trips": cs.total_trips,
        }
        for tier, cs in _circuits.items()
    }
