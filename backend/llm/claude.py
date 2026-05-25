import anthropic
import httpx
from .base import BaseLLMProvider

class ClaudeProvider(BaseLLMProvider):
    def chat(self, system: str, user: str) -> str:
        kwargs = {
            "api_key": self.api_key,
            # 禁用系统代理，避免本地代理软件干扰
            "http_client": httpx.Client(proxy=None),
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = anthropic.Anthropic(**kwargs)
        msg = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        return msg.content[0].text
