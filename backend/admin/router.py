"""
Aadhya – Admin API Router
All endpoints backing the /krsna admin panel.
Protected by require_admin dependency.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.admin.auth import require_admin, generate_session_token
from backend.config import get_settings
from backend.questionnaire.summary_serialization import build_quest_completion_summaries
from backend.storage.redis_store import get_session, delete_session, list_all_sessions
from backend.storage import supabase_store
from backend.utils.logger import get_recent_logs
from backend.schemas.session import ConversationStage

settings = get_settings()
router = APIRouter(prefix="/admin", tags=["admin"])

ROUTER_SERVICE_FIELD = "__router:service_id"
QUEST_SERVICE_FIELD = "__quest:service_id"


def _session_service_id(session) -> str:
    meta = getattr(session, "extracted_fields", None)
    if isinstance(meta, dict):
        sid = meta.get(ROUTER_SERVICE_FIELD) or meta.get(QUEST_SERVICE_FIELD)
        if isinstance(sid, str) and sid:
            return sid
    return ""


def _enquiry_service_id(enquiry_row: dict) -> str:
    ef = enquiry_row.get("extracted_fields")
    if isinstance(ef, dict):
        sid = ef.get(ROUTER_SERVICE_FIELD) or ef.get(QUEST_SERVICE_FIELD)
        if isinstance(sid, str) and sid:
            return sid
    return ""

# ─── Auth endpoint (no protection — it IS the login) ─────────────────────────

class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def admin_login(body: LoginRequest):
    """Exchange admin password for a session token."""
    if body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    token = generate_session_token()
    return {"token": token, "expires_in_hours": 8}


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(auth=Depends(require_admin)):
    sessions = await list_all_sessions()
    now = datetime.utcnow()

    active = [s for s in sessions if s.conversation_stage != ConversationStage.SUMMARY_GENERATED]
    completed = [s for s in sessions if s.summary_generated]

    whatsapp_today = sum(1 for s in sessions if s.channel == "whatsapp")
    voice_today = sum(1 for s in sessions if s.channel == "voice")

    # Hourly message distribution (last 24h, from logs)
    logs = get_recent_logs(500)
    hourly = {}
    for entry in logs:
        if entry.get("event") == "USER_MESSAGE":
            try:
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                hour = ts.strftime("%H:00")
                hourly[hour] = hourly.get(hour, 0) + 1
            except Exception:
                pass

    # Service distribution (from in-memory sessions)
    by_service: dict[str, int] = {}
    for s in sessions:
        sid = _session_service_id(s) or ""
        if not sid:
            continue
        by_service[sid] = by_service.get(sid, 0) + 1

    return {
        "stats": {
            "active_sessions": len(active),
            "completed_enquiries": len(completed),
            "summaries_generated": len(completed),
            "whatsapp_conversations_today": whatsapp_today,
            "voice_calls_today": voice_today,
            "total_sessions": len(sessions),
        },
        "charts": {
            "messages_per_hour": hourly,
            "channel_distribution": {
                "whatsapp": whatsapp_today,
                "voice": voice_today,
            },
            "service_distribution": by_service,
        },
        "generated_at": now.isoformat(),
    }


# ─── Sessions ─────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def get_sessions(
    service_id: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    sessions = await list_all_sessions()
    if service_id:
        want = service_id.strip().lower()
        sessions = [s for s in sessions if _session_service_id(s).lower() == want]
    return {
        "sessions": [
            {
                "session_id": s.session_id,
                "phone_number": s.phone_number,
                "channel": s.channel,
                "service_id": _session_service_id(s),
                "persona_key": getattr(s, "persona_key", "") or "",
                "conversation_stage": s.conversation_stage.value,
                "fields_collected": len(s.completed_fields),
                "field_completion_pct": s.field_completion_pct,
                "turn_count": s.turn_count,
                "summary_generated": s.summary_generated,
                "last_active": s.last_active.isoformat(),
                "created_at": s.created_at.isoformat(),
            }
            for s in sorted(sessions, key=lambda x: x.last_active, reverse=True)
        ]
    }


@router.get("/session/{session_id}")
async def get_session_detail(session_id: str, auth=Depends(require_admin)):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "channel": session.channel,
        "conversation_stage": session.conversation_stage.value,
        "completed_fields": session.completed_fields,
        "extracted_fields": session.extracted_fields,
        "field_completion_pct": session.field_completion_pct,
        "turn_count": session.turn_count,
        "summary_generated": session.summary_generated,
        "summary": session.summary,
        "six_point_summary": session.six_point_summary,
        "quest_summaries_camel": build_quest_completion_summaries(session),
        "created_at": session.created_at.isoformat(),
        "last_active": session.last_active.isoformat(),
        "conversation_history": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "extracted_fields": msg.extracted_fields,
            }
            for msg in session.conversation_history
        ],
        "thinking_traces": [
            {
                "turn": t.turn,
                "user_message": t.user_message,
                "detected_fields": t.detected_fields,
                "next_field_target": t.next_field_target,
                "stage_before": t.stage_before.value,
                "stage_after": t.stage_after.value,
                "guardrail_triggered": t.guardrail_triggered,
                "timestamp": t.timestamp.isoformat(),
            }
            for t in session.thinking_traces
        ],
    }


@router.get("/session/{session_id}/quest-summaries")
async def get_session_quest_summaries_camel(session_id: str, auth=Depends(require_admin)):
    """
    Project + six-point summaries in quest-characters camelCase shape (`ProjectSummary`, `SixPointSummary`).
    For main-platform integration; internal storage remains snake_case.
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return build_quest_completion_summaries(session)


