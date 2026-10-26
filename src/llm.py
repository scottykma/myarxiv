import json
import logging

from openai import OpenAI

from src.config import get, get_env

logger = logging.getLogger(__name__)

_fast_instance = None
_pro_instance = None


class LLMClient:
    def __init__(self, preset="fast"):
        env_var = get("llm.api_key_env", "OPENAI_API_KEY")
        api_key = get_env(env_var)
        if not api_key:
            raise ValueError(f"{env_var} is not set in environment")

        model_key = "llm.fast_model" if preset == "fast" else "llm.pro_model"
        default_model = "deepseek-v4-flash"
        self.model = get(model_key, default_model)
        self.base_url = get("llm.base_url", "https://api.deepseek.com")
        self._client = OpenAI(api_key=api_key, base_url=self.base_url)

    def call(self, messages, *, temperature=None, max_tokens=1024,
             thinking=False, stream=False):
        body = {"thinking": {"type": "enabled" if thinking else "disabled"}}
        kwargs = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            stream=stream,
            extra_body=body,
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        return self._client.chat.completions.create(**kwargs)

    @staticmethod
    def parse_json(content: str):
        content = content.strip()
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```").strip()
        return json.loads(content)


def get_fast() -> LLMClient:
    global _fast_instance
    if _fast_instance is None:
        _fast_instance = LLMClient("fast")
    return _fast_instance


def get_pro() -> LLMClient:
    global _pro_instance
    if _pro_instance is None:
        _pro_instance = LLMClient("pro")
    return _pro_instance
