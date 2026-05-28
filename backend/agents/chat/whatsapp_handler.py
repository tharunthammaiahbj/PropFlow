"""
Aadhya – WhatsApp Webhook Handler (Twilio)
Receives messages, routes through ConversationController, sends responses.
"""
from __future__ import annotations
from datetime import datetime
import asyncio
import time
import re
import hashlib

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response

from backend.config import get_settings
from backend.schemas.session import Session, ConversationStage
from backend.intelligence.conversation_controller import get_controller
from backend.intelligence.persona import get_opening_chat_message_by_persona_key, get_opening_chat_message
from backend.intelligence.service_registry import normalize_service_code, resolve_persona_key
from backend.storage.redis_store import get_session, save_session, delete_session, get_redis_store
from backend.storage import supabase_store
from backend.agents.chat.twilio_client import twiml_response, send_whatsapp_message
from backend.utils.logger import log_event
from backend.utils.perf_analytics import emit_channel_turn_timing
from backend.questionnaire.conversation_engine import QUEST_PARAMETERS

router = APIRouter()
_settings = get_settings()

# Post-completion WhatsApp messages can cause repetitive closings.
# Requirement: once the enquiry is complete, stop "AI working again" on WhatsApp.
# We allow at most one short acknowledgement reply, then ignore additional messages for a window.
_WA_POST_COMPLETE_ACK_RE = re.compile(
    r"^(?:ok(?:ay)?|k{1,2}|done|thanks|thank you|great|cool|got it|yep|yeah|yes)"
    r"(?:\b.*)?$",
    re.I,
)
_WA_POST_COMPLETE_SILENCE_SECONDS = 10 * 60  # 10 minutes

# Fallback per-session lock when Redis is not configured.
_local_locks: dict[str, asyncio.Lock] = {}
_local_locks_guard = asyncio.Lock()

# Fallback idempotency cache when Redis is not configured.
# Twilio retries the same inbound message; without shared Redis, we can still dedupe
# within a single process to avoid obvious double-responses.
_local_idem: dict[str, float] = {}
_local_idem_guard = asyncio.Lock()
_LOCAL_IDEM_TTL_SECONDS = 6 * 3600


async def _get_local_lock(session_id: str) -> asyncio.Lock:
    async with _local_locks_guard:
        lock = _local_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            _local_locks[session_id] = lock
        return lock


def _public_url_for_twilio_validation(request: Request) -> str:
    """
    Twilio's RequestValidator must use the exact URL Twilio signed (public https).
    Behind Railway / other TLS terminators, Starlette often exposes request.url as
    http://... which makes validate() always fail with a correct token.
    """
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    proto_raw = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    if proto_raw in ("http", "https"):
        proto = proto_raw
    elif host:
        # TLS terminator in front; client-facing URL is almost always https
        proto = "https"
    else:
        proto = (request.url.scheme or "https").split(",")[0].strip()
    if proto not in ("http", "https"):
        proto = "https"
    if not host:
        return str(request.url)
    path = request.url.path or ""
    query = request.url.query
    if query:
        return f"{proto}://{host}{path}?{query}"
    return f"{proto}://{host}{path}"