# ─── Enquiries ────────────────────────────────────────────────────────────────

@router.get("/enquiries")
async def get_enquiries(
    service_id: Optional[str] = Query(None),
    auth=Depends(require_admin),
):
    # Try Supabase first
    from_db = await supabase_store.get_all_enquiries()
    if from_db:
        if service_id:
            want = service_id.strip().lower()
            from_db = [e for e in from_db if _enquiry_service_id(e).lower() == want]
        return {"enquiries": from_db}

    # Fallback: build from in-memory sessions
    sessions = await list_all_sessions()
    enquiries = [
        {
            "session_id": s.session_id,
            "phone_number": s.phone_number,
            "channel": s.channel,
            "service_id": _session_service_id(s),
            "persona_key": getattr(s, "persona_key", "") or "",
            "extracted_fields": s.extracted_fields,
            "completed_fields": s.completed_fields,
            "completion_pct": s.field_completion_pct,
        }
        for s in sessions if s.extracted_fields
    ]
    if service_id:
        want = service_id.strip().lower()
        enquiries = [e for e in enquiries if str(e.get("service_id") or "").lower() == want]
    return {"enquiries": enquiries}


# ─── Summaries ────────────────────────────────────────────────────────────────

@router.get("/summaries")
async def get_summaries(auth=Depends(require_admin)):
    from_db = await supabase_store.get_all_summaries()
    if from_db:
        return {"summaries": from_db}

    sessions = await list_all_sessions()
    return {
        "summaries": [
            s.summary for s in sessions if s.summary_generated and s.summary
        ]
    }


# ─── Logs ─────────────────────────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(
    session_id: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    auth=Depends(require_admin),
):
    logs = get_recent_logs(limit)
    if session_id:
        logs = [l for l in logs if l.get("session_id") == session_id]
    if event:
        logs = [l for l in logs if l.get("event") == event]
    return {"logs": logs, "count": len(logs)}


# ─── System Health ────────────────────────────────────────────────────────────

