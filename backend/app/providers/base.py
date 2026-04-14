from abc import ABC, abstractmethod
from typing import Any, Dict


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def structured_json(self, system_prompt: str, user_prompt: str, schema_hint: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def text(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        raise NotImplementedError
