"""
Structured performance / LLM analytics (opt-in via LOG_PERF_ANALYTICS=1).

- quest_llm_phase("extraction") context: attributed to LLM_CALL_METRICS.phase
- emit_llm_call_metrics: per provider network call (duration, tokens when API returns them)
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from backend.config import get_settings
from backend.utils.logger import log_event

_LLM_PHASE: ContextVar[str] = ContextVar("llm_perf_phase", default="")


@contextmanager
def quest_llm_phase(phase: str):
    """Mark the current quest-related LLM call site for LLM_CALL_METRICS.phase."""
    tok: Token[str] = _LLM_PHASE.set(phase or "")
    try:
        yield
    finally:
        _LLM_PHASE.reset(tok)


def peek_quest_llm_phase() -> str | None:
    v = (_LLM_PHASE.get() or "").strip()
    return v or None


def openai_usage_tuple(usage: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    if not usage:
        return None, None, None
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    tt = usage.get("total_tokens")
    try:
        pti = int(pt) if pt is not None else None
    except (TypeError, ValueError):
        pti = None
    try:
        cti = int(ct) if ct is not None else None
    except (TypeError, ValueError):
        cti = None
    try:
        tti = int(tt) if tt is not None else None
    except (TypeError, ValueError):
        tti = None
    return pti, cti, tti


def openai_usage_from_response_body(data: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    if not data or not isinstance(data, dict):
        return None, None, None
    u = data.get("usage")
    if not isinstance(u, dict):
        return None, None, None
    return openai_usage_tuple(u)


def usage_from_gemini_response(response: Any) -> dict[str, Any]:
    """Map google-genai usage_metadata to a small dict + OpenAI-style triple."""
    um = getattr(response, "usage_metadata", None)
    if um is None:
        return {}
    raw: dict[str, Any] = {}
    for key in (
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
    ):
        v = getattr(um, key, None)
        if v is not None:
            try:
                raw[key] = int(v)
            except (TypeError, ValueError):
                raw[key] = v
    pt = raw.get("prompt_token_count")
    ct = raw.get("candidates_token_count")
    tt = raw.get("total_token_count")
    if tt is None and pt is not None and ct is not None:
        tt = pt + ct
    raw["_prompt_tokens"] = pt
    raw["_completion_tokens"] = ct
    raw["_total_tokens"] = tt
    return raw


async def emit_llm_call_metrics(
    session_id: str,
    *,
    operation: str,
    provider: str,
    model: str,
    duration_ms: float,
    max_tokens: int,
    stream: bool,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    ttft_ms: float | None = None,
    text_preview: str | None = None,
    error: str | None = None,
    http_status: int | None = None,
    gemini_usage: dict[str, Any] | None = None,
) -> None:
    if not get_settings().log_perf_analytics:
        return
    phase = peek_quest_llm_phase()
    data: dict[str, Any] = {
        "operation": operation,
        "phase": phase,
        "provider": provider,
        "model": model,
        "duration_ms": round(duration_ms, 3),
        "max_tokens": max_tokens,
        "stream": stream,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    if ttft_ms is not None:
        data["ttft_ms"] = round(ttft_ms, 3)
    if text_preview is not None:
        data["text_preview"] = text_preview[:120]
    if error:
        data["error"] = error[:300]
    if http_status is not None:
        data["http_status"] = http_status
    if gemini_usage:
        # Compact provider-native counts (no prompt text).
        data["gemini_usage"] = {k: v for k, v in gemini_usage.items() if not str(k).startswith("_")}
    await log_event("LLM_CALL_METRICS", session_id=session_id, data=data)


async def emit_channel_turn_timing(
    session_id: str,
    *,
    channel: str,
    segments_ms: dict[str, float],
    extra: dict[str, Any] | None = None,
) -> None:
    if not get_settings().log_perf_analytics:
        return
    rounded = {k: round(v, 3) for k, v in segments_ms.items()}
    total = sum(segments_ms.values())
    payload: dict[str, Any] = {
        "channel": channel,
        "segments_ms": rounded,
        "total_measured_ms": round(total, 3),
    }
    if extra:
        payload.update(extra)
    await log_event("CHANNEL_TURN_TIMING", session_id=session_id, data=payload)
