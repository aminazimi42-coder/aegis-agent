import time
import unittest

from core.observability import CausalSwarmObservability, SpanContext, TraceEvent


class ObservabilityTests(unittest.TestCase):
    def test_trace_span_links_and_metrics(self):
        monitor = CausalSwarmObservability()
        parent = monitor.start_span("request", "tenant-42", metadata={"route": "/tasks/dispatch"})
        child = monitor.start_span("agent", "tenant-42", parent=parent, metadata={"agent": "Alina"})
        monitor.record_event(child, "agent_response", {"status": "ok"})
        monitor.record_metric("dispatch_latency_ms", 42.5)
        monitor.record_metric("tool_calls", 3)

        trace = monitor.snapshot(parent.trace_id)
        self.assertEqual(trace["trace_id"], parent.trace_id)
        self.assertGreaterEqual(len(trace["spans"]), 2)
        self.assertGreaterEqual(len(trace["events"]), 1)
        self.assertIn("dispatch_latency_ms", trace["metrics"])

    def test_span_context_keeps_causal_links(self):
        parent = SpanContext(trace_id="trace-1", span_id="span-1")
        child = SpanContext(trace_id="trace-1", span_id="span-2", parent_span_id="span-1")
        self.assertEqual(child.trace_id, parent.trace_id)
        self.assertEqual(child.parent_span_id, parent.span_id)

    def test_trace_event_tracks_timestamp(self):
        event = TraceEvent(name="tool_execution", payload={"tool": "deploy"})
        self.assertTrue(event.timestamp > 0)
        self.assertEqual(event.payload["tool"], "deploy")

    def test_span_is_expired_after_ttl(self):
        monitor = CausalSwarmObservability(default_ttl_seconds=0)
        span = monitor.start_span("request", "tenant-42")
        time.sleep(0.05)
        self.assertTrue(monitor.is_expired(span))


if __name__ == "__main__":
    unittest.main()
