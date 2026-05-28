"""
Aadhya – Upstash Redis Session Store
Uses Upstash REST API (no redis-py dependency needed) via httpx.
"""
from __future__ import annotations
import json
from typing import Optional
import httpx

from backend.config import get_settings
from backend.schemas.session import Session
from backend.storage import supabase_store
from backend.utils.logger import log_event

settings = get_settings()


class RedisStore:
    def __init__(self):
        # Upstash REST base URL is typically like https://xxxx.upstash.io
        # Pipeline endpoint is /pipeline. Some users may paste the pipeline URL directly,
        # so normalize both forms here.
        raw = (settings.upstash_redis_rest_url or "").rstrip("/")
        self.base_url = raw
        self.pipeline_url = raw if raw.endswith("/pipeline") else (raw + "/pipeline" if raw else "")
        self.token = settings.upstash_redis_rest_token
        self.ttl = settings.session_ttl_hours * 3600
        self._headers = {"Authorization": f"Bearer {self.token}"}
        self._http: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            )
        return self._http

    def is_configured(self) -> bool:
        return bool(self.base_url and self.token
                    and self.base_url != "https://your-db.upstash.io")

    async def _exec(self, *command_parts) -> dict:
        """
        Execute a single Upstash command via POST (pipeline API).

        This avoids putting arbitrary strings (like JSON session blobs) into the URL path,
        which breaks persistence due to lack of URL-encoding.
        """
        if not self.is_configured():
            return {}
        payload = [list(command_parts)]
        try:
            client = self._http_client()
            response = await client.post(
                self.pipeline_url,
                headers={**self._headers, "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            response.raise_for_status()
            data = response.json()
            # Upstash pipeline returns a list of per-command results.
            if isinstance(data, list) and data:
                item = data[0]
                return item if isinstance(item, dict) else {"result": item}
            return data if isinstance(data, dict) else {}
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id="system",
                data={"phase": "upstash_exec", "error": str(e)[:200], "cmd": str(command_parts[:3])},
            )
            return {}

    async def _post(self, payload) -> dict:
        client = self._http_client()
        response = await client.post(
            self.pipeline_url,
            headers={**self._headers, "Content-Type": "application/json"},
            content=json.dumps(payload),
        )
        response.raise_for_status()
        return response.json()

    async def get_session(self, session_id: str) -> Optional[Session]:
        if not self.is_configured():
            return None
        try:
            result = await self._exec("GET", f"session:{session_id}")
            raw = result.get("result")
            if raw:
                return Session.model_validate_json(raw)
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id=session_id,
                data={"phase": "redis_get_session", "error": str(e)[:200]},
            )
        return None

    async def get_incomplete_session_id_for_phone(self, phone_number: str) -> Optional[str]:
        """
        Return the latest known incomplete voice session id for a phone number.
        Stored as a pointer key to avoid SCAN in the hot path.
        """
        if not self.is_configured():
            return None
        phone = (phone_number or "").strip()
        if not phone:
            return None
        try:
            res = await self._exec("GET", f"phone_incomplete:{phone}")
            val = res.get("result")
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id="system",
                data={"phase": "redis_get_phone_incomplete", "error": str(e)[:200]},
            )
        return None

    async def save_session(self, session: Session) -> bool:
        if not self.is_configured():
            return False
        try:
            key = f"session:{session.session_id}"
            # Trim unbounded hint lists to shrink payload (faster Upstash SET on large sessions).
            hints = session.extracted_fields.get("__guardrail_hints")
            if isinstance(hints, list) and len(hints) > 16:
                session.extracted_fields["__guardrail_hints"] = hints[-16:]
            data = session.model_dump_json()
            await self._exec("SET", key, data, "EX", int(self.ttl))
            # Maintain a pointer for "resume after dropped call" for voice.
            phone = (session.phone_number or "").strip()
            if phone:
                if getattr(session, "summary_generated", False):
                    await self._exec("DEL", f"phone_incomplete:{phone}")
                else:
                    await self._exec("SET", f"phone_incomplete:{phone}", session.session_id, "EX", int(self.ttl))
            return True
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id=session.session_id,
                data={"phase": "redis_save_session", "error": str(e)[:200]},
            )
            return False

    async def delete_session(self, session_id: str) -> bool:
        if not self.is_configured():
            return False
        try:
            await self._exec("DEL", f"session:{session_id}")
            return True
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id=session_id,
                data={"phase": "redis_delete_session", "error": str(e)[:200]},
            )
            return False

    async def set_nx(self, key: str, value: str, *, ex_seconds: int) -> bool:
        """
        SET key value NX EX <seconds>
        Returns True if key was set, False if it already existed or on error.
        """
        if not self.is_configured():
            return False
        try:
            res = await self._exec("SET", key, value, "EX", int(ex_seconds), "NX")
            # Upstash returns {"result": "OK"} when successful
            return (res or {}).get("result") == "OK"
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id="system",
                data={"phase": "redis_set_nx", "error": str(e)[:200]},
            )
            return False

    async def delete_key(self, key: str) -> bool:
        if not self.is_configured():
            return False
        try:
            await self._exec("DEL", key)
            return True
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id="system",
                data={"phase": "redis_delete_key", "error": str(e)[:200]},
            )
            return False

    async def list_session_ids(self) -> list[str]:
        """Returns all active session IDs using SCAN (safe for production Redis)."""
        if not self.is_configured():
            return []
        try:
            session_ids: list[str] = []
            cursor = 0
            while True:
                # SCAN cursor MATCH pattern COUNT hint
                result = await self._exec("SCAN", cursor, "MATCH", "session:*", "COUNT", 100)
                data = result.get("result", [])
                # Upstash REST returns [next_cursor, [keys...]]
                if isinstance(data, list) and len(data) == 2:
                    cursor = int(data[0])
                    keys = data[1] if isinstance(data[1], list) else []
                else:
                    # Unexpected shape — fall back to empty
                    break
                session_ids.extend(k.replace("session:", "") for k in keys)
                if cursor == 0:
                    break  # Full scan complete
            return session_ids
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id="system",
                data={"phase": "redis_scan_sessions", "error": str(e)[:200]},
            )
            return []

    async def lpush_capped(self, key: str, value: str, max_len: int):
        """Push to list and trim to max_len (for log feed)."""
        if not self.is_configured():
            return
        try:
            payload = [["LPUSH", key, value], ["LTRIM", key, 0, max_len - 1]]
            await self._post(payload)
        except Exception:
            pass

    async def get_logs(self, n: int = 100) -> list[dict]:
        """Get recent log entries from Redis."""
        if not self.is_configured():
            return []
        try:
            result = await self._exec("LRANGE", REDIS_LOG_KEY, 0, n - 1)
            entries = result.get("result", [])
            return [json.loads(e) for e in entries]
        except Exception as e:
            await log_event(
                "API_ERROR",
                session_id="system",
                data={"phase": "redis_get_logs", "error": str(e)[:200]},
            )
            return []


