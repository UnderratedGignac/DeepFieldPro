"""
Unified LLM Router — route by model name prefix to the right bridge.

Model prefix routing:
  gemini-*  / gemini/*               → GeminiAPIBridge
  groq/*    / llama-* / mixtral-*    → GroqBridge
  deepseek-*                         → DeepSeekBridge
  mistral-* / open-mistral-*         → MistralBridge
  *:free                             → OpenRouterFreeBridge
  hf/*    / huggingface/*            → HuggingFaceBridge
  minimax-* / MiniMax-* / abab*      → MinimaxBridge
  command-*                          → CohereBridge
  qwen3* / qwen-* / qwq-* / qvq-*   → DashScopeBridge  (Alibaba Model Studio intl)
  nvidia/* / qwen/* / meta/* (NIM)   → NvidiaBridge      (explicit NIM model IDs)
  chatgpt-cdp / gpt-*                → ChatGPTCDPBridge (if available)
  gemini-cdp                         → GeminiCDPBridge (if available)
  deepseek-cdp                       → DeepSeekCDPBridge (if available)
  claude-cdp                         → ClaudeCDPBridge (if available)

Usage:
    from tools.llm_router import LLMRouter

    r = LLMRouter()
    result = r.chat("groq/llama-3.3-70b-versatile", "Hello!")
    print(result.text)

    # Streaming
    for chunk in r.stream("gemini-2.0-flash-lite", "Explain Python in 3 sentences"):
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

from typing import Iterator

from tools.llm_bridges.base import LLMBridge, LLMResult
from tools.llm_bridges.cohere_api import CohereBridge
from tools.llm_bridges.deepseek_api import DeepSeekBridge
from tools.llm_bridges.gemini_api import GeminiAPIBridge
from tools.llm_bridges.groq_api import GroqBridge
from tools.llm_bridges.huggingface_api import HuggingFaceBridge
from tools.llm_bridges.minimax_api import MinimaxBridge
from tools.llm_bridges.mistral_api import MistralBridge
from tools.llm_bridges.dashscope_api import DashScopeBridge
from tools.llm_bridges.nvidia_api import NvidiaBridge
from tools.llm_bridges.openrouter_free import OpenRouterFreeBridge

# CDP bridges are optional — import gracefully
try:
    from tools.llm_bridges.chatgpt_cdp import ChatGPTCDPBridge

    _CHATGPT_CDP = ChatGPTCDPBridge()
except Exception:
    _CHATGPT_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.gemini_cdp import GeminiCDPBridge

    _GEMINI_CDP = GeminiCDPBridge()
except Exception:
    _GEMINI_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.deepseek_cdp import DeepSeekCDPBridge

    _DEEPSEEK_CDP = DeepSeekCDPBridge()
except Exception:
    _DEEPSEEK_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.claude_cdp import ClaudeCDPBridge

    _CLAUDE_CDP = ClaudeCDPBridge()
except Exception:
    _CLAUDE_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.huggingface_cdp import HuggingFaceCDPBridge

    _HF_CDP = HuggingFaceCDPBridge()
except Exception:
    _HF_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.minimax_cdp import MinimaxCDPBridge

    _MINIMAX_CDP = MinimaxCDPBridge()
except Exception:
    _MINIMAX_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.mistral_cdp import MistralCDPBridge

    _MISTRAL_CDP = MistralCDPBridge()
except Exception:
    _MISTRAL_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.grok_cdp import GrokCDPBridge

    _GROK_CDP = GrokCDPBridge()
except Exception:
    _GROK_CDP = None  # type: ignore[assignment]

try:
    from tools.llm_bridges.kimi_cdp import KimiCDPBridge

    _KIMI_CDP = KimiCDPBridge()
except Exception:
    _KIMI_CDP = None  # type: ignore[assignment]


class LLMRouter:
    """Routes model name → bridge → result."""

    def __init__(self) -> None:
        self._bridges: list[LLMBridge] = [
            DashScopeBridge(),
            GeminiAPIBridge(),
            GroqBridge(),
            DeepSeekBridge(),
            MistralBridge(),
            OpenRouterFreeBridge(),
            HuggingFaceBridge(),
            MinimaxBridge(),
            CohereBridge(),
            NvidiaBridge(),
        ]
        if _CHATGPT_CDP is not None:
            self._bridges.append(_CHATGPT_CDP)
        if _GEMINI_CDP is not None:
            self._bridges.append(_GEMINI_CDP)
        if _DEEPSEEK_CDP is not None:
            self._bridges.append(_DEEPSEEK_CDP)
        if _CLAUDE_CDP is not None:
            self._bridges.append(_CLAUDE_CDP)
        if _HF_CDP is not None:
            self._bridges.append(_HF_CDP)
        if _MINIMAX_CDP is not None:
            self._bridges.append(_MINIMAX_CDP)
        if _MISTRAL_CDP is not None:
            self._bridges.append(_MISTRAL_CDP)
        if _GROK_CDP is not None:
            self._bridges.append(_GROK_CDP)
        if _KIMI_CDP is not None:
            self._bridges.append(_KIMI_CDP)

    # ------------------------------------------------------------------
    # Routing logic
    # ------------------------------------------------------------------

    def _resolve(self, model: str) -> tuple[LLMBridge, str]:
        """Return (bridge, model_name) for the given model string."""
        m = model.strip()

        # CDP paths — route short alias names to their bridges
        _cdp_aliases = {
            "chatgpt-cdp": _CHATGPT_CDP,
            "gpt-cdp":     _CHATGPT_CDP,
            "gemini-cdp":  _GEMINI_CDP,
            "deepseek-cdp": _DEEPSEEK_CDP,
            "claude-cdp":  _CLAUDE_CDP,
            "hf-cdp":      _HF_CDP,
            "huggingface-cdp": _HF_CDP,
            "minimax-cdp": _MINIMAX_CDP,
            "mistral-cdp": _MISTRAL_CDP,
            "grok-cdp":    _GROK_CDP,
            "kimi-cdp":    _KIMI_CDP,
            "moonshot-cdp": _KIMI_CDP,
        }
        if m in _cdp_aliases and _cdp_aliases[m] is not None:
            b = _cdp_aliases[m]
            return b, b.default_model

        # Model name → bridge dispatch
        prefixes: list[tuple[tuple[str, ...], LLMBridge]] = [
            (("gemini-cdp",), _GEMINI_CDP or GeminiAPIBridge()),
            (("gpt-", "chatgpt-"), _CHATGPT_CDP or OpenRouterFreeBridge()),
            (("deepseek-cdp",), _DEEPSEEK_CDP or DeepSeekBridge()),
            (("claude-cdp",), _CLAUDE_CDP or OpenRouterFreeBridge()),
            (("gemini-", "gemini/"), GeminiAPIBridge()),
            (("groq/", "llama-", "mixtral-", "gemma2-"), GroqBridge()),
            # DashScope: qwen3*/qwen3.x-*, qwen-*, qwq-*, qvq-*, deepseek-v (on dashscope)
            (("qwen3", "qwen-", "qwq-", "qvq-", "wan2",), DashScopeBridge()),
            (("deepseek-",), DeepSeekBridge()),
            (("mistral-", "open-mistral-", "open-mixtral-"), MistralBridge()),
            (("minimax-", "MiniMax-", "abab"), MinimaxBridge()),
            (("command-",), CohereBridge()),
            (("hf/", "huggingface/", "HuggingFace"), HuggingFaceBridge()),
            # nvidia/ prefix → NVIDIA NIM (keep for explicit NVIDIA model IDs)
            (("nvidia/", "qwen/", "meta/", "google/gemma-3-27", "mistralai/mistral-large"), NvidiaBridge()),
            (("kimi-", "moonshot-v1-", "moonshot-v1"), _KIMI_CDP or OpenRouterFreeBridge()),
        ]
        for prefix_tuple, bridge in prefixes:
            if any(m.startswith(p) for p in prefix_tuple):
                return bridge, m

        # :free suffix → OpenRouter
        if m.endswith(":free"):
            return OpenRouterFreeBridge(), m

        # Default: OpenRouter free (covers most model names)
        return OpenRouterFreeBridge(), m

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        model: str,
        prompt: str,
        system: str = "",
        messages: list[dict] | None = None,
    ) -> LLMResult:
        bridge, resolved_model = self._resolve(model)
        if messages is not None:
            return bridge.chat(messages, resolved_model)
        return bridge.simple(prompt, system=system, model=resolved_model)

    def stream(
        self,
        model: str,
        prompt: str,
        system: str = "",
        messages: list[dict] | None = None,
    ) -> Iterator[str]:
        bridge, resolved_model = self._resolve(model)
        if messages is None:
            msgs: list[dict] = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            messages = msgs
        return bridge.stream(messages, resolved_model)

    def available(self) -> dict[str, list[str]]:
        """Return {provider: [model, ...]} for all bridges that have API keys set."""
        out: dict[str, list[str]] = {}
        for bridge in self._bridges:
            if bridge.is_available():
                out[bridge.provider] = list(bridge.models)
        return out

    def all_models(self) -> list[str]:
        """Flat list of all available model names (for autocomplete)."""
        result = []
        for bridge in self._bridges:
            if bridge.is_available():
                result.extend(bridge.models)
        return result

    def status_table(self) -> str:
        """Formatted ASCII table of all providers and their status."""
        lines = [
            f"{'PROVIDER':<22} {'STATUS':<12} {'MODELS':>6}  SAMPLE MODEL",
            "-" * 72,
        ]
        for bridge in self._bridges:
            avail = bridge.is_available()
            status = "[OK]   " if avail else "[no key]"
            count = len(bridge.models) if avail else 0
            sample = bridge.default_model if avail else "-"
            lines.append(f"{bridge.provider:<22} {status:<12} {count:>6}  {sample}")
        return "\n".join(lines)


# ------------------------------------------------------------------
# CLI smoke test
# ------------------------------------------------------------------
if __name__ == "__main__":
    router = LLMRouter()
    print(router.status_table())
    print()

    avail = router.available()
    if not avail:
        print("No providers available. Add API keys to .env")
    else:
        # Quick ping on the first available
        provider, models = next(iter(avail.items()))
        model = models[0]
        print(f"Testing {provider} / {model} ...")
        r = router.chat(model, "Say ONLINE in exactly one word.")
        print(f"ok={r.ok}  time={r.timing_s}s")
        print(r.text if r.ok else r.error)
