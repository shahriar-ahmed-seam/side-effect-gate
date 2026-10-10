"""SideGate Ecosystem Adapters for Anthropic Computer Use, Playwright, and OpenAI Tools."""

from sidegate.adapters.anthropic_adapter import AnthropicComputerUseAdapter
from sidegate.adapters.openai_adapter import OpenAIToolGateAdapter
from sidegate.adapters.playwright_adapter import PlaywrightGateAdapter

__all__ = [
    "AnthropicComputerUseAdapter",
    "OpenAIToolGateAdapter",
    "PlaywrightGateAdapter",
]
