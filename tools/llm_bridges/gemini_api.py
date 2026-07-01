"""
Google Gemini REST API bridge.

Requires: GEMINI_API_KEY in .env (get free key at https://aistudio.google.com)
Free tier: 1500 req/day, 15 RPM for gemini-2.0-flash-lite.

Models:
  gemini-2.0-flash-lite  — fastest, free tier
  gemini-1.5-flash       — smarter, still free
  gemini-2.0-flash       — best free option
  gemini-1.5-pro         — most capable (paid)
"""

import os
import time
from typing import Iterator

import requests
from dotenv import load_dotenv

from tools.llm_bridges.base import LLMBridge, LLMResult

load_dotenv()

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def _convert_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-style messages to Gemini contents format."""
    system_instruction = None
    contents = []
    for m in messages:
        role = m["role"]
        content = m.get("content", "") or ""
        if role == "system":
            system_instruction = content
        else:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": content}]})
    return system_instruction, contents


class GeminiAPIBridge(LLMBridge):
    provider = "gemini-api"
    default_model = "gemini-2.0-flash-lite"
    models = [
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ]

    def is_available(self) -> bool:
        return bool(_api_key())

    def chat(self, messages: list[dict], model: str = "") -> LLMResult:
        key = _api_key()
        if not key:
            return LLMResult(False, "", "GEMINI_API_KEY not set", provider=self.provider)

        model = model or self.default_model
        t0 = time.time()
        system_instruction, contents = _convert_messages(messages)

        body: dict = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{_BASE}/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return LLMResult(
                True, text, timing_s=round(time.time() - t0, 2),
                model=model, provider=self.provider,
            )
        except requests.HTTPError as e:
            return LLMResult(False, "", f"HTTP {resp.status_code}: {resp.text[:300]}",
                             timing_s=round(time.time() - t0, 2), provider=self.provider)
        except Exception as e:
            return LLMResult(False, "", str(e),
                             timing_s=round(time.time() - t0, 2), provider=self.provider)

    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]:
        key = _api_key()
        if not key:
            yield "[ERROR] GEMINI_API_KEY not set"
            return

        model = model or self.default_model
        system_instruction, contents = _convert_messages(messages)

        body: dict = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{_BASE}/{model}:streamGenerateContent?alt=sse&key={key}"
        try:
            with requests.post(url, json=body, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    raw = line.decode("utf-8", errors="replace")
                    if raw.startswith("data: "):
                        raw = raw[6:]
                    try:
                        import json
                        chunk = json.loads(raw)
                        text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                        yield text
                    except Exception:
                        pass
        except Exception as e:
            yield f"[ERROR] {e}"


if __name__ == "__main__":
    bridge = GeminiAPIBridge()
    print(f"available={bridge.is_available()}")
    if bridge.is_available():
        r = bridge.simple("Say hi in one sentence.")
        print(f"ok={r.ok}  time={r.timing_s}s\n{r.text}")
