"""
LLM Bridges — multi-provider LLM interface for ElieAtch.

Usage:
    from tools.llm_bridges import get_router

    router = get_router()
    r = router.chat("gemini-2.0-flash-lite", "Hello!")
    print(r.text)

    # List all available providers + models
    for provider, models in router.available().items():
        print(f"{provider}: {models}")
"""

from tools.llm_bridges.base import LLMBridge, LLMResult
from tools.llm_bridges.claude_cdp import ClaudeCDPBridge
from tools.llm_bridges.cohere_api import CohereBridge
from tools.llm_bridges.deepseek_api import DeepSeekBridge
from tools.llm_bridges.deepseek_cdp import DeepSeekCDPBridge
from tools.llm_bridges.gemini_api import GeminiAPIBridge
from tools.llm_bridges.groq_api import GroqBridge
from tools.llm_bridges.huggingface_api import HuggingFaceBridge
from tools.llm_bridges.minimax_api import MinimaxBridge
from tools.llm_bridges.mistral_api import MistralBridge
from tools.llm_bridges.nvidia_api import NvidiaBridge
from tools.llm_bridges.openrouter_free import OpenRouterFreeBridge
from tools.llm_bridges.huggingface_cdp import HuggingFaceCDPBridge
from tools.llm_bridges.minimax_cdp import MinimaxCDPBridge
from tools.llm_bridges.mistral_cdp import MistralCDPBridge
from tools.llm_bridges.grok_cdp import GrokCDPBridge
from tools.llm_bridges.kimi_cdp import KimiCDPBridge

__all__ = [
    "LLMBridge",
    "LLMResult",
    "GeminiAPIBridge",
    "GroqBridge",
    "DeepSeekBridge",
    "DeepSeekCDPBridge",
    "ClaudeCDPBridge",
    "MistralBridge",
    "OpenRouterFreeBridge",
    "HuggingFaceBridge",
    "MinimaxBridge",
    "CohereBridge",
    "NvidiaBridge",
    "HuggingFaceCDPBridge",
    "MinimaxCDPBridge",
    "MistralCDPBridge",
    "GrokCDPBridge",
    "KimiCDPBridge",
    "get_router",
]

_router = None


def get_router():
    global _router
    if _router is None:
        from tools.llm_router import LLMRouter
        _router = LLMRouter()
    return _router
