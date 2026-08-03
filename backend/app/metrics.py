"""Small, dependency-free Prometheus registry for process health metrics.

The registry intentionally exposes only low-cardinality dimensions. It is a
useful baseline for a single API process; production installations should
still scrape each replica through an authenticated/private network and merge
metrics in their monitoring platform.
"""

from __future__ import annotations

from collections import Counter
from threading import Lock
from time import time


_KNOWN_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD")


def _method_label(method: str) -> str:
    normalized = method.upper()
    return normalized if normalized in _KNOWN_METHODS else "OTHER"


def _status_class(status_code: int) -> str:
    if 100 <= status_code < 600:
        return f"{status_code // 100}xx"
    return "unknown"


class MetricsRegistry:
    """Thread-safe counters with a stable, intentionally small label set."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.started_at = time()
        self._requests = Counter()
        self._responses = Counter()
        self._rejections = Counter()
        self._duration_count = 0
        self._duration_sum = 0.0

    def observe_request(
        self,
        method: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        with self._lock:
            self._requests[_method_label(method)] += 1
            self._responses[_status_class(status_code)] += 1
            self._duration_count += 1
            self._duration_sum += max(0.0, duration_seconds)

    def record_rejection(self, reason: str) -> None:
        # Reasons are server-owned constants (never request input). Keep the
        # fallback to avoid accidentally introducing an unbounded label set.
        allowed = {
            "invalid_content_length",
            "request_body_too_large",
            "rate_limit_exceeded",
        }
        label = reason if reason in allowed else "other"
        with self._lock:
            self._rejections[label] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            requests = dict(self._requests)
            responses = dict(self._responses)
            rejections = dict(self._rejections)
            duration_count = self._duration_count
            duration_sum = self._duration_sum
            started_at = self.started_at

        lines = [
            "# HELP deployguard_process_start_time_seconds Unix timestamp when the process started.",
            "# TYPE deployguard_process_start_time_seconds gauge",
            f"deployguard_process_start_time_seconds {started_at:.3f}",
            "# HELP deployguard_http_requests_total HTTP requests seen by the API process.",
            "# TYPE deployguard_http_requests_total counter",
        ]
        for method in _KNOWN_METHODS + ("OTHER",):
            lines.append(
                f'deployguard_http_requests_total{{method="{method}"}} '
                f"{requests.get(method, 0)}"
            )
        lines.extend(
            [
                "# HELP deployguard_http_responses_total HTTP responses by status class.",
                "# TYPE deployguard_http_responses_total counter",
            ]
        )
        for status_class in ("1xx", "2xx", "3xx", "4xx", "5xx", "unknown"):
            lines.append(
                f'deployguard_http_responses_total{{status_class="{status_class}"}} '
                f"{responses.get(status_class, 0)}"
            )
        lines.extend(
            [
                "# HELP deployguard_http_request_duration_seconds HTTP request duration summary.",
                "# TYPE deployguard_http_request_duration_seconds summary",
                f"deployguard_http_request_duration_seconds_count {duration_count}",
                f"deployguard_http_request_duration_seconds_sum {duration_sum:.6f}",
                "# HELP deployguard_request_rejections_total Requests rejected before application handling.",
                "# TYPE deployguard_request_rejections_total counter",
            ]
        )
        for reason in (
            "invalid_content_length",
            "request_body_too_large",
            "rate_limit_exceeded",
            "other",
        ):
            lines.append(
                f'deployguard_request_rejections_total{{reason="{reason}"}} '
                f"{rejections.get(reason, 0)}"
            )
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
