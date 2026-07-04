"""LLM 客户端 — OpenAI 兼容协议."""

from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx

from fanqie.utils.config import get_llm_config


class LLMClient:
    """OpenAI 兼容 LLM 客户端."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        cfg = get_llm_config()
        self.base_url = (base_url or cfg.get("base_url", "")).rstrip("/")
        self.api_key = api_key or cfg.get("api_key", "")
        self.model = model or cfg.get("model", "gpt-4o")
        self.temperature = temperature if temperature is not None else cfg.get("temperature", 0.7)
        self.max_tokens = max_tokens or cfg.get("max_tokens", 4096)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> dict:
        """发送聊天请求."""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": stream,
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=120) as client:
                    response = client.post(url, headers=self._headers(), json=payload)
                    response.raise_for_status()
                    data = response.json()

                    choice = data["choices"][0]
                    return {
                        "content": choice["message"]["content"],
                        "usage": {
                            "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                            "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                            "total_tokens": data.get("usage", {}).get("total_tokens", 0),
                        },
                        "model": data.get("model", self.model),
                    }
            except httpx.HTTPStatusError as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

        raise RuntimeError("LLM request failed after retries")

    def chat_json(
        self,
        messages: list[dict],
        temperature: float | None = None,
    ) -> dict:
        """发送请求并尝试解析 JSON 返回."""
        result = self.chat(messages, temperature=temperature or 0.3)
        content = result["content"]

        json_str = _extract_json(content)
        if json_str:
            try:
                parsed = json.loads(json_str)
                result["parsed"] = parsed
                return result
            except json.JSONDecodeError:
                pass

        result["parsed"] = None
        result["parse_error"] = True
        return result


def _extract_json(text: str) -> str | None:
    """从 LLM 响应中提取 JSON 块."""
    # 策略1: 匹配 ```json 代码块
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if m:
        return m.group(1).strip()

    # 策略2: 匹配最外层 {}
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数: 1 汉字约 1.5 token."""
    return int(len(text) * 1.5)
