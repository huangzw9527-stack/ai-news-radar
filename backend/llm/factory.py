import os

from .base import BaseLLMProvider
from .claude import ClaudeProvider
from .openai_provider import OpenAIProvider
from .ollama import OllamaProvider


def _resolve_api_key(config_value: str) -> str:
    # yaml 中的值优先（前端配置页改动即时生效）；为空时回退到 .env 中的 LLM_API_KEY
    return config_value or os.environ.get("LLM_API_KEY") or ""


def create_llm_provider(config: dict) -> BaseLLMProvider:
    provider = config.get("provider", "claude")
    model = config.get("model", "")
    api_key = _resolve_api_key(config.get("api_key", ""))
    base_url = config.get("base_url", "")
    if provider == "claude":
        return ClaudeProvider(model, api_key, base_url)
    elif provider == "openai":
        return OpenAIProvider(model, api_key, base_url)
    elif provider == "ollama":
        return OllamaProvider(model, base_url=base_url or "http://localhost:11434")
    else:
        raise ValueError(f"Unknown provider: {provider}")