@router.get("/health")
async def get_health(auth=Depends(require_admin)):
    import httpx
    checks = {}

    # LLM (primary path)
    try:
        # Exercise the same router used by production flows.
        from backend.intelligence.llm_engine import get_llm_engine
        engine = get_llm_engine()
        # Minimal “ping” that triggers a provider call.
        ping = await engine.extract_json(
            session_id="system_health",
            extraction_prompt="Return ONLY valid JSON: {\"status\": \"ok\"}",
        )
        if not isinstance(ping, dict) or ping.get("status") != "ok":
            raise RuntimeError("LLM ping failed (no valid JSON status). Check provider config/model.")
        checks["llm"] = {"status": "ok", "provider": settings.llm_provider}
    except Exception as e:
        checks["llm"] = {"status": "error", "error": str(e)[:140], "provider": settings.llm_provider}

    # Upstash Redis
    try:
        from backend.storage.redis_store import get_redis_store
        store = get_redis_store()
        if store.is_configured():
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{settings.upstash_redis_rest_url}/ping",
                                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"})
                checks["redis"] = {"status": "ok" if r.status_code == 200 else "error"}
        else:
            checks["redis"] = {"status": "not_configured", "mode": "in_memory_fallback"}
    except Exception as e:
        checks["redis"] = {"status": "error", "error": str(e)[:80]}

    # Supabase
    try:
        if supabase_store.is_configured():
            client = supabase_store._get_client()
            client.table("project_summaries").select("id").limit(1).execute()
            checks["supabase"] = {"status": "ok"}
        else:
            checks["supabase"] = {"status": "not_configured"}
    except Exception as e:
        checks["supabase"] = {"status": "error", "error": str(e)[:80]}

    # Twilio
    checks["twilio"] = {
        "status": "configured" if settings.twilio_account_sid else "not_configured"
    }

    # Vapi
    checks["vapi"] = {
        "status": "configured" if settings.vapi_api_key else "not_configured"
    }

    # ElevenLabs
    checks["elevenlabs"] = {
        "status": "configured" if settings.elevenlabs_api_key else "not_configured"
    }

    overall = "healthy" if all(
        v.get("status") in ("ok", "configured", "not_configured")
        for v in checks.values()
    ) else "degraded"

    return {"overall": overall, "services": checks, "checked_at": datetime.utcnow().isoformat()}


# ─── Live SSE Stream ──────────────────────────────────────────────────────────

@router.get("/stream")
async def live_stream(request: Request, auth=Depends(require_admin)):
    """Server-Sent Events stream for live admin monitor feed."""
    from backend.storage.redis_store import get_redis_store

    async def event_generator():
        store = get_redis_store()
        last_count = 0
        yield "data: {\"event\": \"connected\", \"message\": \"Live monitor active\"}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                logs = get_recent_logs(20)
                if len(logs) != last_count:
                    new_logs = logs[: len(logs) - last_count] if last_count > 0 else logs[:5]
                    for log in reversed(new_logs):
                        yield f"data: {json.dumps(log)}\n\n"
                    last_count = len(logs)
            except Exception:
                pass
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Manual Controls ──────────────────────────────────────────────────────────

@router.post("/session/{session_id}/reset")
async def reset_session(session_id: str, auth=Depends(require_admin)):
    """Delete session from store — client starts fresh on next message."""
    await delete_session(session_id)
    return {"status": "reset", "session_id": session_id}


@router.post("/session/{session_id}/force-summary")
async def force_summary(session_id: str, auth=Depends(require_admin)):
    """Force summary generation for a session, even if not all fields are collected."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from backend.summarizer.summary_generator import get_summary_generator
    from backend.storage.redis_store import save_session
    summarizer = get_summary_generator()
    summary = await summarizer.generate(session)
    session.summary = summary.model_dump()
    session.summary_generated = True
    await save_session(session)
    return {"status": "summary_generated", "summary": session.summary}


@router.post("/session/{session_id}/close")
async def close_session(session_id: str, auth=Depends(require_admin)):
    """Mark session as closed (summary_generated=True) without generating a summary."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from backend.schemas.session import ConversationStage
    from backend.storage.redis_store import save_session
    session.conversation_stage = ConversationStage.SUMMARY_GENERATED
    await save_session(session)
    return {"status": "closed", "session_id": session_id}
