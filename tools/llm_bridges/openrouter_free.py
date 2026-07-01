"""
OpenRouter free-tier bridge — access to many models with :free suffix.

Requires: OPENROUTER_API_KEY in .env (already set in this project).
Free models have rate limits but no cost.

Models (all have :free suffix on OpenRouter, verified 2026-06):
  meta-llama/llama-3.3-70b-instruct:free    — best quality free
  meta-llama/llama-3.2-3b-instruct:free     — fast small
  qwen/qwen3-next-80b-a3b-instruct:free     — Qwen3 80B
  qwen/qwen3-coder:free                     — code specialist
  nvidia/nemotron-3-super-120b-a12b:free    — NVIDIA large
  nvidia/nemotron-3-ultra-550b-a55b:free    — NVIDIA biggest
  openai/gpt-oss-120b:free                  — OpenAI OSS 120B
  openai/gpt-oss-20b:free                   — OpenAI OSS 20B
  google/gemma-4-31b-it:free               — Google Gemma 31B
  nousresearch/hermes-3-llama-3.1-405b:free — Nous Hermes 405B
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://openrouter.ai/api/v1"
_REFERER = "https://deepfieldpro.local"
_APP_NAME = "ElieAtch/DeepFieldPro"


def _client() -> OpenAI | None:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        return None
    return OpenAI(
        api_key=key,
        base_url=_BASE_URL,
        default_headers={
            "HTTP-Referer": _REFERER,
            "X-Title": _APP_NAME,
        },
    )


class OpenRouterFreeBridge(LLMBridge):
    provider = "openrouter-free"
    # qwen3-next-80b is the same model used by openrouter_worker.py — reliably available
    default_model = "qwen/qwen3-next-80b-a3b-instruct:free"
    models = [
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "qwen/qwen3-coder:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openai/gpt-oss-120b:free",
        "openai/gpt-oss-20b:free",
        "google/gemma-4-31b-it:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("OPENROUTER_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "OPENROUTER_API_KEY not set", provider=self.provider)
        model = model or self.default_model
        t0 = time.time()
        # Try fallback models if the primary is rate-limited
        candidates = [model] + [m for m in self.models if m != model]
        last_err = ""
        for m in candidates:
            try:
                resp = c.chat.completions.create(model=m, messages=messages, timeout=90)
                text = resp.choices[0].message.content or ""
                return LLMResult(
                    True, text, timing_s=round(time.time() - t0, 2),
                    model=m, provider=self.provider,
                )
            except Exception as e:
                last_err = str(e)
                if "429" not in last_err and "rate" not in last_err.lower():
                    break  # non-rate-limit error, don't try other models
                time.sleep(1)
        return LLMResult(False, "", last_err,
                         timing_s=round(time.time() - t0, 2), provider=self.provider)

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        c = _client()
        if c is None:
            yield "[ERROR] OPENROUTER_API_KEY not set"
            return
        model = model or self.default_model
        try:
            stream = c.chat.completions.create(
                model=model, messages=messages, stream=True, timeout=120
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield f"[ERROR] {e}"


if __name__ == "__main__":
    bridge = OpenRouterFreeBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
