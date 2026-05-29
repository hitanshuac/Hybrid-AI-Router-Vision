"""
Hybrid AI Router — Provider Health Monitor
===========================================
Background task that pings each cloud provider every 5 minutes.
Exposes real-time status for the dashboard.
"""

import asyncio
import logging
import time
import requests
from dataclasses import dataclass, field
from typing import Dict

from src.config import GROQ_API_KEYS, OPENROUTER_API_KEYS, NVIDIA_API_KEYS, GEMINI_API_KEYS

logger = logging.getLogger("health")

PING_INTERVAL_SECONDS = 300  # 5 minutes


@dataclass
class ProviderStatus:
    name: str
    url: str
    status: str = "unknown"  # "up", "down", "unknown"
    latency_ms: float = 0.0
    last_checked: float = 0.0
    error: str = ""


# Global state — read by dashboard, written by background task
provider_statuses: Dict[str, ProviderStatus] = {
    "groq": ProviderStatus(name="Groq", url="https://api.groq.com/openai/v1/models"),
    "openrouter": ProviderStatus(name="OpenRouter", url="https://openrouter.ai/api/v1/models"),
    "gemini": ProviderStatus(name="Gemini Flash", url="https://generativelanguage.googleapis.com/v1beta/openai/models"),
    "nvidia": ProviderStatus(name="NVIDIA NIM", url="https://integrate.api.nvidia.com/v1/models"),
}

# Request tracking — read by dashboard, incremented by server
@dataclass
class RequestStats:
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    last_provider: str = ""
    last_latency: float = 0.0

stats = RequestStats()


def _ping_provider(provider_id: str, status: ProviderStatus, api_keys: list):
    """Ping a single provider and update its status."""
    headers = {}
    if api_keys:
        headers["Authorization"] = f"Bearer {api_keys[0]}"

    try:
        start = time.time()
        resp = requests.get(status.url, headers=headers, timeout=10)
        latency = (time.time() - start) * 1000

        if resp.status_code < 400:
            status.status = "up"
            status.latency_ms = round(latency, 1)
            status.error = ""
        else:
            status.status = "down"
            status.latency_ms = round(latency, 1)
            status.error = f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        status.status = "down"
        status.latency_ms = 0
        status.error = "Connection refused"
    except requests.exceptions.Timeout:
        status.status = "down"
        status.latency_ms = 0
        status.error = "Timeout"
    except Exception as e:
        status.status = "down"
        status.latency_ms = 0
        status.error = str(e)[:100]

    status.last_checked = time.time()


def run_health_check():
    """Run a single health check cycle against all providers."""
    logger.info("Running provider health checks...")

    _ping_provider("groq", provider_statuses["groq"], GROQ_API_KEYS)
    _ping_provider("openrouter", provider_statuses["openrouter"], OPENROUTER_API_KEYS)
    _ping_provider("gemini", provider_statuses["gemini"], GEMINI_API_KEYS)
    _ping_provider("nvidia", provider_statuses["nvidia"], NVIDIA_API_KEYS)

    for pid, ps in provider_statuses.items():
        icon = "✅" if ps.status == "up" else "❌"
        logger.info(f"  {icon} {ps.name}: {ps.status} ({ps.latency_ms}ms)")


async def health_ping_loop():
    """Background async loop that pings providers every PING_INTERVAL_SECONDS."""
    # Initial check on startup
    run_health_check()

    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        run_health_check()
