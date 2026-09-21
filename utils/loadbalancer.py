"""
Health-Aware Round-Robin Load Balancer with Circuit Breaker.

Distributes API requests across multiple endpoints, tracks health,
and auto-disables failing APIs until they recover.
"""
import time
import logging
import asyncio

log = logging.getLogger(__name__)


class APIEndpoint:
    """Tracks one API endpoint's health and performance."""

    __slots__ = (
        "name", "template", "healthy",
        "success_count", "failure_count", "consecutive_fails",
        "total_latency_ms", "request_count",
        "circuit_open_until",
    )

    def __init__(self, name: str, template: str):
        self.name = name
        self.template = template
        self.healthy = True
        self.success_count = 0
        self.failure_count = 0
        self.consecutive_fails = 0
        self.total_latency_ms = 0
        self.request_count = 0
        self.circuit_open_until = 0.0

    @property
    def avg_latency_ms(self) -> int:
        if self.request_count == 0:
            return 0
        return self.total_latency_ms // self.request_count

    @property
    def success_rate(self) -> float:
        if self.request_count == 0:
            return 100.0
        return (self.success_count / self.request_count) * 100

    def is_circuit_open(self) -> bool:
        return time.monotonic() < self.circuit_open_until

    def circuit_remaining(self) -> int:
        """Seconds left before circuit closes."""
        left = self.circuit_open_until - time.monotonic()
        return max(0, int(left))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "healthy": self.healthy and not self.is_circuit_open(),
            "success": self.success_count,
            "failure": self.failure_count,
            "total": self.request_count,
            "success_rate": f"{self.success_rate:.1f}%",
            "avg_latency_ms": self.avg_latency_ms,
            "circuit_open": self.is_circuit_open(),
            "circuit_remaining_s": self.circuit_remaining(),
        }


class LoadBalancer:
    """
    Health-Aware Round-Robin with Circuit Breaker.

    - Alternates requests across endpoints (round-robin).
    - Tracks success/failure per endpoint.
    - After N consecutive failures, opens circuit for M seconds.
    - Auto-recovers when cooldown expires.
    """

    CIRCUIT_THRESHOLD = 5      # consecutive failures before opening
    CIRCUIT_COOLDOWN = 120     # seconds to wait before retry

    def __init__(self, endpoints: list[APIEndpoint]):
        self.endpoints = endpoints
        self._index = 0

    def next(self) -> APIEndpoint | None:
        """Return next healthy endpoint, or None if all circuits are open."""
        if not self.endpoints:
            return None
        for _ in range(len(self.endpoints)):
            ep = self.endpoints[self._index % len(self.endpoints)]
            self._index += 1
            if ep.healthy and not ep.is_circuit_open():
                return ep
        return None

    def report_success(self, ep: APIEndpoint, latency_ms: int):
        """Record a successful request."""
        ep.success_count += 1
        ep.consecutive_fails = 0
        ep.total_latency_ms += latency_ms
        ep.request_count += 1

    def report_failure(self, ep: APIEndpoint):
        """Record a failed request. Open circuit if threshold reached."""
        ep.failure_count += 1
        ep.consecutive_fails += 1
        ep.request_count += 1
        if ep.consecutive_fails >= self.CIRCUIT_THRESHOLD:
            ep.circuit_open_until = time.monotonic() + self.CIRCUIT_COOLDOWN
            log.warning(
                f"[LB] Circuit OPENED for {ep.name} — "
                f"{ep.consecutive_fails} consecutive fails, "
                f"retry in {self.CIRCUIT_COOLDOWN}s"
            )

    def stats(self) -> list[dict]:
        """Return per-endpoint stats for /apihealth."""
        return [ep.to_dict() for ep in self.endpoints]

    def active_count(self) -> int:
        """Number of endpoints currently available (circuit closed)."""
        return sum(1 for ep in self.endpoints if ep.healthy and not ep.is_circuit_open())


# --- Singleton (initialized on first import via build_balancer) ---

_balancer: LoadBalancer | None = None


def build_balancer(endpoints_cfg: list[dict]) -> LoadBalancer:
    """
    Build the global balancer from config.API_ENDPOINTS.

    Each entry: {"name": str, "url": str, "token": str}
    """
    global _balancer
    eps = []
    for ep_cfg in endpoints_cfg:
        name = ep_cfg.get("name", f"api{len(eps)+1}")
        url = ep_cfg["url"].rstrip("/")
        token = ep_cfg.get("token", "")
        if token:
            template = f"{url}?authkey={token}&url={{url}}"
        else:
            template = f"{url}?url={{url}}"
        eps.append(APIEndpoint(name, template))
    _balancer = LoadBalancer(eps)
    log.info(f"[LB] Initialized with {len(eps)} endpoints: {[e.name for e in eps]}")
    return _balancer


def get_balancer() -> LoadBalancer | None:
    return _balancer
