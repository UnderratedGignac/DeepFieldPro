"""
Cohere API bridge — OpenAI-compatible v2 endpoint.

Requires: COHERE_API_KEY in .env (get free trial key at https://dashboard.cohere.com)
Free trial: 5 req/min, 1000 req/month.

Models:
  command-r-plus  — most capable, best for RAG
  command-r       — fast, efficient
  command-light   — lightweight
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://api.cohere.com/compatibility/v1"


def _client() -> OpenAI | None:
    key = os.getenv("COHERE_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key, base_url=_BASE_URL)


class CohereBridge(LLMBridge):
    provider = "cohere"
    default_model = "command-r"
    models = [
        "command-r-plus",
        "command-r",
        "command-light",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("COHERE_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "COHERE_API_KEY not set", provider=self.provider)
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
            yield "[ERROR] COHERE_API_KEY not set"
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
    bridge = CohereBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
