"""
Groq API bridge — ultra-fast inference, generous free tier.

Requires: GROQ_API_KEY in .env (get free key at https://console.groq.com)
Free tier: 30 RPM, 6000 RPD, 6000 TPM per model.

Models:
  llama-3.3-70b-versatile  — best quality, free
  llama-3.1-8b-instant     — fastest, free
  mixtral-8x7b-32768       — long context, free
  gemma2-9b-it             — Google Gemma, free
"""

import os
import time
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE_URL = "https://api.groq.com/openai/v1"


def _client() -> OpenAI | None:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return None
    return OpenAI(api_key=key, base_url=_BASE_URL)


class GroqBridge(LLMBridge):
    provider = "groq"
    default_model = "llama-3.3-70b-versatile"
    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY", ""))

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        c = _client()
        if c is None:
            return LLMResult(False, "", "GROQ_API_KEY not set", provider=self.provider)
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
            yield "[ERROR] GROQ_API_KEY not set"
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
    bridge = GroqBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
