import httpx
from openai import OpenAI
from .base import BaseLLMProvider

class OpenAIProvider(BaseLLMProvider):
    def chat(self, system: str, user: str) -> str:
        kwargs = {
            "api_key": self.api_key,
            "http_client": httpx.Client(proxy=None),
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = OpenAI(**kwargs)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=8192,
        )
        content = resp.choices[0].message.content
        finish = resp.choices[0].finish_reason
        if finish != "stop":
            print(f"[LLM] Warning: finish_reason={finish}, output may be truncated", flush=True)
        return content
