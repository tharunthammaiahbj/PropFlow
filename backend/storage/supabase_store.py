"""
Aadhya – Supabase Persistent Storage
Stores enquiries and project summaries to Supabase PostgreSQL.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional

from backend.config import get_settings
from backend.schemas.session import Session

settings = get_settings()

_client = None


def _get_client():
    global _client
    if _client is None and settings.supabase_url and settings.supabase_service_key:
        try:
            from supabase import create_client
            _client = create_client(settings.supabase_url, settings.supabase_service_key)
        except Exception:
            _client = None
    return _client


def is_configured() -> bool:
    return bool(
        settings.supabase_url
        and settings.supabase_service_key
        and settings.supabase_url != "https://your-project.supabase.co"
    )


# ─── SQL to create tables (run once in Supabase) ─────────────────────────────
SCHEMA_SQL = """
-- Enquiries Table
CREATE TABLE IF NOT EXISTS enquiries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    channel TEXT,
    extracted_fields JSONB,
    completed_fields JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Project Summaries Table
CREATE TABLE IF NOT EXISTS project_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    next_step TEXT,
    project_overview TEXT,
    scope_of_work JSONB,
    client_requirements TEXT,
    technical_specs TEXT,
    timeline TEXT,
    special_considerations TEXT,
    estimated_scope TEXT,
    design_direction TEXT,
    execution_readiness TEXT,
    enquiry_snapshot JSONB,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions Log Table (metadata + full session JSON for rehydrate after Redis TTL / new instance)
CREATE TABLE IF NOT EXISTS sessions_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    channel TEXT,
    conversation_stage TEXT,
    field_completion_pct INTEGER,
    turn_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    session_data JSONB
);

-- Required for PostgREST upsert(on_conflict="session_id")
CREATE UNIQUE INDEX IF NOT EXISTS enquiries_session_id_key ON enquiries (session_id);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_log_session_id_key ON sessions_log (session_id);

-- Upgrade existing databases (safe if column already exists):
ALTER TABLE sessions_log ADD COLUMN IF NOT EXISTS session_data JSONB;
"""

# ─── CRUD operations ─────────────────────────────────────────────────────────

def _json_safe(obj: Any) -> Any:
    """Recursively make values JSON-serializable for PostgREST (datetimes → ISO)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return str(obj)


async def save_enquiry(session) -> bool:
    """Save or upsert enquiry data from a session."""
    if not is_configured():
        return False
    try:
        client = _get_client()
        record = {
            "session_id": session.session_id,
            "phone_number": session.phone_number,
            "channel": session.channel,
            "extracted_fields": _json_safe(session.extracted_fields),
            "completed_fields": _json_safe(session.completed_fields),
            "updated_at": datetime.utcnow().isoformat(),
        }
        client.table("enquiries").upsert(record, on_conflict="session_id").execute()
        return True
    except Exception as e:
        print(f"[Supabase] save_enquiry error: {e}")
        return False


async def save_summary(summary, phone_number: str = "") -> bool:
    """Insert a generated project summary."""
    if not is_configured():
        return False
    try:
        client = _get_client()
        record = {
            "session_id": summary.session_id,
            "phone_number": phone_number,
            "next_step": summary.next_step,
            "project_overview": summary.project_overview,
            "scope_of_work": summary.scope_of_work,
            "client_requirements": summary.client_requirements,
            "technical_specs": summary.technical_specs,
            "timeline": summary.timeline,
            "special_considerations": summary.special_considerations,
            "estimated_scope": summary.estimated_scope,
            "design_direction": summary.design_direction,
            "execution_readiness": summary.execution_readiness,
            "enquiry_snapshot": summary.enquiry_snapshot,
            "generated_at": summary.generated_at.isoformat(),
        }
        client.table("project_summaries").insert(record).execute()
        return True
    except Exception as e:
        print(f"[Supabase] save_summary error: {e}")
        return False


async def save_session_snapshot(session: Session) -> bool:
    """
    Persist full session to Supabase so chat survives Redis expiry, deploy restarts,
    and multi-instance setups (rehydrate via load_session_snapshot).
    """
    if not is_configured():
        return False
    try:
        client = _get_client()
        record = {
            "session_id": session.session_id,
            "phone_number": session.phone_number,
            "channel": session.channel,
            "conversation_stage": session.conversation_stage.value,
            "field_completion_pct": session.field_completion_pct,
            "turn_count": session.turn_count,
            "last_active": session.last_active.isoformat(),
            "session_data": session.model_dump(mode="json"),
        }
        client.table("sessions_log").upsert(record, on_conflict="session_id").execute()
        return True
    except Exception as e:
        print(f"[Supabase] save_session_snapshot error: {e}")
        return False


async def load_session_snapshot(session_id: str) -> Optional[Session]:
    """Load full session from Supabase when Redis has no key."""
    if not is_configured():
        return None
    try:
        client = _get_client()
        result = (
            client.table("sessions_log")
            .select("session_data")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        raw = rows[0].get("session_data")
        if not raw:
            return None
        return Session.model_validate(raw)
    except Exception as e:
        print(f"[Supabase] load_session_snapshot error: {e}")
        return None


async def delete_session_snapshot(session_id: str) -> bool:
    """Remove durable snapshot (e.g. RESTART45 or admin reset)."""
    if not is_configured():
        return False
    try:
        client = _get_client()
        client.table("sessions_log").delete().eq("session_id", session_id).execute()
        return True
    except Exception as e:
        print(f"[Supabase] delete_session_snapshot error: {e}")
        return False


async def upsert_session_log(session: Session) -> bool:
    """Alias for save_session_snapshot (same row shape)."""
    return await save_session_snapshot(session)


async def get_all_enquiries() -> list[dict]:
    if not is_configured():
        return []
    try:
        client = _get_client()
        result = client.table("enquiries").select("*").order("updated_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []


async def get_all_summaries() -> list[dict]:
    if not is_configured():
        return []
    try:
        client = _get_client()
        result = client.table("project_summaries").select("*").order("generated_at", desc=True).execute()
        return result.data or []
    except Exception:
        return []
