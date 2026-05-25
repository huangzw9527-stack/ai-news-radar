import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.llm.factory import create_llm_provider
from backend.llm.base import BaseLLMProvider

def test_factory_returns_provider():
    config = {"provider": "claude", "model": "claude-sonnet-4-6", "api_key": "test"}
    provider = create_llm_provider(config)
    assert isinstance(provider, BaseLLMProvider)
    assert provider.model == "claude-sonnet-4-6"

def test_factory_unknown_provider_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown provider"):
        create_llm_provider({"provider": "unknown", "model": "x", "api_key": ""})
