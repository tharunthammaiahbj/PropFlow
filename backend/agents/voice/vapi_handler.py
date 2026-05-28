"""
Aadhya – Vapi Voice Webhook Handler
Processes Vapi call events and routes through the ConversationController.
"""
from __future__ import annotations
import json
import re
import uuid
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Request, HTTPException

from backend.schemas.session import Session, ConversationStage, MessageRole
from backend.intelligence.conversation_controller import get_controller
from backend.intelligence.persona import get_opening_voice_message_by_persona_key, get_opening_voice_message
from backend.intelligence.service_registry import normalize_service_code, resolve_persona_key
from backend.storage.redis_store import get_session, save_session, delete_session
from backend.storage import supabase_store
from backend.agents.voice.voice_response_optimizer import (
    optimize_for_voice,
    detect_leading_ack,
    strip_leading_ack,
)
from backend.utils.logger import log_event

router = APIRouter()

# Voice sessions must be scoped to a single Vapi call. If Vapi ever sends a webhook
# without `call.id`, we MUST NOT fall back to a shared stable id like "unknown_call"
# (that causes session collisions across real calls and leaks `summary_generated=True`
# into brand-new calls). We use a per-request UUID fallback and record `__voice:call_id`
# inside the session for mismatch detection.
VOICE_CALL_ID_KEY = "__voice:call_id"
VOICE_FAREWELL_SENT_KEY = "__voice:farewell_sent"
# FIX 5 — Empty stream fallback variation
VOICE_LAST_FALLBACK_KEY = "__voice:lastFallback"
VOICE_LAST_FALLBACK_Q_KEY = "__voice:lastFallbackQuestion"
_EMPTY_STREAM_FALLBACK_PREFIXES = [
    "One sec — could you say that again?",
    "Sorry, the line cut for a moment — could you repeat?",
    "Didn't quite get that — say it once more?",
    "Sorry, I missed that — could you spell it out?",
]

# Phase 1 receptionist (voice): this is the only line Vapi should speak at call start.
# The correct specialist introduction is produced on the FIRST real user utterance
# after routing + quest engine opening.
VOICE_RECEPTIONIST_FIRST_MESSAGE = "Hello, welcome to PropFlow. How can I help you today?"
VOICE_ROUTER_CLARIFY_MESSAGE = (
    "Hi, I’m Jessica from PropFlow. What can I help you with today—"
    "interiors, construction, painting, solar, plumbing, electrical, or home automation?"
)

# If routing is still unclear after the first clarify, switch to an even shorter prompt
# to avoid repeating the same pitch and to reduce ASR confusion.
VOICE_ROUTER_CLARIFY_MESSAGE_SHORT = (
    "Sorry — which service is this for? You can say a full sentence like “solar for my home”, or just say: solar, interiors, construction, painting, plumbing, electrical, or automation."
)


def _service_intro_line(service_id: str, persona_key: str | None) -> str:
    """
    One-time specialist intro after service lock.
    Keep it short (voice), but include the character's name like legacy openings.
    """
    from backend.intelligence.persona import get_opening_voice_message_by_persona_key
    from backend.intelligence.service_registry import QUEST_SERVICE_REGISTRY

    sid = (service_id or "").strip().lower()
    pk = (persona_key or "").strip() or None
    # Reuse the legacy persona opening first sentence for name+service consistency.
    opening = get_opening_voice_message_by_persona_key(pk)
    first_sentence = (opening.split(".")[0].strip() + ".") if opening else ""

    manifest = QUEST_SERVICE_REGISTRY.get(sid) or {}
    service_label = str(manifest.get("webhook_service_name") or sid.replace("_", " ")).strip()
    if not first_sentence:
        first_sentence = f"Hello, this is Jessica from PropFlow {service_label}."

    # Follow-up is short, deterministic, and avoids asking a new question here.
    return f"{first_sentence} I’ll ask a couple quick questions to guide you properly."

# Short farewell-only utterances (no questionnaire content). Used so Vapi does not hang up
# mid-brief via endCallPhrases; we handle these in /chat/completions while fields are incomplete.
_GOODBYE_ONLY = re.compile(
    r"^(?:(?:ok|okay|thanks|thank you)\s+)?"
    r"(?:bye|goodbye|good bye|bye-?bye|see you(?: later)?|talk to you later|ciao|gotta go)"
    r"(?:\s*[.!])*$",
    re.I,
)


def _voice_message_is_goodbye_only(msg: str) -> bool:
    s = (msg or "").strip()
    if not s or len(s) > 120:
        return False
    return bool(_GOODBYE_ONLY.match(s))


def _request_includes_vapi_end_call_tool(body: dict[str, Any]) -> bool:
    """True when Vapi attached the default endCall tool to this chat/completions request."""
    for t in body.get("tools") or []:
        if not isinstance(t, dict):
            continue
        if t.get("type") == "endCall":
            return True
        fn = t.get("function")
        if isinstance(fn, dict) and fn.get("name") == "endCall":
            return True
    return False


