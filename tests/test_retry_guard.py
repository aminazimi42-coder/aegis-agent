import unittest

from core.retry_guard import RetryGuard


class RetryGuardTests(unittest.TestCase):
    def test_retry_guard_allows_two_retries_before_failure(self):
        guard = RetryGuard(max_retries=2)
        attempts = {"count": 0}

        def action():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("temporary failure")
            return "ok"

        result = guard.execute("task-123", action)

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 3)
        self.assertEqual(guard.snapshot("task-123")["status"], "healthy")

    def test_retry_guard_halts_after_retry_budget_is_exhausted(self):
        guard = RetryGuard(max_retries=2)

        def action():
            raise ValueError("persistent failure")

        with self.assertRaises(RuntimeError):
            guard.execute("task-456", action)

        snapshot = guard.snapshot("task-456")
        self.assertEqual(snapshot["status"], "open")
        self.assertGreaterEqual(snapshot["failures"], 2)


if __name__ == "__main__":
    unittest.main()
