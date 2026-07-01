"""
Mistral AI API bridge — OpenAI-compatible.

Requires: MISTRAL_API_KEY in .env (get free key at https://console.mistral.ai)
Free tier available (rate-limited).

Models:
  mistral-small-latest    — fast, cheap
  open-mistral-7b         — fully open, cheap
  open-mixtral-8x7b       — larger MoE model
  open-mixtral-8x22b      — biggest open model
  mistral-medium-latest   — balanced quality/price
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://api.mistral.ai/v1"


def _client() -> OpenAI | None:
    key = os.getenv("MISTRAL_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key, base_url=_BASE_URL)


class MistralBridge(LLMBridge):
    provider = "mistral"
    default_model = "mistral-small-latest"
    models = [
        "mistral-small-latest",
        "open-mistral-7b",
        "open-mixtral-8x7b",
        "open-mixtral-8x22b",
        "mistral-medium-latest",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("MISTRAL_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "MISTRAL_API_KEY not set", provider=self.provider)
        model = model or self.default_model
        t0 = time.time()
        try:
            resp = c.chat.completions.create(model=model, messages=messages, timeout=60)
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
            yield "[ERROR] MISTRAL_API_KEY not set"
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
    bridge = MistralBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
