"""
Aadhya – Retry Utility
Exponential backoff decorator for async functions.
"""
from __future__ import annotations
import asyncio
import functools
from typing import Any, Callable, Tuple, Type

from backend.utils.logger import log_event


async def with_retry(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    session_id: str = "unknown",
    **kwargs,
) -> Any:
    """
    Async retry with exponential backoff.

    Usage:
        result = await with_retry(some_async_fn, arg1, kwarg1=val, session_id="xyz")
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exc = e
            if attempt == max_attempts:
                await log_event("API_ERROR", session_id=session_id,
                                data={
                                    "error": str(e),
                                    "retry_count": attempt,
                                    "final": True,
                                })
                raise
            delay = base_delay * (2 ** (attempt - 1))
            await log_event("API_ERROR", session_id=session_id,
                            data={
                                "error": str(e),
                                "retry_count": attempt,
                                "retry_in_seconds": delay,
                            })
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore


def sync_retry(max_attempts: int = 3, base_delay: float = 1.0):
    """Decorator for sync functions (used in non-async contexts)."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt == max_attempts:
                        raise
                    import time
                    time.sleep(base_delay * (2 ** (attempt - 1)))
            raise last_exc
        return wrapper
    return decorator
