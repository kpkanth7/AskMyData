from __future__ import annotations

from typing import Any, Dict

import httpx

from app.providers.base import LLMProvider


class CerebrasProvider(LLMProvider):
    name = "cerebras"

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def _chat(self, system_prompt: str, user_prompt: str, temperature: float, response_format: Dict[str, Any] | None = None) -> str:
        if not self.api_key:
            raise RuntimeError("Cerebras API key is not configured")
        payload: Dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format:
            payload["response_format"] = response_format
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def structured_json(self, system_prompt: str, user_prompt: str, schema_hint: Dict[str, Any]) -> Dict[str, Any]:
        import json

        content = await self._chat(
            system_prompt,
            f"{user_prompt}\n\nReturn only JSON matching this shape: {json.dumps(schema_hint)}",
            temperature=0.05,
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    async def text(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        return await self._chat(system_prompt, user_prompt, temperature=temperature)
