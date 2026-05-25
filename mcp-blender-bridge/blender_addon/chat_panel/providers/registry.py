"""Provider registry — factory for all supported LLM providers."""

from __future__ import annotations

from .anthropic import AnthropicProvider
from .base import Provider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider

PROVIDERS: dict[str, type[Provider]] = {
    "anthropic": AnthropicProvider,
    "openai_compat": OpenAICompatProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str, *, api_key: str, base_url: str | None = None) -> Provider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider {name!r}. Choose from: {list(PROVIDERS)}")
    cls = PROVIDERS[name]
    if base_url is not None and name == "openai_compat":
        return OpenAICompatProvider(api_key=api_key, base_url=base_url)
    return cls(api_key=api_key)  # type: ignore[call-arg]
