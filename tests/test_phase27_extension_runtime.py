import unittest
from pathlib import Path

from core.extension_runtime import ExtensionRuntime, ExtensionRuntimeSingleton


class ExtensionRuntimeTests(unittest.TestCase):
    def test_register_and_execute(self):
        rt = ExtensionRuntime()

        def hello(ctx):
            return {"msg": f"hello {ctx.get('name', 'x')}"}

        rt.register_extension("hello_ext", module=__import__(__name__), run_callable=hello)
        res = rt.execute("hello_ext", "tenant27", {"name": "tester"})
        self.assertEqual(res.get("msg"), "hello tester")

    def test_load_from_path_and_execute(self):
        rt = ExtensionRuntimeSingleton
        p = Path("core/extensions/sample_extension.py").resolve()
        name = rt.load_extension_from_path(str(p))
        res = rt.execute(name, "tenant27", {"data": "payload"})
        self.assertEqual(res.get("echo"), "payload")
        self.assertEqual(res.get("tag"), "sample_extension")

    def test_execute_missing(self):
        rt = ExtensionRuntime()
        with self.assertRaises(KeyError):
            rt.execute("nope", "t", {})


if __name__ == "__main__":
    unittest.main()
