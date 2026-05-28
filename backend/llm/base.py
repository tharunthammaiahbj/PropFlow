from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    raw: Any | None = None


class LLMProvider(Protocol):
    name: str

    async def chat(
        self,
        *,
        session_id: str,
        system_prompt: str,
        user_message: str,
        history: list[dict],
        temperature: float = 0.85,
        max_tokens: int = 512,
    ) -> LLMResult: ...

    async def extract_json(
        self,
        *,
        session_id: str,
        extraction_prompt: str,
        max_tokens: int = 512,
    ) -> dict: ...

