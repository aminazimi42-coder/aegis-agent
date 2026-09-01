from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional

from core.evidence_ledger import EvidenceLedgerSingleton
from core.usage_meter import UsageMeterSingleton


@dataclass
class Extension:
    name: str
    module: ModuleType
    run_callable: Callable[[Dict[str, Any]], Any]


class ExtensionRuntime:
    """Extensible runtime for loading and running user-supplied extensions.

    Features:
    - Register/unregister extensions dynamically
    - Load extensions from a directory
    - Execute an extension with a context; records evidence and usage
    - Lightweight and pluggable for future sandboxing/isolated execution
    """

    def __init__(self) -> None:
        self._extensions: Dict[str, Extension] = {}

    def register_extension(
        self,
        name: str,
        module: ModuleType,
        run_callable: Callable[[Dict[str, Any]], Any],
    ) -> None:
        self._extensions[name] = Extension(name=name, module=module, run_callable=run_callable)
        EvidenceLedgerSingleton.append_entry(
            tenant_id="system",
            actor="extension_runtime",
            action="register",
            payload={"name": name},
        )

    def unregister_extension(self, name: str) -> bool:
        if name in self._extensions:
            del self._extensions[name]
            EvidenceLedgerSingleton.append_entry(
                tenant_id="system",
                actor="extension_runtime",
                action="unregister",
                payload={"name": name},
            )
            return True
        return False

    def load_extension_from_path(self, path: str, name: Optional[str] = None) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(path)
        module_name = name or p.stem
        spec = importlib.util.spec_from_file_location(module_name, str(p))
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load module from {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        # Expect extension module to expose `run(context)` callable
        run_callable = getattr(mod, "run", None)
        if not callable(run_callable):
            raise AttributeError("extension module must define a callable `run(context)`")
        self.register_extension(module_name, mod, run_callable)
        return module_name

    def execute(self, name: str, tenant_id: str, context: Dict[str, Any]) -> Any:
        ext = self._extensions.get(name)
        if not ext:
            raise KeyError(name)
        # Record invocation in ledger and usage meter (small token cost)
        EvidenceLedgerSingleton.append_entry(
            tenant_id=tenant_id,
            actor=f"extension:{name}",
            action="invoke",
            payload={"context_keys": list(context.keys())},
        )
        UsageMeterSingleton.record_usage(tenant_id, tokens=1, model=f"extension:{name}")
        try:
            return ext.run_callable(context)
        except Exception as exc:  # record failure
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor=f"extension:{name}",
                action="error",
                payload={"error": str(exc)},
            )
            raise


ExtensionRuntimeSingleton = ExtensionRuntime()
