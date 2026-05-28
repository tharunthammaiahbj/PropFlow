from __future__ import annotations

from functools import lru_cache

from backend.config import get_settings
from backend.utils.logger import log_event
from backend.llm.base import LLMProvider, LLMResult
from backend.llm.errors import LLMRetryableError, LLMError
from backend.llm.providers_gemini import GeminiProvider
from backend.llm.providers_openai_compat import OpenAICompatProvider


settings = get_settings()


def _parse_fallbacks(value: str) -> list[str]:
    parts = [p.strip() for p in (value or "").split(",")]
    return [p for p in parts if p]


class LLMRouter:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {
            "gemini": GeminiProvider(),
            "openai_compat": OpenAICompatProvider(),
        }

    def _ordered_provider_names(self) -> list[str]:
        # Primary first, then fallbacks in order, de-duplicated.
        names: list[str] = []
        primary = (settings.llm_provider or "gemini").strip()
        if primary:
            names.append(primary)
        names.extend(_parse_fallbacks(settings.llm_fallbacks))
        out: list[str] = []
        for n in names:
            if n not in out:
                out.append(n)
        return out

    def _get(self, name: str) -> LLMProvider:
        if name not in self._providers:
            raise LLMError(f"Unknown LLM provider '{name}'. Expected one of: {', '.join(self._providers.keys())}.")
        return self._providers[name]

    async def chat(
        self,
        *,
        session_id: str,
        system_prompt: str,
        user_message: str,
        history: list[dict],
        temperature: float = 0.85,
        max_tokens: int = 512,
    ) -> LLMResult:
        last_err: Exception | None = None
        for name in self._ordered_provider_names():
            provider = self._get(name)
            try:
                return await provider.chat(
                    session_id=session_id,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    history=history,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMRetryableError as e:
                last_err = e
                await log_event(
                    "LLM_FALLBACK",
                    session_id=session_id,
                    data={"from_provider": name, "reason": str(e)[:160]},
                )
                continue
            except LLMError as e:
                # Non-retryable provider error: still allow fallback if others exist.
                last_err = e
                await log_event(
                    "LLM_PROVIDER_ERROR",
                    session_id=session_id,
                    data={"provider": name, "error": str(e)[:160]},
                )
                continue
        raise LLMError(str(last_err) if last_err else "No LLM providers available.")

    def chat_stream(
        self,
        *,
        session_id: str,
        system_prompt: str,
        user_message: str,
        history: list[dict],
        temperature: float = 0.85,
        max_tokens: int = 512,
    ):
        """
        Best-effort streaming: uses the first provider that exposes chat_stream().
        Falls back to non-streaming chat() yielding a single chunk.
        """
        async def _fallback_single_chunk():
            res = await self.chat(
                session_id=session_id,
                system_prompt=system_prompt,
                user_message=user_message,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            yield res.text

        for name in self._ordered_provider_names():
            provider = self._get(name)
            fn = getattr(provider, "chat_stream", None)
            if callable(fn):
                try:
                    return fn(
                        session_id=session_id,
                        system_prompt=system_prompt,
                        user_message=user_message,
                        history=history,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                except Exception:
                    # If streaming setup fails, fall back to next provider.
                    continue
        return _fallback_single_chunk()

    async def extract_json(
        self,
        *,
        session_id: str,
        extraction_prompt: str,
        max_tokens: int = 512,
    ) -> dict:
        last_err: Exception | None = None
        for name in self._ordered_provider_names():
            provider = self._get(name)
            try:
                return await provider.extract_json(
                    session_id=session_id,
                    extraction_prompt=extraction_prompt,
                    max_tokens=max_tokens,
                )
            except LLMRetryableError as e:
                last_err = e
                await log_event(
                    "LLM_FALLBACK",
                    session_id=session_id,
                    data={"from_provider": name, "reason": str(e)[:160], "mode": "extract_json"},
                )
                continue
            except LLMError as e:
                last_err = e
                await log_event(
                    "LLM_PROVIDER_ERROR",
                    session_id=session_id,
                    data={"provider": name, "error": str(e)[:160], "mode": "extract_json"},
                )
                continue
        return {}


@lru_cache
def get_llm_router() -> LLMRouter:
    return LLMRouter()