REDIS_LOG_KEY = "aadhya:logs"

# In-memory fallback when Redis is not configured
_memory_sessions: dict[str, Session] = {}


class InMemoryStore:
    """Fallback store for local dev without Upstash."""

    async def get_session(self, session_id: str) -> Optional[Session]:
        return _memory_sessions.get(session_id)

    async def save_session(self, session: Session) -> bool:
        _memory_sessions[session.session_id] = session
        return True

    async def delete_session(self, session_id: str) -> bool:
        _memory_sessions.pop(session_id, None)
        return True

    async def list_session_ids(self) -> list[str]:
        return list(_memory_sessions.keys())

    async def get_session_by_id(self, session_id: str) -> Optional[Session]:
        return _memory_sessions.get(session_id)

    async def all_sessions(self) -> list[Session]:
        return list(_memory_sessions.values())

    def is_configured(self) -> bool:
        return True  # Always available


_redis: RedisStore | None = None
_memory: InMemoryStore | None = None


def get_redis_store() -> RedisStore:
    global _redis
    if _redis is None:
        _redis = RedisStore()
    return _redis


def get_memory_store() -> InMemoryStore:
    global _memory
    if _memory is None:
        _memory = InMemoryStore()
    return _memory


async def get_session(session_id: str) -> Optional[Session]:
    """Get session — Redis, then Supabase snapshot, then in-memory."""
    redis = get_redis_store()
    if redis.is_configured():
        session = await redis.get_session(session_id)
        if session:
            return session
    if supabase_store.is_configured():
        session = await supabase_store.load_session_snapshot(session_id)
        if session:
            if redis.is_configured():
                await redis.save_session(session)
            await get_memory_store().save_session(session)
            return session
    return await get_memory_store().get_session(session_id)


async def save_session(session: Session) -> None:
    """Save session to Redis, memory, and Supabase (durable snapshot for chat/voice)."""
    redis = get_redis_store()
    if redis.is_configured():
        await redis.save_session(session)
    await get_memory_store().save_session(session)
    if supabase_store.is_configured():
        await supabase_store.save_session_snapshot(session)


async def delete_session(session_id: str) -> None:
    redis = get_redis_store()
    if redis.is_configured():
        await redis.delete_session(session_id)
    await get_memory_store().delete_session(session_id)
    if supabase_store.is_configured():
        await supabase_store.delete_session_snapshot(session_id)


async def list_all_sessions() -> list[Session]:
    """Returns all sessions (from memory store for now)."""
    return await get_memory_store().all_sessions()
