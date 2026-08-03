from opentelemetry import trace
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    set_span_in_context,
)

from app.observability import extract_trace_context, inject_trace_context


def test_w3c_trace_context_round_trips_without_unrelated_payload_fields() -> None:
    span_context = SpanContext(
        trace_id=int("1234567890abcdef1234567890abcdef", 16),
        span_id=int("1234567890abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    context = set_span_in_context(NonRecordingSpan(span_context))

    carrier = inject_trace_context(
        {"workspace_id": "must-not-propagate"},
        context=context,
    )

    assert carrier == {
        "traceparent": (
            "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
        )
    }
    extracted = trace.get_current_span(
        extract_trace_context(carrier)
    ).get_span_context()
    assert extracted.trace_id == span_context.trace_id
    assert extracted.span_id == span_context.span_id
    assert extracted.is_remote is True
