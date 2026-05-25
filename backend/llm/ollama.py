import requests
from .base import BaseLLMProvider

class OllamaProvider(BaseLLMProvider):
    def __init__(self, model: str, api_key: str = "", base_url: str = "http://localhost:11434"):
        super().__init__(model, api_key)
        self.base_url = base_url

    def chat(self, system: str, user: str) -> str:
        resp = requests.post(f"{self.base_url}/api/chat", json={
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        })
        return resp.json()["message"]["content"]
