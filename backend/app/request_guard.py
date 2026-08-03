"""Dependency-free request protection for local and single-instance deploys.

This is a safe baseline, not a replacement for a distributed API gateway.
It provides request IDs, body-size enforcement, a bounded in-process rate
limiter, and structured access logs until the production edge is configured.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .metrics import metrics

logger = logging.getLogger("deployguard.access")


class RequestGuardMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        rate_limit_requests: int,
        rate_limit_window_seconds: int,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window_seconds = rate_limit_window_seconds
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", "/"))
        started = time.perf_counter()
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        declared_size = 0

        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                self._record_guard_rejection(
                    method, "invalid_content_length", 400, started
                )
                await self._json_error(
                    send, request_id, 400, "invalid_content_length",
                    "Content-Length must be a valid integer",
                )
                return
            if declared_size > self.max_body_bytes:
                self._record_guard_rejection(
                    method, "request_body_too_large", 413, started
                )
                await self._json_error(
                    send, request_id, 413, "request_body_too_large",
                    "Request body exceeds the configured limit",
                )
                return

        app_receive = receive
        if method in {"POST", "PUT", "PATCH"}:
            buffered: list[Message] = []
            received_bytes = 0
            while True:
                message = await receive()
                buffered.append(message)
                if message["type"] == "http.request":
                    received_bytes += len(message.get("body", b""))
                    if received_bytes > self.max_body_bytes:
                        self._record_guard_rejection(
                            method, "request_body_too_large", 413, started
                        )
                        await self._json_error(
                            send, request_id, 413, "request_body_too_large",
                            "Request body exceeds the configured limit",
                        )
                        return
                    if not message.get("more_body", False):
                        break
                else:
                    break

            async def replay_receive() -> Message:
                if buffered:
                    return buffered.pop(0)
                return {"type": "http.request", "body": b"", "more_body": False}

            app_receive = replay_receive
        if self._is_rate_limited(scope, path, method):
            self._record_guard_rejection(
                method, "rate_limit_exceeded", 429, started
            )
            await self._json_error(
                send, request_id, 429, "rate_limit_exceeded",
                "Too many requests; retry after the configured window",
                headers={"Retry-After": str(self.rate_limit_window_seconds)},
            )
            return

        scope.setdefault("state", {})["request_id"] = request_id

        response_status = 500

        async def send_with_headers(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message.get("status", 500))
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, app_receive, send_with_headers)
        finally:
            metrics.observe_request(
                method,
                response_status,
                time.perf_counter() - started,
            )
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "method": method,
                        "path": path,
                        "request_id": request_id,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                    separators=(",", ":"),
                )
            )

    @staticmethod
    def _record_guard_rejection(
        method: str,
        reason: str,
        status_code: int,
        started: float,
    ) -> None:
        metrics.record_rejection(reason)
        metrics.observe_request(
            method,
            status_code,
            time.perf_counter() - started,
        )

    @staticmethod
    def _request_id(scope: Scope) -> str:
        supplied = dict(scope.get("headers", [])).get(b"x-request-id", b"")
        candidate = supplied.decode("ascii", errors="ignore").strip()
        if candidate and len(candidate) <= 80 and all(
            char.isalnum() or char in ".:_-" for char in candidate
        ):
            return candidate
        return str(uuid4())

    def _is_rate_limited(self, scope: Scope, path: str, method: str) -> bool:
        if method not in {"POST", "PUT", "PATCH"}:
            return False
        if path not in {
            "/api/v1/auth/development-session",
            "/api/v1/webhooks/github",
            "/api/v1/telemetry/events",
        }:
            return False
        client = scope.get("client") or ("unknown", 0)
        key = (str(client[0]), path)
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - self.rate_limit_window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.rate_limit_requests:
            return True
        bucket.append(now)
        if len(self._buckets) > 4096:
            self._buckets = defaultdict(
                deque,
                {
                    item_key: item_bucket
                    for item_key, item_bucket in self._buckets.items()
                    if item_bucket and item_bucket[-1] > cutoff
                },
            )
        return False

    async def _json_error(
        self,
        send: Send,
        request_id: str,
        status_code: int,
        code: str,
        detail: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        payload = json.dumps({"detail": detail, "code": code}, separators=(",", ":")).encode("utf-8")
        response_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
            (b"x-request-id", request_id.encode("ascii")),
            (b"x-content-type-options", b"nosniff"),
        ]
        for name, value in (headers or {}).items():
            response_headers.append((name.lower().encode("ascii"), value.encode("ascii")))
        await send({"type": "http.response.start", "status": status_code, "headers": response_headers})
        await send({"type": "http.response.body", "body": payload})
