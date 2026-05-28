from __future__ import annotations

import json
import time

import httpx

from backend.config import get_settings
from backend.utils.logger import log_event
from backend.utils.perf_analytics import emit_llm_call_metrics, openai_usage_from_response_body, openai_usage_tuple
from backend.llm.base import LLMResult
from backend.llm.errors import LLMRetryableError, LLMError
from backend.llm.util import safe_parse_json


settings = get_settings()


class OpenAICompatProvider:
    """
    Provider for OpenAI-compatible Chat Completions APIs.
    Works with OpenAI, OpenRouter, Groq, Together, Fireworks, etc.
    """

    name = "openai_compat"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _maybe_inject_reasoning_effort(self, payload: dict) -> None:
        """
        Inject `reasoning_effort` into the request body when the configured model is a
        reasoning-capable model (e.g. Groq's `openai/gpt-oss-20b`, OpenAI's o-series).

        WHY THIS MATTERS — root cause of "empty replies" on gpt-oss-20b:
        gpt-oss is a reasoning model. By default it generates hidden chain-of-thought
        tokens that count against `max_tokens` but are stripped from the returned
        `choices[0].message.content`. With small caps (24 for the classifier, 220 for
        the assistant, 384 for extraction), the model burns the entire budget on
        thinking and returns an empty string — visible in our logs as
        `text_preview: "" completion_tokens: <max_tokens>`.

        Setting `reasoning_effort: "low"` (or "none") tells the model to skip / minimise
        internal thinking and emit the answer directly.
        """
        effort = (settings.openai_reasoning_effort or "").strip().lower()
        if effort in ("", "auto"):
            return
        if effort not in ("none", "low", "medium", "high"):
            return
        model_lower = (self.model or "").lower()
        # Only send the param to models known to accept it. Other Groq / OpenRouter
        # models will 400 on unknown fields, so we stay conservative.
        if "gpt-oss" in model_lower or model_lower.startswith("o1") or model_lower.startswith("o3") or model_lower.startswith("o4"):
            payload["reasoning_effort"] = effort

    def _openai_messages(self, system_prompt: str, user_message: str, history: list[dict]) -> list[dict]:
        """Convert Gemini-style history into OpenAI chat messages."""
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for item in history:
            role = item.get("role", "user")
            text = item.get("parts", [{}])[0].get("text", "")
            messages.append({"role": "assistant" if role == "model" else "user", "content": text})
        messages.append({"role": "user", "content": user_message})
        return messages

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
        if not self.base_url or not self.api_key or not self.model:
            raise LLMError("OpenAI-compatible provider is not configured (OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL).")

        messages = self._openai_messages(system_prompt, user_message, history)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        self._maybe_inject_reasoning_effort(payload)

        url = f"{self.base_url}/chat/completions"
        t0 = time.perf_counter()
        r = await self._client().post(url, headers=self._headers(), json=payload)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        if r.status_code in (429, 500, 502, 503, 504):
            await emit_llm_call_metrics(
                session_id,
                operation="chat",
                provider=self.name,
                model=self.model,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=False,
                http_status=r.status_code,
                error=r.text[:200],
            )
            raise LLMRetryableError(f"{r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            await emit_llm_call_metrics(
                session_id,
                operation="chat",
                provider=self.name,
                model=self.model,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=False,
                http_status=r.status_code,
                error=r.text[:200],
            )
            raise LLMError(f"{r.status_code} {r.text[:200]}")

        data = r.json()
        text = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        pt, ct, tt = openai_usage_from_response_body(data)
        await emit_llm_call_metrics(
            session_id,
            operation="chat",
            provider=self.name,
            model=self.model,
            duration_ms=duration_ms,
            max_tokens=max_tokens,
            stream=False,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            text_preview=text,
            http_status=r.status_code,
        )
        if not get_settings().log_perf_analytics:
            await log_event(
                "LLM_RESPONSE",
                session_id=session_id,
                data={"provider": self.name, "model": self.model, "preview": text[:120]},
            )
        return LLMResult(text=text, provider=self.name, model=self.model, raw=None)

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
        Stream incremental text from OpenAI-compatible SSE (/v1/chat/completions with stream: true).
        Yields each delta.content fragment as received (Groq, OpenAI, OpenRouter, etc.).
        """
        if not self.base_url or not self.api_key or not self.model:
            raise LLMError("OpenAI-compatible provider is not configured (OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL).")

        messages = self._openai_messages(system_prompt, user_message, history)
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        self._maybe_inject_reasoning_effort(payload)
        url = f"{self.base_url}/chat/completions"

        async def gen():
            preview_accum = ""
            stream_err: str | None = None
            t0 = time.perf_counter()
            ttft_ms: float | None = None
            last_usage: dict | None = None
            http_status: int | None = None
            try:
                async with self._client().stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=httpx.Timeout(60.0),
                ) as r:
                    http_status = r.status_code
                    if r.status_code in (429, 500, 502, 503, 504):
                        body = (await r.aread()).decode("utf-8", errors="replace")
                        raise LLMRetryableError(f"{r.status_code} {body[:200]}")
                    if r.status_code >= 400:
                        body = (await r.aread()).decode("utf-8", errors="replace")
                        raise LLMError(f"{r.status_code} {body[:200]}")

                    async for raw_line in r.aiter_lines():
                        line = (raw_line or "").strip()
                        if not line or line.startswith(":"):
                            continue
                        if line == "data: [DONE]":
                            break
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        try:
                            obj = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        err = obj.get("error")
                        if isinstance(err, dict) and err.get("message"):
                            raise LLMError(str(err.get("message"))[:300])
                        u = obj.get("usage")
                        if isinstance(u, dict):
                            last_usage = u
                        for ch in obj.get("choices") or []:
                            delta = ch.get("delta") or {}
                            piece = delta.get("content")
                            if isinstance(piece, str) and piece:
                                if ttft_ms is None:
                                    ttft_ms = (time.perf_counter() - t0) * 1000.0
                                if len(preview_accum) < 120:
                                    preview_accum += piece
                                yield piece
            except LLMRetryableError as e:
                stream_err = str(e)[:300]
                raise
            except LLMError as e:
                stream_err = str(e)[:300]
                raise
            except httpx.HTTPError as e:
                stream_err = str(e)[:200]
                raise LLMRetryableError(str(e)[:200]) from e
            except Exception as e:
                stream_err = str(e)[:200]
                raise LLMError(str(e)[:200]) from e
            finally:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                pt, ct, tt = openai_usage_tuple(last_usage)
                await emit_llm_call_metrics(
                    session_id,
                    operation="chat",
                    provider=self.name,
                    model=self.model,
                    duration_ms=duration_ms,
                    max_tokens=max_tokens,
                    stream=True,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                    ttft_ms=ttft_ms,
                    text_preview=preview_accum or None,
                    http_status=http_status,
                    error=stream_err,
                )
                if not get_settings().log_perf_analytics and not stream_err:
                    await log_event(
                        "LLM_RESPONSE",
                        session_id=session_id,
                        data={
                            "provider": self.name,
                            "model": self.model,
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
        if not self.base_url or not self.api_key or not self.model:
            raise LLMError("OpenAI-compatible provider is not configured (OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL).")

        # Ask for JSON-only output. Some providers support response_format; keep it optional.
        messages = [
            {"role": "system", "content": "Return only valid JSON. No markdown, no explanation."},
            {"role": "user", "content": extraction_prompt},
        ]

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        # Best-effort: if provider supports it, it will help.
        payload["response_format"] = {"type": "json_object"}
        self._maybe_inject_reasoning_effort(payload)

        url = f"{self.base_url}/chat/completions"
        t0 = time.perf_counter()
        r = await self._client().post(url, headers=self._headers(), json=payload)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        if r.status_code in (429, 500, 502, 503, 504):
            await emit_llm_call_metrics(
                session_id,
                operation="extract_json",
                provider=self.name,
                model=self.model,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=False,
                http_status=r.status_code,
                error=r.text[:200],
            )
            raise LLMRetryableError(f"{r.status_code} {r.text[:200]}")
        if r.status_code >= 400:
            await emit_llm_call_metrics(
                session_id,
                operation="extract_json",
                provider=self.name,
                model=self.model,
                duration_ms=duration_ms,
                max_tokens=max_tokens,
                stream=False,
                http_status=r.status_code,
                error=r.text[:200],
            )
            raise LLMError(f"{r.status_code} {r.text[:200]}")

        data = r.json()
        text = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        pt, ct, tt = openai_usage_from_response_body(data)
        await emit_llm_call_metrics(
            session_id,
            operation="extract_json",
            provider=self.name,
            model=self.model,
            duration_ms=duration_ms,
            max_tokens=max_tokens,
            stream=False,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            text_preview=text,
            http_status=r.status_code,
        )
        return safe_parse_json(text)
