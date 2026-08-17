"""
Alibaba Model Studio / DashScope international bridge.

Endpoint: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
Requires: DASHSCOPE_API_KEY in .env (workspace key from console.alibabacloud.com/model-studio)

Free-tier note: the account starts with "use free tier only" enabled.
To unlock paid models, go to the Model Studio console and disable that setting.
Until then, quota-exhausted models return AllocationQuota.FreeTierOnly and this
bridge automatically falls back through the flash → 35b → turbo chain.

Models (text, non-realtime):
  qwen3.5-flash          — fast, free tier first — default
  qwen3.5-35b-a3b        — mid-size MoE, good quality/cost
  qwen3.5-122b-a10b      — same model as NVIDIA NIM worker (large)
  qwen3-235b-a22b        — largest Qwen3 (paid)
  qwen3-coder-plus       — code specialist
  qwen3.7-max            — newest flagship
  qwen-max               — stable production alias
  deepseek-v3.2          — also available on this endpoint
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# Ordered fallback chain when a model hits its free-tier quota
_FALLBACK_CHAIN = [
    "qwen3.5-flash",
    "qwen3.5-35b-a3b",
    "qwen3-30b-a3b",
    "qwen3.5-122b-a10b",
]

_QUOTA_CODES = {"AllocationQuota.FreeTierOnly", "Arrearage", "QuotaExceeded"}


def _client() -> OpenAI | None:
    key = os.getenv("DASHSCOPE_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key, base_url=_BASE_URL)


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc)
    return any(c in msg for c in _QUOTA_CODES)


class DashScopeBridge(LLMBridge):
    provider = "dashscope-intl"
    default_model = "qwen3.5-flash"
    models = [
        "qwen3.5-flash",
        "qwen3.5-35b-a3b",
        "qwen3.5-122b-a10b",
        "qwen3.5-397b-a17b",
        "qwen3-235b-a22b",
        "qwen3-coder-plus",
        "qwen3-coder-next",
        "qwen3.7-max",
        "qwen3.7-plus",
        "qwen-max",
        "qwen-plus",
        "qwq-plus",
        "deepseek-v3.2",
        "deepseek-v4-flash",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("DASHSCOPE_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "DASHSCOPE_API_KEY not set", provider=self.provider)
        candidates = [model or self.default_model]
        # If requested model isn't already in the fallback chain, append it
        for fb in _FALLBACK_CHAIN:
            if fb not in candidates:
                candidates.append(fb)

        t0 = time.time()
        last_err = ""
        for m in candidates:
            try:
                resp = c.chat.completions.create(model=m, messages=messages, timeout=90)
                text = resp.choices[0].message.content or ""
                return LLMResult(
                    True, text,
                    timing_s=round(time.time() - t0, 2),
                    model=m, provider=self.provider,
                )
            except Exception as e:
                last_err = str(e)
                if _is_quota_error(e):
                    continue  # try next model in fallback chain
                break  # non-quota error — stop trying
        return LLMResult(False, "", last_err,
                         timing_s=round(time.time() - t0, 2), provider=self.provider)

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        c = _client()
        if c is None:
            yield "[ERROR] DASHSCOPE_API_KEY not set"
            return
        m = model or self.default_model
        try:
            stream = c.chat.completions.create(
                model=m, messages=messages, stream=True, timeout=120
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield f"[ERROR] {e}"


if __name__ == "__main__":
    bridge = DashScopeBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  model={r.model}  time={r.timing_s}s\n{r.text}")
