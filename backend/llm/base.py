from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    def __init__(self, model: str, api_key: str, base_url: str = ""):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def chat(self, system: str, user: str) -> str:
        """发送消息，返回文本响应"""
        pass
