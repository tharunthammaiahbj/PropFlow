from __future__ import annotations

from typing import Optional

from backend.llm.router import get_llm_router
from backend.utils.retry import with_retry


class LLMEngine:
    """
    Drop-in replacement for GeminiEngine with the same surface area used by the app:
    - chat()
    - extract_json()
    - build_history()

    Internally routes to a provider-agnostic LLM router with fallback.
    """

    def __init__(self):
        self.router = get_llm_router()

    async def chat(
        self,
        session_id: str,
        user_message: str,
        system_prompt: str,
        history: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        # Keep existing retry wrapper, but router already handles fallback.
        result = await with_retry(
            self._chat_once,
            session_id,
            user_message,
            system_prompt,
            history,
            temperature,
            max_tokens,
            session_id=session_id,
        )
        return result

    async def chat_stream(
        self,
        *,
        session_id: str,
        user_message: str,
        system_prompt: str,
        history: list[dict],
        temperature: float = 0.85,
        max_tokens: int = 512,
    ):
        """
        Stream text chunks from the LLM.
        Returns an async iterator yielding incremental text pieces.
        """
        return self.router.chat_stream(
            session_id=session_id,
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _chat_once(
        self,
        session_id: str,
        user_message: str,
        system_prompt: str,
        history: list[dict],
        temperature: float | None,
        max_tokens: int | None,
    ) -> str:
        kwargs: dict = {
            "session_id": session_id,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "history": history,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        res = await self.router.chat(**kwargs)
        return res.text

    async def extract_json(self, session_id: str, extraction_prompt: str) -> dict:
        return await self.router.extract_json(session_id=session_id, extraction_prompt=extraction_prompt)

    def build_history(self, conversation_history: list) -> list[dict]:
        """
        Keep the existing Gemini-style history format because:
        - Gemini provider consumes it directly.
        - OpenAI-compatible provider converts it internally.
        """
        history = []
        for msg in conversation_history:
            if msg.role in ("user", "assistant"):
                role = "model" if msg.role == "assistant" else "user"
                history.append(
                    {
                        "role": role,
                        "parts": [{"text": msg.content}],
                    }
                )
        return history


_engine: Optional[LLMEngine] = None


def get_llm_engine() -> LLMEngine:
    global _engine
    if _engine is None:
        _engine = LLMEngine()
    return _engine

