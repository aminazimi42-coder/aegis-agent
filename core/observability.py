from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpanContext:
    """Represents causal trace linkage across request, agent, tool, and validation spans."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    kind: str = "span"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceEvent:
    """A traced event captured within a span."""

    name: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class CausalSwarmObservability:
    """Track causal execution traces across multi-agent orchestration and tools."""

    def __init__(self, default_ttl_seconds: int = 3600) -> None:
        self.default_ttl_seconds = max(0, int(default_ttl_seconds))
        self._spans: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[TraceEvent]] = {}
        self._metrics: dict[str, list[float]] = {}
        self._trace_index: dict[str, list[str]] = {}

    def _now(self) -> float:
        return time.time()

    def _make_span_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _make_trace_id(self) -> str:
        return uuid.uuid4().hex[:24]

    def _span_record(self, span: SpanContext, tenant_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        record = {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "kind": span.kind,
            "tenant_id": tenant_id,
            "metadata": dict(metadata or {}),
            "started_at": self._now(),
            "expires_at": self._now() + self.default_ttl_seconds,
        }
        self._spans[span.span_id] = record
        self._trace_index.setdefault(span.trace_id, []).append(span.span_id)
        return record

    def start_span(
        self,
        kind: str,
        tenant_id: str,
        *,
        parent: SpanContext | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SpanContext:
        trace_id = parent.trace_id if parent else self._make_trace_id()
        span_id = self._make_span_id()
        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent.span_id if parent else None,
            kind=kind,
            metadata=dict(metadata or {}),
        )
        self._span_record(span, tenant_id, metadata or {})
        return span

    def record_event(self, span: SpanContext, name: str, payload: dict[str, Any] | None = None) -> TraceEvent:
        event = TraceEvent(name=name, payload=dict(payload or {}))
        self._events.setdefault(span.span_id, []).append(event)
        return event

    def record_metric(self, name: str, value: float | int, *, unit: str | None = None) -> dict[str, Any]:
        metric_entry = {"name": name, "value": float(value), "unit": unit or "count", "timestamp": self._now()}
        self._metrics.setdefault(name, []).append(float(value))
        return metric_entry

    def is_expired(self, span: SpanContext) -> bool:
        record = self._spans.get(span.span_id)
        if record is None:
            return True
        return record["expires_at"] <= self._now()

    def snapshot(self, trace_id: str) -> dict[str, Any]:
        spans = [
            {
                "trace_id": record["trace_id"],
                "span_id": record["span_id"],
                "parent_span_id": record["parent_span_id"],
                "kind": record["kind"],
                "tenant_id": record["tenant_id"],
                "metadata": record["metadata"],
                "started_at": record["started_at"],
            }
            for record in self._spans.values()
            if record["trace_id"] == trace_id
        ]
        events = [
            {"span_id": span_id, "events": [event.__dict__ for event in event_list]}
            for span_id, event_list in self._events.items()
            if span_id in self._trace_index.get(trace_id, [])
        ]
        metrics = {name: values[:] for name, values in self._metrics.items()}
        return {
            "trace_id": trace_id,
            "spans": spans,
            "events": [event for group in events for event in group["events"]],
            "metrics": metrics,
        }

    def trace_request(self, *, tenant_id: str, kind: str = "request", metadata: dict[str, Any] | None = None) -> SpanContext:
        return self.start_span(kind, tenant_id, metadata=metadata)


Observability = CausalSwarmObservability
