"""
NVIDIA NIM API bridge — already configured in this project.

Requires: NVIDIA_API_KEY in .env (already set — from NIM access).
Access many models via NVIDIA's inference platform.

Models:
  qwen/qwen3.5-122b-a10b         — large Qwen3 (primary worker)
  meta/llama-3.1-70b-instruct    — Meta Llama 70B
  meta/llama-3.1-8b-instruct     — Meta Llama 8B (fast)
  google/gemma-3-27b-it          — Google Gemma 27B
  mistralai/mistral-large-2-instruct  — Mistral Large
  nvidia/llama-3.1-nemotron-70b-instruct  — NVIDIA fine-tuned
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _client() -> OpenAI | None:
    key = os.getenv("NVIDIA_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key, base_url=_BASE_URL)


class NvidiaBridge(LLMBridge):
    provider = "nvidia-nim"
    default_model = "meta/llama-3.1-8b-instruct"
    models = [
        "qwen/qwen3.5-122b-a10b",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.1-8b-instruct",
        "google/gemma-3-27b-it",
        "mistralai/mistral-large-2-instruct",
        "nvidia/llama-3.1-nemotron-70b-instruct",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("NVIDIA_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "NVIDIA_API_KEY not set", provider=self.provider)
        model = model or self.default_model
        t0 = time.time()
        try:
            resp = c.chat.completions.create(model=model, messages=messages, timeout=90)
            text = resp.choices[0].message.content or ""
            return LLMResult(
                True, text, timing_s=round(time.time() - t0, 2),
                model=model, provider=self.provider,
            )
        except Exception as e:
            return LLMResult(False, "", str(e),
                             timing_s=round(time.time() - t0, 2), provider=self.provider)

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        c = _client()
        if c is None:
            yield "[ERROR] NVIDIA_API_KEY not set"
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
    bridge = NvidiaBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.", model="meta/llama-3.1-8b-instruct")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
