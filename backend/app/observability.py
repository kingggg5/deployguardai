"""Optional OpenTelemetry tracing with bounded, non-sensitive attributes."""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from typing import Any

from opentelemetry import context as context_api, propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings


_configure_lock = Lock()
_configured_endpoint: str | None = None


def configure_tracing(settings: Settings) -> bool:
    """Configure one process-wide OTLP exporter, or retain the no-op provider."""

    global _configured_endpoint
    endpoint = settings.otel_traces_endpoint.strip()
    if not endpoint:
        return False
    with _configure_lock:
        if _configured_endpoint is not None:
            return _configured_endpoint == endpoint
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.otel_service_name,
                    "deployment.environment.name": settings.environment,
                }
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=endpoint,
                    timeout=settings.otel_export_timeout_seconds,
                )
            )
        )
        trace.set_tracer_provider(provider)
        _configured_endpoint = endpoint
    return True


def inject_trace_context(
    carrier: dict[str, str], *, context=None
) -> dict[str, str]:
    """Inject the current W3C trace context into a small job carrier."""

    propagate.inject(carrier, context=context)
    return {
        key: value
        for key, value in carrier.items()
        if key.lower() in {"traceparent", "tracestate"}
    }


def extract_trace_context(carrier: Mapping[str, Any]):
    safe_carrier = {
        str(key): str(value)
        for key, value in carrier.items()
        if str(key).lower() in {"traceparent", "tracestate"}
    }
    return propagate.extract(safe_carrier)


def attach_trace_context(carrier: Mapping[str, Any]):
    """Attach an extracted job context and return the token for detach()."""

    return context_api.attach(extract_trace_context(carrier))


def detach_trace_context(token) -> None:
    context_api.detach(token)


class OpenTelemetryMiddleware:
    """Create one server span per request without path or tenant labels."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.tracer = trace.get_tracer("deployguard.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
            if key.lower() in {b"traceparent", b"tracestate"}
        }
        context = extract_trace_context(headers)
        method = str(scope.get("method", "GET")).upper()
        status_code = 500

        async def observe_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        with self.tracer.start_as_current_span(
            "HTTP request",
            context=context,
            kind=SpanKind.SERVER,
            attributes={"http.request.method": method},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                await self.app(scope, receive, observe_status)
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
