"""
HuggingFace Inference API bridge.

Requires: HF_API_KEY in .env (get free token at https://huggingface.co/settings/tokens)
Free tier: limited daily requests on serverless inference.

Models:
  meta-llama/Llama-3.2-3B-Instruct   — small, fast
  meta-llama/Llama-3.1-8B-Instruct   — balanced
  Qwen/Qwen2.5-7B-Instruct           — strong 7B
  mistralai/Mistral-7B-Instruct-v0.3 — classic
  google/gemma-2-2b-it               — small Google model
  HuggingFaceH4/zephyr-7b-beta       — reliable free option

Uses the newer OpenAI-compatible endpoint at router.huggingface.co.
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://router.huggingface.co/hf-inference/v1"


def _client() -> OpenAI | None:
    key = os.getenv("HF_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key, base_url=_BASE_URL)


class HuggingFaceBridge(LLMBridge):
    provider = "huggingface"
    default_model = "meta-llama/Llama-3.1-8B-Instruct"
    models = [
        "meta-llama/Llama-3.2-3B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "google/gemma-2-2b-it",
        "HuggingFaceH4/zephyr-7b-beta",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("HF_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "HF_API_KEY not set", provider=self.provider)
        model = model or self.default_model
        t0 = time.time()
        try:
            resp = c.chat.completions.create(
                model=model, messages=messages, max_tokens=2048, timeout=120
            )
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
            yield "[ERROR] HF_API_KEY not set"
            return
        model = model or self.default_model
        try:
            stream = c.chat.completions.create(
                model=model, messages=messages, max_tokens=2048, stream=True, timeout=120
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield f"[ERROR] {e}"


if __name__ == "__main__":
    bridge = HuggingFaceBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
