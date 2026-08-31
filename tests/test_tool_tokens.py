import time
import unittest

from core.tool_tokens import ToolTokenManager


class ToolTokenManagerTests(unittest.TestCase):
    def test_issue_and_validate_token(self):
        manager = ToolTokenManager(ttl_seconds=300)
        token = manager.issue_token(
            tenant_id="tenant-42",
            task_id="task-100",
            tool_name="deploy",
            capabilities=["deploy", "read"],
        )

        validated = manager.validate_token(
            token,
            tool_name="deploy",
            required_capabilities=["deploy"],
            tenant_id="tenant-42",
            task_id="task-100",
        )

        self.assertEqual(validated.tenant_id, "tenant-42")
        self.assertEqual(validated.tool_name, "deploy")
        self.assertIn("deploy", validated.capabilities)

    def test_token_rejects_missing_capability(self):
        manager = ToolTokenManager(ttl_seconds=300)
        token = manager.issue_token(
            tenant_id="tenant-42",
            task_id="task-100",
            tool_name="deploy",
            capabilities=["read"],
        )

        with self.assertRaises(PermissionError):
            manager.validate_token(
                token,
                tool_name="deploy",
                required_capabilities=["deploy"],
                tenant_id="tenant-42",
                task_id="task-100",
            )

    def test_token_rejects_expired_access(self):
        manager = ToolTokenManager(ttl_seconds=0)
        token = manager.issue_token(
            tenant_id="tenant-42",
            task_id="task-100",
            tool_name="deploy",
            capabilities=["deploy"],
        )

        time.sleep(0.05)
        with self.assertRaises(PermissionError):
            manager.validate_token(
                token,
                tool_name="deploy",
                required_capabilities=["deploy"],
                tenant_id="tenant-42",
                task_id="task-100",
            )

    def test_token_rejects_cross_tenant_use(self):
        manager = ToolTokenManager(ttl_seconds=300)
        token = manager.issue_token(
            tenant_id="tenant-1",
            task_id="task-100",
            tool_name="deploy",
            capabilities=["deploy"],
        )

        with self.assertRaises(PermissionError):
            manager.validate_token(
                token,
                tool_name="deploy",
                required_capabilities=["deploy"],
                tenant_id="tenant-2",
                task_id="task-100",
            )


if __name__ == "__main__":
    unittest.main()
