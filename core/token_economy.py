from __future__ import annotations

import base64
import gzip
import hashlib
import shelve
from pathlib import Path
from typing import Dict

from core.usage_meter import UsageMeterSingleton

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_DB = str(CACHE_DIR / "token_cache.db")


class TokenEconomy:
    """Lightweight token-optimization proxy: prompt compression + caching.

    This is intentionally small and dependency-free so it can run in CI and
    low-privilege environments. It records token usage via `UsageMeterSingleton`.
    """

    def __init__(self, cache_path: str = CACHE_DB) -> None:
        self.cache_path = cache_path

    def _compress_prompt(self, prompt: str) -> str:
        # Use deterministic gzip (fixed mtime) so identical prompts map to same cache key
        import io

        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
            f.write(prompt.encode("utf-8"))
        compressed = buf.getvalue()
        return base64.b64encode(compressed).decode("ascii")

    def _make_cache_key(self, tenant_id: str, model: str, compressed_prompt: str) -> str:
        digest = hashlib.sha256(f"{tenant_id}:{model}:{compressed_prompt}".encode()).hexdigest()
        return digest

    def call_model(
        self,
        tenant_id: str,
        model: str,
        prompt: str,
        token_budget: int = 1024,
    ) -> Dict[str, object]:
        """Call the model with prompt compression and simple caching.

        Returns a dict with `cached` boolean and `response` string and optional
        `tokens` used.
        """
        compressed = self._compress_prompt(prompt)
        key = self._make_cache_key(tenant_id, model, compressed)
        with shelve.open(self.cache_path) as db:
            if key in db:
                return {"cached": True, "response": db[key]}

            # Simulate a low-token optimized response and record usage.
            # In production this would proxy to the real model backend.
            tokens_used = min(max(len(prompt) // 4, 1), token_budget)
            response = f"[optimized:{model}] {prompt[:256]}"
            UsageMeterSingleton.record_usage(tenant_id, tokens_used, model, "inference")
            db[key] = response
            return {"cached": False, "response": response, "tokens": tokens_used}


# Simple module-level singleton convenience
TokenEconomySingleton = TokenEconomy()