def _maybe_merge_recent_voice_transcript(session: Session, new_user_text: str) -> bool:
    """
    Vapi/ASR can send a partial transcript followed quickly by a longer "final" transcript.
    If we already responded to the partial, merge it to avoid duplicate turns / repeated intros.

    Returns True when the session transcript was modified (merged).
    """
    s = (new_user_text or "").strip()
    if not s:
        return False
    hist = session.conversation_history
    if len(hist) < 2:
        return False

    # We only attempt to merge when the last two items are USER then ASSISTANT,
    # which is the "we already replied" shape.
    last = hist[-1]
    prev = hist[-2]
    if prev.role != MessageRole.USER or last.role != MessageRole.ASSISTANT:
        return False

    prev_text = (prev.content or "").strip()
    if not prev_text:
        return False

    # Merge only if the new transcript is a near-immediate expansion of the previous.
    # This catches: "Hello." -> "Hello. Who is this?"
    try:
        dt = abs((prev.timestamp - datetime.utcnow()).total_seconds())
    except Exception:
        dt = 999.0
    if dt > 2.0:
        return False

    prev_norm = re.sub(r"\s+", " ", prev_text).strip().lower()
    new_norm = re.sub(r"\s+", " ", s).strip().lower()
    if prev_norm == new_norm:
        return False
    if not (new_norm.startswith(prev_norm) or prev_norm in new_norm):
        return False
    if len(new_norm) <= len(prev_norm) + 3:
        return False

    # Merge: replace the previous USER text and remove the ASSISTANT reply that was generated for the partial.
    prev.content = s
    hist.pop()
    session.last_active = datetime.utcnow()
    return True


