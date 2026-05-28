from __future__ import annotations


class LLMError(Exception):
    """Base error for LLM provider calls."""


class LLMRetryableError(LLMError):
    """Retryable errors like 429s and transient 5xx."""

