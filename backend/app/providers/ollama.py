from typing import Any, Dict

import httpx

from app.providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def _generate(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool = False) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json().get("response", "")

    async def structured_json(self, system_prompt: str, user_prompt: str, schema_hint: Dict[str, Any]) -> Dict[str, Any]:
        import json

        content = await self._generate(
            system_prompt,
            f"{user_prompt}\n\nReturn only JSON matching this shape: {json.dumps(schema_hint)}",
            temperature=0.05,
            json_mode=True,
        )
        return json.loads(content)

    async def text(self, system_prompt: str, user_prompt: str, temperature: float = 0.25) -> str:
        return await self._generate(system_prompt, user_prompt, temperature=temperature)