async def _verify_twilio_signature(request: Request) -> None:
    """
    FastAPI dependency that validates the X-Twilio-Signature header.
    If TWILIO_AUTH_TOKEN is not set (local dev), validation is skipped.
    Raises HTTP 403 on tampered/spoofed requests.
    """
    token = _settings.twilio_auth_token
    if not token or token in ("your_twilio_auth_token", ""):
        return  # Skip in local dev / unconfigured environments

    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        return  # twilio not installed — skip silently

    signature = request.headers.get("X-Twilio-Signature", "")
    url = _public_url_for_twilio_validation(request)
    # Twilio passes form data — read it as dict for validation
    form = await request.form()
    params = dict(form)

    validator = RequestValidator(token)
    if not validator.validate(url, params, signature):
        await log_event(
            "SECURITY_VIOLATION",
            session_id="system",
            data={"reason": "invalid_twilio_signature", "url": url, "raw_request_url": str(request.url)},
        )
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str | None = Form(None),
    _: None = Depends(_verify_twilio_signature),
):
    """
    Twilio sends POST with Form fields: From (whatsapp:+91...), Body (message text).
    We return TwiML XML to reply.
    """
    phone_number = From  # e.g. "whatsapp:+919876543210"
    user_message = Body.strip()
    session_id = f"wa_{phone_number}"

    # Optional: allow a query param override for web integrations/tests.
    service_code = normalize_service_code(request.query_params.get("service_code"))
    persona_key = resolve_persona_key(service_code) if service_code else None

    # ─── Idempotency (Twilio retries) ───────────────────────────────────────
    # If Twilio retries the same inbound message, don't double-process and mutate state twice.
    if MessageSid:
        store = get_redis_store()
        if store.is_configured():
            idem_key = f"idem:twilio:{MessageSid}"
            ok = await store.set_nx(idem_key, "1", ex_seconds=6 * 3600)
            if not ok:
                # Already processed: return empty 200 TwiML to stop retry loops
                return Response(content=twiml_response(""), media_type="application/xml")
        else:
            # Local best-effort dedupe (single instance only).
            now = asyncio.get_event_loop().time()
            async with _local_idem_guard:
                # Opportunistic cleanup
                expire_before = now - _LOCAL_IDEM_TTL_SECONDS
                if len(_local_idem) > 2000:
                    for k, ts in list(_local_idem.items()):
                        if ts < expire_before:
                            _local_idem.pop(k, None)
                if MessageSid in _local_idem and _local_idem[MessageSid] >= expire_before:
                    return Response(content=twiml_response(""), media_type="application/xml")
                _local_idem[MessageSid] = now

    # ─── Short-window body dedupe (covers retries with new MessageSid) ──────
    # Rarely, the same inbound WhatsApp message can be delivered twice with different SIDs
    # (or users double-tap send). We dedupe identical bodies per sender within a very short
    # window to prevent duplicate specialist welcomes / repeated turns.
    try:
        body_norm = " ".join((user_message or "").strip().lower().split())
        if body_norm:
            digest = hashlib.sha1(body_norm.encode("utf-8")).hexdigest()[:12]
            store2 = get_redis_store()
            if store2.is_configured():
                body_key = f"idem:wa:{session_id}:{digest}"
                ok2 = await store2.set_nx(body_key, "1", ex_seconds=12)
                if not ok2:
                    return Response(content=twiml_response(""), media_type="application/xml")
    except Exception:
        pass

    # ─── Per-session lock (fast double messages) ────────────────────────────
    # Prevent two concurrent requests from the same user corrupting the session.
    lock_store = get_redis_store()
    lock_key = f"lock:{session_id}"
    lock_acquired = False
    if lock_store.is_configured():
        for _ in range(5):
            if await lock_store.set_nx(lock_key, "1", ex_seconds=15):
                lock_acquired = True
                break
            await asyncio.sleep(0.2)
        if not lock_acquired:
            # Redis is configured (shared), but we couldn't acquire the lock.
            # Processing anyway would allow concurrent mutation and cause repeats/races.
            return Response(content=twiml_response(""), media_type="application/xml")
    local_lock: asyncio.Lock | None = None
    if not lock_acquired:
        local_lock = await _get_local_lock(session_id)
        await local_lock.acquire()
    try:
        t_wall0 = time.perf_counter()
        t_seg0 = time.perf_counter()
        # Load or create session
        session = await get_session(session_id)
        get_session_ms = (time.perf_counter() - t_seg0) * 1000.0

        # ─── RESTART45: Reset session for testing ─────────────────────────────
        if user_message.upper() == "RESTART45":
            await delete_session(session_id)
            await log_event("SESSION_RESET", session_id=session_id,
                            data={"reason": "RESTART45_command"})
            # Create a brand new session
            new_session = Session(
                session_id=session_id,
                phone_number=phone_number,
                channel="whatsapp",
                conversation_stage=ConversationStage.DISCOVERY,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            new_session.extracted_fields = {"__wa:stage": "PRIYA_SERVICE_PICK", "__wa:first_message": True}
            # WhatsApp channel: we already know the user is on WhatsApp, so never ask contact preference.
            new_session.extracted_fields[QUEST_PARAMETERS] = {
                "contact_pref": {"value": "whatsapp", "confidence": 1.0, "ts": datetime.utcnow().isoformat() + "Z"}
            }
            if service_code:
                new_session.service_code = service_code
                new_session.persona_key = persona_key
            # Immediately send Priya's opener (LLM-generated), like the voice agent.
            controller = get_controller()
            resp = await controller.process_message(session=new_session, user_message="", channel="whatsapp")
            await save_session(resp.session)
            return Response(content=twiml_response(resp.text), media_type="application/xml")

        if session is None:
            session = Session(
                session_id=session_id,
                phone_number=phone_number,
                channel="whatsapp",
                conversation_stage=ConversationStage.DISCOVERY,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            if service_code:
                session.service_code = service_code
                session.persona_key = persona_key
            # WhatsApp channel: we already know the user is on WhatsApp, so never ask contact preference.
            session.extracted_fields = session.extracted_fields or {}
            session.extracted_fields.setdefault("__wa:stage", "PRIYA_SERVICE_PICK")
            session.extracted_fields.setdefault("__wa:first_message", True)
            session.extracted_fields[QUEST_PARAMETERS] = {
                "contact_pref": {"value": "whatsapp", "confidence": 1.0, "ts": datetime.utcnow().isoformat() + "Z"}
            }
            await log_event("SESSION_START", session_id=session_id,
                            data={"phone": phone_number, "channel": "whatsapp"})
            # Do not return early: a missing session (new user OR Redis/TTL expiry) must still
            # process this Body, or the user's text is dropped and they only see the canned opening.
        else:
            # Persist routing once, if provided and not already set.
            if service_code and not session.service_code:
                session.service_code = service_code
            if persona_key and not session.persona_key:
                session.persona_key = persona_key

        # ─── WhatsApp-only: stop post-completion repetition ───────────────────
        # If the enquiry is already completed, do not re-run the controller and do not
        # keep sending closings. Reply once (optional), then stay silent for a window.
        if getattr(session, "summary_generated", False):
            norm = " ".join((user_message or "").lower().split())
            meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
            now_ts = datetime.utcnow().timestamp()
            last_any_ts = float(meta.get("__wa:post_complete_last_ts") or 0.0)
            last_any_norm = str(meta.get("__wa:post_complete_last_norm") or "")

            # If we responded (or decided to ignore) recently, stay silent.
            if last_any_ts and (now_ts - last_any_ts) < _WA_POST_COMPLETE_SILENCE_SECONDS:
                meta["__wa:post_complete_last_norm"] = norm
                meta["__wa:post_complete_last_ts"] = now_ts
                session.extracted_fields = meta
                await save_session(session)
                return Response(content=twiml_response(""), media_type="application/xml")

            # First post-completion message: if it's an acknowledgement, send one final short reply.
            if norm and _WA_POST_COMPLETE_ACK_RE.match(norm):
                reply = "Perfect — we already have everything. You're all set; the right PropFlow vendor will contact you shortly."
                meta["__wa:post_complete_last_norm"] = norm
                meta["__wa:post_complete_last_ts"] = now_ts
                meta["__wa:post_complete_replied"] = True
                session.extracted_fields = meta
                await save_session(session)
                return Response(content=twiml_response(reply), media_type="application/xml")

            # If it's not an acknowledgement (user asks something else), keep it strict:
            # do not re-open the completed enquiry; stay silent to prevent loops.
            meta["__wa:post_complete_last_norm"] = norm
            meta["__wa:post_complete_last_ts"] = now_ts
            session.extracted_fields = meta
            await save_session(session)
            return Response(content=twiml_response(""), media_type="application/xml")

        # Process message through controller
        controller = get_controller()
        try:
            t_ctrl = time.perf_counter()
            agent_response = await controller.process_message(
                session=session,
                user_message=user_message,
                channel="whatsapp",
            )
            controller_ms = (time.perf_counter() - t_ctrl) * 1000.0
        except Exception as e:
            await log_event("API_ERROR", session_id=session_id,
                            data={"error": str(e), "phase": "whatsapp_handler"})
            fallback = "Could you give me just a moment? I'm just pulling your details together."
            await save_session(session)
            return Response(content=twiml_response(fallback), media_type="application/xml")

        # Persist session
        t_save = time.perf_counter()
        await save_session(agent_response.session)
        save_session_ms = (time.perf_counter() - t_save) * 1000.0

        supabase_ms = 0.0
        # Persist to Supabase on summary generation
        if agent_response.summary_generated and agent_response.session.summary:
            t_sb = time.perf_counter()
            await supabase_store.save_enquiry(agent_response.session)
            try:
                from backend.schemas.summary import ProjectSummary
                summary_obj = ProjectSummary.model_validate(agent_response.session.summary)
                await supabase_store.save_summary(summary_obj, phone_number=phone_number)
            except Exception:
                pass
            supabase_ms = (time.perf_counter() - t_sb) * 1000.0
            try:
                from backend.questionnaire.completion_webhook import schedule_questionnaire_completion_webhook
                from backend.questionnaire.completion_webhook import schedule_enquiry_webhook
                from backend.questionnaire.conversation_engine import ensure_quest_service

                qsid = ensure_quest_service(agent_response.session)
                schedule_questionnaire_completion_webhook(agent_response.session, service_id=qsid)
                schedule_enquiry_webhook(agent_response.session, service_id=qsid)
            except Exception:
                pass

        wall_clock_ms = (time.perf_counter() - t_wall0) * 1000.0
        await emit_channel_turn_timing(
            session_id,
            channel="whatsapp",
            segments_ms={
                "redis_get_session_ms": get_session_ms,
                "controller_process_message_ms": controller_ms,
                "redis_save_session_ms": save_session_ms,
                "supabase_persist_ms": supabase_ms,
            },
            extra={
                "summary_generated": agent_response.summary_generated,
                "wall_clock_ms": round(wall_clock_ms, 3),
            },
        )

        return Response(
            content=twiml_response(agent_response.text),
            media_type="application/xml",
        )
    finally:
        if local_lock and local_lock.locked():
            local_lock.release()
        if lock_acquired and lock_store.is_configured():
            await lock_store.delete_key(lock_key)

