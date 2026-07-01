"""Shared base class and result type for all LLM bridges."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class LLMResult:
    ok: bool
    text: str
    error: str = ""
    timing_s: float = 0.0
    model: str = ""
    provider: str = ""


class LLMBridge(ABC):
    provider: str = ""
    default_model: str = ""
    models: list[str] = []

    @abstractmethod
    def chat(self, messages: list[dict], model: str = "") -> LLMResult: ...

    @abstractmethod
    def stream(self, messages: list[dict], model: str = "") -> Iterator[str]: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    def simple(self, prompt: str, system: str = "", model: str = "") -> LLMResult:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return self.chat(msgs, model or self.default_model)