@router.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    """
    Vapi sends JSON POST with a 'message' object.
    We handle transcript events and return assistant.say responses.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = body.get("message", {})
    msg_type = message.get("type", "")

    # ─── Handle call start ────────────────────────────────────────────────
    if msg_type == "assistant-request":
        # Vapi is asking for assistant config — return our voice config
        return _assistant_config_response(VOICE_RECEPTIONIST_FIRST_MESSAGE)

    # ─── Handle transcripts ───────────────────────────────────────────────
    if msg_type == "transcript":
        # We no longer process AI logic here, because Vapi Custom LLM
        # sends requests directly to the /chat/completions endpoint.
        # This event is just for monitoring if needed.
        return {"results": []}

    # ─── Handle end-of-call ───────────────────────────────────────────────
    if msg_type == "end-of-call-report":
        call = body.get("call", {})
        call_id = call.get("id", "unknown")
        session_id = f"voice_{call_id}"
        await log_event("CALL_ENDED", session_id=session_id,
                        data={"event": "call_ended", "call_id": call_id})
        return {"status": "ok"}

    return {"results": []}


def _say_response(text: str) -> dict:
    """Vapi response format to make the assistant speak."""
    return {
        "results": [{
            "toolCallId": "aadhya_response",
            "result": text,
        }]
    }


@router.post("/webhook/vapi/chat/completions")
async def vapi_chat_completions(request: Request):
    """
    Vapi Custom LLM endpoint.
    Vapi calls this to get the next assistant message.
    It expects an OpenAI-compatible /chat/completions response.
    Supports both streaming (SSE) and non-streaming responses.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    is_streaming = body.get("stream", False)
    from backend.config import get_settings
    settings = get_settings()

    # Allow website / Vapi metadata to pass service_code for persona routing.
    service_code = (
        body.get("service_code")
        or body.get("metadata", {}).get("service_code")
        or request.query_params.get("service_code")
    )
    service_code = normalize_service_code(service_code)
    persona_key = resolve_persona_key(service_code) if service_code else None
    opening_message = get_opening_voice_message_by_persona_key(
        persona_key,
        default_persona=settings.consultant_persona,
    )

    # Find the latest user message
    messages = body.get("messages", [])
    if not messages:
        # Seed session transcript with the same spoken receptionist firstMessage so the quest engine
        # does not generate a second greeting on the first real user utterance.
        call = body.get("call", {}) or {}
        call_id = call.get("id", "unknown_call")
        phone = call.get("customer", {}).get("number", call_id)
        session_id = f"voice_{call_id}"
        session = await get_session(session_id)
        if session is None:
            session = Session(
                session_id=session_id,
                phone_number=phone,
                channel="voice",
                conversation_stage=ConversationStage.DISCOVERY,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            if service_code:
                session.service_code = service_code
                session.persona_key = persona_key
        else:
            if service_code and not session.service_code:
                session.service_code = service_code
            if persona_key and not session.persona_key:
                session.persona_key = persona_key

        if not any(m.role == MessageRole.ASSISTANT for m in session.conversation_history):
            session.add_message(MessageRole.SYSTEM, VOICE_RECEPTIONIST_FIRST_MESSAGE)
        await save_session(session)
        return _build_response(VOICE_RECEPTIONIST_FIRST_MESSAGE, is_streaming)

    last_user_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            # content can be a string or a list of content parts
            if isinstance(content, list):
                last_user_msg = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                ).strip()
            else:
                last_user_msg = content.strip()
            break

    if not last_user_msg:
        call = body.get("call", {}) or {}
        call_id = call.get("id", "unknown_call")
        phone = call.get("customer", {}).get("number", call_id)
        session_id = f"voice_{call_id}"
        session = await get_session(session_id)
        if session is None:
            session = Session(
                session_id=session_id,
                phone_number=phone,
                channel="voice",
                conversation_stage=ConversationStage.DISCOVERY,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            if service_code:
                session.service_code = service_code
                session.persona_key = persona_key
        else:
            if service_code and not session.service_code:
                session.service_code = service_code
            if persona_key and not session.persona_key:
                session.persona_key = persona_key

        if not any(m.role == MessageRole.ASSISTANT for m in session.conversation_history):
            session.add_message(MessageRole.SYSTEM, VOICE_RECEPTIONIST_FIRST_MESSAGE)
        await save_session(session)
        return _build_response(VOICE_RECEPTIONIST_FIRST_MESSAGE, is_streaming)

    # Build session ID from call data
    call = body.get("call", {})
    call_id = call.get("id")
    if not isinstance(call_id, str) or not call_id.strip():
        # Hard safety net: never allow "unknown_call" collisions.
        call_id = f"generated_{uuid.uuid4().hex}"
        await log_event(
            "CALL_ID_MISSING",
            session_id=f"voice_{call_id}",
            data={"reason": "missing call.id", "has_call_obj": bool(call), "keys": list(body.keys())[:12]},
        )
    call_id = call_id.strip()
    phone = call.get("customer", {}).get("number", call_id)
    session_id = f"voice_{call_id}"

    # Load or create session
    session = await get_session(session_id)
    if session is None:
        # Resume after dropped call: if we have an incomplete session for this phone, load it.
        prior_id: str | None = None
        try:
            from backend.storage.redis_store import get_redis_store

            prior_id = await get_redis_store().get_incomplete_session_id_for_phone(phone)
        except Exception:
            prior_id = None

        if prior_id and prior_id != session_id:
            resumed = await get_session(prior_id)
            # Only resume very recent, incomplete sessions. Never resume a completed
            # session (summary_generated=True), and never resume something stale.
            is_recent = False
            try:
                if resumed is not None and getattr(resumed, "last_active", None):
                    age_s = (datetime.utcnow() - resumed.last_active).total_seconds()
                    is_recent = age_s <= 15 * 60
            except Exception:
                is_recent = False

            if resumed is not None and (not getattr(resumed, "summary_generated", False)) and is_recent:
                await log_event(
                    "SESSION_RESUMED",
                    session_id=prior_id,
                    data={"new_call_id": call_id, "phone": phone},
                )
                # Carry the prior session state forward into this call's session id.
                resumed.extracted_fields = dict(resumed.extracted_fields or {})
                resumed.extracted_fields["__voice:resumed_from"] = prior_id
                resumed.extracted_fields[VOICE_CALL_ID_KEY] = call_id
                resumed.session_id = session_id
                session = resumed
                await save_session(session)

        if session is None:
            session = Session(
                session_id=session_id,
                phone_number=phone,
                channel="voice",
                conversation_stage=ConversationStage.DISCOVERY,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            if service_code:
                session.service_code = service_code
                session.persona_key = persona_key
            session.extracted_fields = dict(session.extracted_fields or {})
            session.extracted_fields[VOICE_CALL_ID_KEY] = call_id
            # Persist immediately so concurrent / near-duplicate requests don't both create a "new" session.
            await save_session(session)
            await log_event(
                "SESSION_START",
                session_id=session_id,
                data={"phone": phone, "channel": "voice"},
            )
    else:
        # If Vapi reuses call ids or we ever collided due to missing call.id, prevent
        # cross-call leakage: a session's recorded call_id must match the request's.
        meta_existing = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
        recorded_call_id = str(meta_existing.get(VOICE_CALL_ID_KEY) or "").strip()
        if recorded_call_id and recorded_call_id != call_id:
            await log_event(
                "SESSION_CALL_ID_MISMATCH_RESET",
                session_id=session_id,
                data={"recorded_call_id": recorded_call_id, "request_call_id": call_id, "phone": phone},
            )
            await delete_session(session_id)
            await log_event(
                "SESSION_STALE_KEY_DELETED",
                session_id=session_id,
                data={"deleted_session_id": session_id, "recorded_call_id": recorded_call_id, "request_call_id": call_id},
            )
            session = Session(
                session_id=session_id,
                phone_number=phone,
                channel="voice",
                conversation_stage=ConversationStage.DISCOVERY,
                created_at=datetime.utcnow(),
                last_active=datetime.utcnow(),
            )
            session.extracted_fields = {VOICE_CALL_ID_KEY: call_id}
            await save_session(session)
        # Persist routing once, if provided and not already set.
        if service_code and not session.service_code:
            session.service_code = service_code
        if persona_key and not session.persona_key:
            session.persona_key = persona_key
        meta_existing2 = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
        if isinstance(meta_existing2, dict) and not meta_existing2.get(VOICE_CALL_ID_KEY):
            meta_existing2[VOICE_CALL_ID_KEY] = call_id
            session.extracted_fields = meta_existing2

    # Capture whether the session already has ANY prior assistant message BEFORE we
    # mutate anything on this turn (ASR merge, routing, add_message, etc.).
    #
    # This is the signal the quest engine uses (`prior_assistant` in
    # `_quest_pre_reply_phases`) to decide whether to run its OPENING_PROMPT phase.
    # When True → opening runs, producing a persona-rich self-intro + first question
    # ("Hi! I'm Claire Foster, your Solar Services consultant. What type of...").
    # When False → the engine skips opening and jumps straight to the next question.
    #
    # Why we need this flag here: on the session's very first assistant turn BOTH
    # paths were firing (deterministic `_service_intro_line` below AND the LLM
    # opening), causing the stacked intro bug. We now gate the deterministic
    # intro on this flag so it only fires for mid-conversation service SWITCHES
    # (when the engine won't produce its own opening).
    had_prior_assistant_before_turn = any(
        getattr(m, "role", None) == MessageRole.ASSISTANT
        for m in (session.conversation_history or [])
    )

    # If ASR produced a partial transcript and then a longer one, merge to avoid duplicate turns.
    # If a merge happens, persist the corrected transcript before processing.
    if _maybe_merge_recent_voice_transcript(session, last_user_msg):
        await save_session(session)

    # Idempotency guard: Vapi may retry / send duplicates. If we just handled the same user text,
    # replay the last assistant text instead of generating a new turn.
    now_ts = datetime.utcnow().timestamp()
    norm_user = re.sub(r"\s+", " ", (last_user_msg or "").strip().lower())
    meta = session.extracted_fields
    if isinstance(meta, dict):
        last_norm = str(meta.get("__voice:last_user_norm") or "")
        last_assistant = str(meta.get("__voice:last_assistant_text") or "")
        last_ts = float(meta.get("__voice:last_turn_ts") or 0.0)
        if norm_user and last_norm == norm_user and last_assistant and (now_ts - last_ts) < 6.0:
            return _build_response(optimize_for_voice(last_assistant), is_streaming)

    # ── POST-COMPLETION HARD GUARD ──────────────────────────────────────
    # Once the questionnaire is complete (summary_generated=True) the PREVIOUS
    # turn already emitted an endCall tool-call frame. Vapi should have hung up.
    # In production (12:31:30 in the 2026-04-24 transcript) we observed Vapi
    # delivering ONE more /chat/completions request after endCall — either the
    # TTS hadn't drained when the caller spoke again, or Vapi's endCall handshake
    # raced with the new user audio. Running the full pipeline on that stray turn
    # re-awakens the classifier + off-topic redirect ("I wish I could help with
    # that... When can we call you back?"), which is exactly the bug.
    #
    # We short-circuit here BEFORE routing / controller so: no new LLM calls,
    # no conversation-history mutation, and no risk of the session drifting back
    # into a questioning state. We re-emit the endCall tool-call frame so Vapi
    # eventually hangs up even if it missed the first signal.
    if getattr(session, "summary_generated", False):
        await log_event(
            "POST_COMPLETION_TURN_BLOCKED",
            session_id=session_id,
            data={"message_preview": (last_user_msg or "")[:80]},
        )
        meta_pc = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
        # Only speak the farewell ONCE. If Vapi sends multiple stray webhook turns
        # after completion, staying silent is better than repeating "Thanks again"
        # and sounding broken/robotic.
        if isinstance(meta_pc, dict) and meta_pc.get(VOICE_FAREWELL_SENT_KEY):
            silent = ""
            end_call = _request_includes_vapi_end_call_tool(body)
            if is_streaming:
                return _openai_stream_response_with_end_call(silent, emit_end_call=end_call)
            if end_call:
                return _openai_response_with_end_call(silent)
            return _openai_response(silent)

        farewell = optimize_for_voice("Thanks again — have a great day!")
        if isinstance(meta_pc, dict):
            meta_pc[VOICE_FAREWELL_SENT_KEY] = True
            session.extracted_fields = meta_pc
            await save_session(session)
        end_call = _request_includes_vapi_end_call_tool(body)
        if is_streaming:
            return _openai_stream_response_with_end_call(farewell, emit_end_call=end_call)
        if end_call:
            return _openai_response_with_end_call(farewell)
        return _openai_response(farewell)

    # Mid-call farewell: do not end the questionnaire (Vapi endCallPhrases removed). Acknowledge
    # and keep collecting until required coverage is satisfied.
    from backend.questionnaire.conversation_engine import _get_quest_params, ensure_quest_service
    from backend.questionnaire.coverage_policy import is_coverage_satisfied

    # ROUTE FIRST: set __quest:service_id before ensure_quest_service() can default it.
    # Persist immediately on first successful lock to avoid later turns falling back to tier-3 default
    # if the session is reloaded before a later save point.
    before_locked_sid = (
        session.extracted_fields.get("__quest:service_id")
        if isinstance(session.extracted_fields, dict)
        else None
    )
    routing = await get_controller().router_engine.route(last_user_msg, channel="voice", session=session)
    after_locked_sid = (
        session.extracted_fields.get("__quest:service_id")
        if isinstance(session.extracted_fields, dict)
        else None
    )
    just_locked_service = (not before_locked_sid) and isinstance(after_locked_sid, str) and bool(after_locked_sid)
    did_relock_service = (
        isinstance(before_locked_sid, str)
        and bool(before_locked_sid)
        and isinstance(after_locked_sid, str)
        and bool(after_locked_sid)
        and before_locked_sid != after_locked_sid
    )
    if just_locked_service:
        await log_event(
            "SERVICE_LOCKED",
            session_id=session_id,
            data={
                "service_id": after_locked_sid,
                "confidence": getattr(routing, "confidence", ""),
                "confidence_score": float(getattr(routing, "confidence_score", 0.0) or 0.0),
            },
        )
    if did_relock_service:
        await log_event(
            "SERVICE_RELOCKED",
            session_id=session_id,
            data={
                "from_service_id": before_locked_sid,
                "to_service_id": after_locked_sid,
                "confidence": getattr(routing, "confidence", ""),
                "confidence_score": float(getattr(routing, "confidence_score", 0.0) or 0.0),
            },
        )
    if getattr(routing, "is_first_route", False) and getattr(routing, "quest_service_id", None):
        await save_session(session)

    # If router had zero signal on the first utterance, do not lock the quest service yet.
    # Ask a Priya clarifying question and wait for the next user turn.
    meta2 = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    if (
        meta2.get("__router:awaiting_service_selection") is True
        and not meta2.get("__quest:service_id")
    ):
        # Avoid repeating the same long clarify message on unclear/garbled ASR.
        # Count clarifier turns per session and tighten the prompt after the first repeat.
        try:
            cnt = int(meta2.get("__voice:router_clarify_count") or 0)
        except Exception:
            cnt = 0
        meta2["__voice:router_clarify_count"] = cnt + 1
        clarify_text = VOICE_ROUTER_CLARIFY_MESSAGE if cnt == 0 else VOICE_ROUTER_CLARIFY_MESSAGE_SHORT
        session.add_message(MessageRole.USER, last_user_msg)
        session.add_message(MessageRole.SYSTEM, clarify_text)
        await save_session(session)
        return _build_response(optimize_for_voice(clarify_text), is_streaming)

    before_sid = (session.extracted_fields.get("__quest:service_id") if isinstance(session.extracted_fields, dict) else None)
    _qsid = ensure_quest_service(session)
    after_sid = (session.extracted_fields.get("__quest:service_id") if isinstance(session.extracted_fields, dict) else None)
    if not before_sid and isinstance(after_sid, str) and after_sid:
        await save_session(session)
    _params = _get_quest_params(session)
    if (
        not session.summary_generated
        and not is_coverage_satisfied(_params, _qsid)
        and _voice_message_is_goodbye_only(last_user_msg)
    ):
        reply = (
            "I hear you. We're not quite finished with this quick brief yet—"
            "may I ask just one more question so nothing important is missed?"
        )
        session.add_message(MessageRole.USER, last_user_msg)
        session.add_message(MessageRole.ASSISTANT, reply)
        await save_session(session)
        return _build_response(optimize_for_voice(reply), is_streaming)

    # Route through controller
    controller = get_controller()
    try:
        if is_streaming and getattr(settings, "vapi_true_streaming", True):
            stream_iter, updated_session, summary_generated = await controller.process_message_stream(
                session=session,
                user_message=last_user_msg,
                channel="voice",
            )

            async def sse():
                from backend.config import get_settings as _gs

                s = _gs()
                chunk_id = f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}"
                created = int(datetime.utcnow().timestamp())

                def wrap(delta: dict, finish_reason=None):
                    return {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": "aadhya-backend",
                        "choices": [{
                            "index": 0,
                            "delta": delta,
                            "finish_reason": finish_reason,
                        }],
                    }

                # role chunk
                yield f"data: {json.dumps(wrap({'role': 'assistant', 'content': ''}))}\n\n"

                # If routing just locked a service on this turn, speak a 1-line specialist intro once.
                # GUARD (Problem #2 fix): ONLY prepend when the session already had a prior
                # assistant message. On the very first assistant turn the quest engine's
                # OPENING_PROMPT phase already emits a persona-rich "Hi! I'm <name>, your
                # <role>..." self-intro AND the first question in a single line. Firing the
                # deterministic intro here as well produced the stacked intro heard in prod.
                # The flag is still flipped to True in both branches so a later same-service
                # re-lock never re-intros.
                meta3 = updated_session.extracted_fields if isinstance(updated_session.extracted_fields, dict) else {}
                locked_sid = meta3.get("__quest:service_id") if isinstance(meta3, dict) else None
                persona_key_locked = getattr(updated_session, "persona_key", None)
                if just_locked_service and isinstance(locked_sid, str) and locked_sid:
                    key = f"__voice:intro_done:{locked_sid}"
                    if not meta3.get(key):
                        if had_prior_assistant_before_turn:
                            intro = optimize_for_voice(_service_intro_line(locked_sid, persona_key_locked))
                            yield f"data: {json.dumps(wrap({'content': intro + ' '}))}\n\n"
                        meta3[key] = True

                buf = ""
                emitted_any_content = False
                flush_chars = max(12, int(getattr(s, "vapi_stream_flush_chars", 28) or 28))
                boundary_min = max(8, int(getattr(s, "vapi_stream_boundary_min_chars", 12) or 12))
                boundaries = (".", "?", "!", "\n")

                # Voice ack-dedup: read the previous turn's acknowledgement
                # ONCE up front. `_quest_turn_finalize` later in this same
                # request will update `__voice:lastAck` — here we only read.
                # Keeping the read-vs-write separation means the stream and
                # the finalize use the same prev_ack snapshot and make the
                # same strip decision, so audio == stored transcript.
                prev_meta_for_ack = updated_session.extracted_fields if isinstance(
                    updated_session.extracted_fields, dict
                ) else {}
                prev_ack_for_stream = ""
                if isinstance(prev_meta_for_ack, dict):
                    prev_ack_for_stream = str(prev_meta_for_ack.get("__voice:lastAck") or "").strip().lower()
                first_flush_decided = False

                async for piece in stream_iter:
                    if not piece:
                        continue
                    buf += piece
                    should_flush = False
                    if len(buf) >= flush_chars:
                        should_flush = True
                    if any(b in buf for b in boundaries) and len(buf) >= boundary_min:
                        # if we have a sentence boundary, flush earlier
                        should_flush = True
                    if should_flush:
                        # On the FIRST flush only: if this reply's opening ack
                        # matches the previous turn's ack, strip it from the
                        # buffer BEFORE emitting. Prevents "Got it." on 2+
                        # consecutive turns which the caller hears as robotic.
                        if not first_flush_decided:
                            first_flush_decided = True
                            if prev_ack_for_stream:
                                current_ack_in_buf = detect_leading_ack(buf)
                                if current_ack_in_buf and current_ack_in_buf == prev_ack_for_stream:
                                    stripped_buf = strip_leading_ack(buf)
                                    if stripped_buf and stripped_buf != buf:
                                        buf = stripped_buf
                        emitted_any_content = True
                        # TTS pronunciation safety net: ensure "PropFlow" never reaches Cartesia/ElevenLabs
                        # (otherwise heard as "platforms"). Streaming bypasses optimize_for_voice.
                        flushed = re.sub(r"PropFlow", "Prop Flow", buf, flags=re.IGNORECASE)
                        yield f"data: {json.dumps(wrap({'content': flushed}))}\n\n"
                        buf = ""

                if buf.strip():
                    # Single-chunk reply: the whole reply fits in `buf` and
                    # the per-iteration flush never fired. Apply the same
                    # first-flush ack-dedup here so the caller doesn't hear
                    # "Got it." twice in a row.
                    if not first_flush_decided and prev_ack_for_stream:
                        current_ack_in_buf = detect_leading_ack(buf)
                        if current_ack_in_buf and current_ack_in_buf == prev_ack_for_stream:
                            stripped_buf = strip_leading_ack(buf)
                            if stripped_buf and stripped_buf != buf:
                                buf = stripped_buf
                    emitted_any_content = True
                    flushed = re.sub(r"PropFlow", "Prop Flow", buf, flags=re.IGNORECASE)
                    yield f"data: {json.dumps(wrap({'content': flushed}))}\n\n"
                elif not emitted_any_content:
                    # Empty-stream fallback: upstream produced zero text (LLM truncation,
                    # reasoning-token blow-up, provider timeout). We must speak SOMETHING
                    # or Vapi will time out the call.
                    #
                    # IMPORTANT: only say "I didn't catch that" when the user message is
                    # actually unintelligible (≤3 words AND looks like ASR noise). For
                    # any normal-length utterance the LLM (not the user) failed — saying
                    # "I didn't catch that" would gaslight the caller. Instead, re-ask
                    # the last question so the conversation moves forward.
                    user_words = (last_user_msg or "").strip().split()
                    word_count = len(user_words)
                    only_short_tokens = bool(user_words) and all(len(w.strip(".,!?")) <= 2 for w in user_words)
                    looks_unintelligible = word_count <= 3 and only_short_tokens

                    last_question_for_fallback = ""
                    try:
                        meta_for_fallback = updated_session.extracted_fields if isinstance(updated_session.extracted_fields, dict) else {}
                        la = meta_for_fallback.get("__quest:lastAsk") if isinstance(meta_for_fallback, dict) else None
                        if isinstance(la, dict):
                            last_question_for_fallback = str(la.get("question") or "").strip()
                    except Exception:  # noqa: BLE001
                        last_question_for_fallback = ""

                    if looks_unintelligible:
                        fallback_msg = "Sorry, I didn't catch that. Could you say it again?"
                    elif last_question_for_fallback:
                        # FIX 5: rotate fallback phrasing and avoid repeating the exact last question
                        # verbatim more than once in a row.
                        meta_fb = (
                            updated_session.extracted_fields
                            if isinstance(updated_session.extracted_fields, dict)
                            else {}
                        )
                        last_fb = str(meta_fb.get(VOICE_LAST_FALLBACK_KEY) or "") if isinstance(meta_fb, dict) else ""
                        last_fb_q = str(meta_fb.get(VOICE_LAST_FALLBACK_Q_KEY) or "") if isinstance(meta_fb, dict) else ""

                        # Pick a prefix that isn't the same as last time (simple rotation).
                        prefixes = _EMPTY_STREAM_FALLBACK_PREFIXES
                        try:
                            last_i = prefixes.index(last_fb)
                        except ValueError:
                            last_i = -1
                        prefix = prefixes[(last_i + 1) % len(prefixes)]

                        if last_fb_q and last_fb_q == last_question_for_fallback:
                            # Would repeat the exact question again → use the spelling fallback.
                            prefix = "Sorry, I missed that — could you spell it out?"
                            fallback_msg = prefix
                            if isinstance(meta_fb, dict):
                                meta_fb[VOICE_LAST_FALLBACK_Q_KEY] = ""
                        else:
                            fallback_msg = f"{prefix} {last_question_for_fallback}"
                            if isinstance(meta_fb, dict):
                                meta_fb[VOICE_LAST_FALLBACK_Q_KEY] = last_question_for_fallback

                        if isinstance(meta_fb, dict):
                            meta_fb[VOICE_LAST_FALLBACK_KEY] = prefix
                            updated_session.extracted_fields = meta_fb
                    else:
                        meta_fb = (
                            updated_session.extracted_fields
                            if isinstance(updated_session.extracted_fields, dict)
                            else {}
                        )
                        last_fb = str(meta_fb.get(VOICE_LAST_FALLBACK_KEY) or "") if isinstance(meta_fb, dict) else ""
                        prefixes = _EMPTY_STREAM_FALLBACK_PREFIXES
                        try:
                            last_i = prefixes.index(last_fb)
                        except ValueError:
                            last_i = -1
                        prefix = prefixes[(last_i + 1) % len(prefixes)]
                        fallback_msg = prefix
                        if isinstance(meta_fb, dict):
                            meta_fb[VOICE_LAST_FALLBACK_KEY] = prefix
                            meta_fb[VOICE_LAST_FALLBACK_Q_KEY] = ""
                            updated_session.extracted_fields = meta_fb
                    fallback_text = optimize_for_voice(fallback_msg)
                    emitted_any_content = True
                    yield f"data: {json.dumps(wrap({'content': fallback_text}))}\n\n"

                # After the closing line, tell Vapi to end the call (only when questionnaire just finished).
                emitted_end_call_tools = False
                if _request_includes_vapi_end_call_tool(body) and getattr(
                    updated_session, "voice_turn_requested_end_call", False
                ):
                    emitted_end_call_tools = True
                    tc_id = f"call_end_{uuid.uuid4().hex[:24]}"
                    tool_chunk = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": "aadhya-backend",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": tc_id,
                                            "type": "function",
                                            "function": {"name": "endCall", "arguments": "{}"},
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(tool_chunk)}\n\n"
                    final_tool = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": "aadhya-backend",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": "tool_calls",
                            }
                        ],
                    }
                    yield f"data: {json.dumps(final_tool)}\n\n"

                # Persist after streaming completes
                await save_session(updated_session)
                if getattr(updated_session, "summary_generated", False) and updated_session.summary:
                    await supabase_store.save_enquiry(updated_session)
                    try:
                        from backend.schemas.summary import ProjectSummary
                        summary_obj = ProjectSummary.model_validate(updated_session.summary)
                        await supabase_store.save_summary(summary_obj, phone_number=phone)
                    except Exception:
                        pass
                    try:
                        from backend.questionnaire.completion_webhook import schedule_questionnaire_completion_webhook
                        from backend.questionnaire.completion_webhook import schedule_enquiry_webhook
                        from backend.questionnaire.conversation_engine import ensure_quest_service

                        qsid = ensure_quest_service(updated_session)
                        schedule_questionnaire_completion_webhook(updated_session, service_id=qsid)
                        schedule_enquiry_webhook(updated_session, service_id=qsid)
                    except Exception:
                        pass

                if not emitted_end_call_tools:
                    yield f"data: {json.dumps(wrap({}, finish_reason='stop'))}\n\n"
                yield "data: [DONE]\n\n"

            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                sse(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        agent_response = await controller.process_message(
            session=session,
            user_message=last_user_msg,
            channel="voice",
        )
    except Exception as e:
        await log_event("API_ERROR", session_id=session_id,
                        data={"error": str(e), "phase": "vapi_custom_llm"})
        fallback = "Could you give me just a moment, I'm pulling up your details."
        await save_session(session)
        return _build_response(fallback, is_streaming)

    # Optimize for voice (and optionally prepend one-time specialist intro)
    voice_text = optimize_for_voice(agent_response.text)
    meta4 = agent_response.session.extracted_fields if isinstance(agent_response.session.extracted_fields, dict) else {}
    locked_sid2 = meta4.get("__quest:service_id") if isinstance(meta4, dict) else None
    persona_key_locked2 = getattr(agent_response.session, "persona_key", None)
    if just_locked_service and isinstance(locked_sid2, str) and locked_sid2:
        key2 = f"__voice:intro_done:{locked_sid2}"
        if not meta4.get(key2):
            # Same guard as the streaming path above — skip deterministic intro on
            # the first assistant turn to prevent stacking with the OPENING_PROMPT
            # self-intro the quest engine emits.
            if had_prior_assistant_before_turn:
                voice_text = f"{optimize_for_voice(_service_intro_line(locked_sid2, persona_key_locked2))} {voice_text}".strip()
            meta4[key2] = True

    # Persist
    if isinstance(agent_response.session.extracted_fields, dict):
        agent_response.session.extracted_fields["__voice:last_user_norm"] = norm_user
        agent_response.session.extracted_fields["__voice:last_assistant_text"] = agent_response.text
        agent_response.session.extracted_fields["__voice:last_turn_ts"] = now_ts
        # If this turn is explicitly ending the call (graceful close), mark farewell sent
        # so any stray post-farewell webhook turns stay silent.
        if getattr(agent_response.session, "voice_turn_requested_end_call", False):
            agent_response.session.extracted_fields[VOICE_FAREWELL_SENT_KEY] = True
    await save_session(agent_response.session)

    if agent_response.summary_generated and agent_response.session.summary:
        await supabase_store.save_enquiry(agent_response.session)
        try:
            from backend.schemas.summary import ProjectSummary
            summary_obj = ProjectSummary.model_validate(agent_response.session.summary)
            await supabase_store.save_summary(summary_obj, phone_number=phone)
        except Exception:
            pass
        try:
            from backend.questionnaire.completion_webhook import schedule_questionnaire_completion_webhook
            from backend.questionnaire.completion_webhook import schedule_enquiry_webhook
            from backend.questionnaire.conversation_engine import ensure_quest_service

            qsid = ensure_quest_service(agent_response.session)
            schedule_questionnaire_completion_webhook(agent_response.session, service_id=qsid)
            schedule_enquiry_webhook(agent_response.session, service_id=qsid)
        except Exception:
            pass

    # End-call gate: the streaming branch above already honors BOTH conditions, but this
    # non-streaming path previously only checked `summary_generated`. That silently
    # ignored `voice_turn_requested_end_call=True` set by the graceful-close path in
    # `prepare_voice_quest_stream_or_sync` (caller farewell after questionnaire was
    # already complete → `summary_generated` stays False for the bye-bye turn). Result:
    # the agent said "have a great day!" but the call stayed open. OR-merging both
    # signals closes that gap without changing behavior for the normal completion turn.
    end_call = bool(
        (
            agent_response.summary_generated
            or getattr(agent_response.session, "voice_turn_requested_end_call", False)
        )
        and _request_includes_vapi_end_call_tool(body)
    )
    return _build_response(voice_text, is_streaming, end_call_after_speech=end_call)


def _build_response(text: str, stream: bool = False, *, end_call_after_speech: bool = False):
    """Return either an SSE stream or a plain JSON response."""
    if stream:
        return _openai_stream_response(text)
    if end_call_after_speech:
        return _openai_response_with_end_call(text)
    return _openai_response(text)


def _openai_response(text: str) -> dict:
    """Format the response exactly how Vapi Custom LLM expects it (non-streaming)."""
    return {
        "id": f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}",
        "object": "chat.completion",
        "created": int(datetime.utcnow().timestamp()),
        "model": "aadhya-backend",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": text
            },
            "finish_reason": "stop"
        }]
    }


