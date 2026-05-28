from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Optional

from google import genai
from google.genai import types

from backend.config import get_settings
from backend.utils.logger import log_event
from backend.utils.perf_analytics import emit_llm_call_metrics, usage_from_gemini_response
from backend.llm.base import LLMResult
from backend.llm.errors import LLMRetryableError, LLMError
from backend.llm.util import safe_parse_json


settings = get_settings()

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options={"api_version": "v1beta"},
        )
    return _client


def _gemini_content_role_from_openai_style(role: str | None) -> str:
    """
    Gemini generateContent expects roles 'user' or 'model' only.
    OpenAI-style histories use 'assistant' for model turns — map that here.
    """
    r = (role or "user").strip().lower()
    if r == "assistant":
        return "model"
    if r == "model":
        return "model"
    return "user"


def _history_item_text(item: dict) -> str:
    """Support both {'content': ...} (OpenAI-style) and {'parts': [{'text': ...}]} (Gemini-style)."""
    if not isinstance(item, dict):
        return ""
    if item.get("content") is not None:
        return str(item.get("content") or "")
    parts = item.get("parts") or []
    if parts and isinstance(parts[0], dict):
        return str(parts[0].get("text") or "")
    return ""


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None):
        self.model_name = model or settings.gemini_model

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
        client = _get_client()

        contents: list[types.Content] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = _gemini_content_role_from_openai_style(item.get("role"))
            text = _history_item_text(item)
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            top_p=0.95,
            max_output_tokens=max_tokens,
        )

        loop = asyncio.get_event_loop()
        t0 = time.perf_counter()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                ),
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            msg = str(e)
            await emit_llm_call_metrics(
                session_id,
                operation="chat",
                provider=self.name,
                model=self.model_name,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=False,
                error=msg[:300],
            )
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise LLMRetryableError(msg)
            raise LLMError(msg)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        text = response.text.strip() if getattr(response, "text", None) else ""
        gu = usage_from_gemini_response(response)
        pt, ct, tt = gu.get("_prompt_tokens"), gu.get("_completion_tokens"), gu.get("_total_tokens")
        await emit_llm_call_metrics(
            session_id,
            operation="chat",
            provider=self.name,
            model=self.model_name,
            duration_ms=duration_ms,
            max_tokens=max_tokens,
            stream=False,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            text_preview=text,
            gemini_usage=gu or None,
        )
        if not get_settings().log_perf_analytics:
            await log_event(
                "LLM_RESPONSE",
                session_id=session_id,
                data={"provider": self.name, "model": self.model_name, "preview": text[:120]},
            )
        return LLMResult(text=text, provider=self.name, model=self.model_name, raw=None)

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
        Stream incremental text pieces from Gemini.
        Returns an async iterator yielding small text chunks.
        """
        client = _get_client()

        contents: list[types.Content] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = _gemini_content_role_from_openai_style(item.get("role"))
            text = _history_item_text(item)
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            top_p=0.95,
            max_output_tokens=max_tokens,
        )

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_event_loop()
        usage_chunk: list[Any] = []
        err_holder: list[str] = []

        def worker():
            try:
                stream = client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                for chunk in stream:
                    if getattr(chunk, "usage_metadata", None) is not None:
                        usage_chunk[:] = [chunk]
                    text_part = getattr(chunk, "text", None)
                    if text_part:
                        loop.call_soon_threadsafe(queue.put_nowait, text_part)
            except Exception as e:
                err_holder.append(str(e)[:300])
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()

        async def gen():
            preview_accum = ""
            t0 = time.perf_counter()
            ttft_ms: float | None = None
            while True:
                item = await queue.get()
                if item is None:
                    break
                if item:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - t0) * 1000.0
                    if len(preview_accum) < 120:
                        preview_accum += item
                    yield item
            duration_ms = (time.perf_counter() - t0) * 1000.0
            gu: dict[str, Any] = {}
            if usage_chunk:
                gu = usage_from_gemini_response(usage_chunk[0])
            pt, ct, tt = gu.get("_prompt_tokens"), gu.get("_completion_tokens"), gu.get("_total_tokens")
            err = err_holder[0] if err_holder else None
            await emit_llm_call_metrics(
                session_id,
                operation="chat",
                provider=self.name,
                model=self.model_name,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=True,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                ttft_ms=ttft_ms,
                text_preview=preview_accum or None,
                error=err,
                gemini_usage=gu or None,
            )
            if not get_settings().log_perf_analytics and not err:
                await log_event(
                    "LLM_RESPONSE",
                    session_id=session_id,
                    data={
                        "provider": self.name,
                        "model": self.model_name,
                        "preview": preview_accum[:120],
                        "stream": True,
                    },
                )

        return gen()

    async def extract_json(
        self,
        *,
        session_id: str,
        extraction_prompt: str,
        max_tokens: int = 512,
    ) -> dict:
        client = _get_client()
        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )
        loop = asyncio.get_event_loop()
        t0 = time.perf_counter()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self.model_name,
                    contents=extraction_prompt,
                    config=config,
                ),
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            msg = str(e)
            await emit_llm_call_metrics(
                session_id,
                operation="extract_json",
                provider=self.name,
                model=self.model_name,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=False,
                error=msg[:300],
            )
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise LLMRetryableError(msg)
            raise LLMError(msg)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        text = response.text.strip() if getattr(response, "text", None) else "{}"
        gu = usage_from_gemini_response(response)
        pt, ct, tt = gu.get("_prompt_tokens"), gu.get("_completion_tokens"), gu.get("_total_tokens")
        await emit_llm_call_metrics(
            session_id,
            operation="extract_json",
            provider=self.name,
            model=self.model_name,
            duration_ms=duration_ms,
            max_tokens=max_tokens,
            stream=False,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            text_preview=text,
            gemini_usage=gu or None,
        )
        parsed = safe_parse_json(text)
        if parsed:
            return parsed

        # If Gemini returned partial/invalid JSON despite response_mime_type,
        # fall back to a normal chat call that returns JSON as text.
        # This prevents rare mid-object truncations like '{"field":' causing data loss.
        if isinstance(text, str) and text.lstrip().startswith("{"):
            try:
                res = await self.chat(
                    session_id=f"{session_id}:json_fallback",
                    system_prompt="Return ONLY a valid JSON object. No markdown, no commentary.",
                    user_message=extraction_prompt,
                    history=[],
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                repaired = safe_parse_json(res.text)
                return repaired if repaired else {}
            except Exception:
                return {}

        return {}