def _openai_response_with_end_call(text: str) -> dict:
    """Non-streaming completion: speak `text`, then Vapi executes default endCall tool."""
    tc_id = f"call_end_{uuid.uuid4().hex[:24]}"
    return {
        "id": f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}",
        "object": "chat.completion",
        "created": int(datetime.utcnow().timestamp()),
        "model": "aadhya-backend",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [
                        {
                            "id": tc_id,
                            "type": "function",
                            "function": {"name": "endCall", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def _openai_stream_response(text: str):
    """Return an SSE streaming response compatible with OpenAI chat completions."""
    import json
    from fastapi.responses import StreamingResponse

    chunk_id = f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}"
    created = int(datetime.utcnow().timestamp())

    def generate():
        # First chunk: role
        chunk1 = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk1)}\n\n"

        # Second chunk: full content
        chunk2 = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{
                "index": 0,
                "delta": {"content": text},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk2)}\n\n"

        # Final chunk: stop
        chunk3 = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(chunk3)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


def _openai_stream_response_with_end_call(text: str, *, emit_end_call: bool = True):
    """SSE response that speaks `text` and then emits Vapi's endCall tool-call.

    Mirrors the 3-chunk pattern used in the main streaming path (content chunk
    → tool_calls chunk → finish_reason=tool_calls). Used by the post-completion
    hard guard in `vapi_chat_completions` so Vapi hangs up even on stray turns
    delivered after the first endCall frame was emitted. `emit_end_call=False`
    still emits the speech but ends with `finish_reason=stop` — used when the
    inbound request didn't carry Vapi's default endCall tool (unlikely but
    defensive, matches `_openai_response` behaviour).
    """
    import json
    from fastapi.responses import StreamingResponse

    chunk_id = f"chatcmpl-aadhya-{int(datetime.utcnow().timestamp())}"
    created = int(datetime.utcnow().timestamp())

    def generate():
        role_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(role_chunk)}\n\n"

        content_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "aadhya-backend",
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(content_chunk)}\n\n"

        if emit_end_call:
            tc_id = f"call_end_{uuid.uuid4().hex[:24]}"
            tool_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "aadhya-backend",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": tc_id,
                                    "type": "function",
                                    "function": {"name": "endCall", "arguments": "{}"},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(tool_chunk)}\n\n"
            final_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "aadhya-backend",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
        else:
            final_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "aadhya-backend",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _assistant_config_response(opening_message: str) -> dict:
    """
    Returns Vapi assistant configuration.
    This is sent when Vapi first establishes a call.
    """
    from backend.config import get_settings
    s = get_settings()
    provider = (s.tts_provider or "cartesia").strip().lower()
    if provider in ("elevenlabs", "11lab", "11labs", "xi"):
        provider = "11labs"
    if provider in ("cartesia", "cartesia-ai"):
        provider = "cartesia"

    if provider == "cartesia":
        voice_config = {
            "provider": "cartesia",
            "voiceId": s.cartesia_voice_id,
            "model": (s.cartesia_model or "sonic-3"),
        }
    else:
        voice_config = {
            "provider": "11labs",
            "voiceId": s.elevenlabs_voice_id or "EXAVITQu4vr4xnSDxMaL",  # Default: Bella
            # Use a multilingual model so the same voice can speak Hindi/Tamil/Kannada/English.
            # Low-latency alternative: eleven_flash_v2_5
            "model": (s.elevenlabs_voice_model or "eleven_multilingual_v2"),
            "stability": 0.6,
            "similarityBoost": 0.85,
        }

    return {
        "assistant": {
            "firstMessage": opening_message,
            # Make call behavior deterministic: always speak our opening first.
            "firstMessageMode": "assistant-speaks-first",
            # Prevent the caller from interrupting the opening greeting.
            "firstMessageInterruptionsEnabled": False,
            "voice": voice_config,
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                # "multi" enables multilingual realtime transcription (auto-detect language).
                "language": (s.deepgram_language or "multi"),
            },
            "model": {
                "provider": "custom-llm",
                # Full OpenAI-compatible URL — Vapi POSTs chat completions here (not /webhook/vapi).
                "url": f"{s.base_url.rstrip('/')}/webhook/vapi/chat/completions",
                # Lets the server signal hang-up after the closing line (see tool_calls on completion turns).
                "tools": [{"type": "endCall"}],
            },
            # Spoken when the call ends for other reasons (user hangs up, carrier drop, etc.).
            # We intentionally omit endCallPhrases: phrase-based hangup cannot be gated on
            # questionnaire completion from this backend, so short "bye" mid-flow would
            # otherwise cut calls short during data collection.
            "endCallMessage": "",
        }
    }
