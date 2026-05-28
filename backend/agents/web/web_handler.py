"""
PropFlow – Web Demo Handler
Simple REST endpoint for browser-based demo. Reuses the WhatsApp conversation flow
without Twilio, webhooks, or any external dependencies.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.schemas.session import Session, ConversationStage
from backend.intelligence.conversation_controller import get_controller
from backend.storage.redis_store import get_session, save_session
from backend.questionnaire.conversation_engine import QUEST_PARAMETERS
from backend.utils.logger import log_event

router = APIRouter()


class WebMessageRequest(BaseModel):
    session_id: str
    message: str


class WebMessageResponse(BaseModel):
    reply: str
    completed: bool = False
    fields: Optional[dict] = None


@router.post("/webhook/web", response_model=WebMessageResponse)
async def web_webhook(body: WebMessageRequest):
    session_id = f"web_{body.session_id}"
    user_message = (body.message or "").strip()

    session = await get_session(session_id)

    if session is None:
        now = datetime.utcnow()
        session = Session(
            session_id=session_id,
            phone_number=f"web_{body.session_id}",
            channel="whatsapp",
            conversation_stage=ConversationStage.DISCOVERY,
            created_at=now,
            last_active=now,
        )
        session.extracted_fields = {
            "__wa:stage": "PRIYA_SERVICE_PICK",
            "__wa:first_message": True,
        }
        session.extracted_fields[QUEST_PARAMETERS] = {
            "contact_pref": {
                "value": "web",
                "confidence": 1.0,
                "ts": now.isoformat() + "Z",
            }
        }
        await log_event("SESSION_START", session_id=session_id, data={"channel": "web"})

    controller = get_controller()
    try:
        response = await controller.process_message(
            session=session,
            user_message=user_message,
            channel="whatsapp",
        )
    except Exception as e:
        await log_event("API_ERROR", session_id=session_id, data={"error": str(e)[:200]})
        return WebMessageResponse(
            reply="Give me just a moment — I'm getting things together.",
            completed=False,
        )

    await save_session(response.session)

    # Build project brief fields when the enquiry is complete
    brief_fields: Optional[dict] = None
    if response.completed and isinstance(response.session.extracted_fields, dict):
        ef = response.session.extracted_fields
        brief_fields = {}

        # Service type from the Jessica routing stage
        svc = str(ef.get("__wa:service_bucket") or "").strip()
        if svc:
            brief_fields["service"] = svc.title()

        # All collected quest parameters
        params_raw = ef.get(QUEST_PARAMETERS)
        if isinstance(params_raw, dict):
            # Skip internal flags + overflow buckets where the LLM dumps
            # commentary that duplicates structured fields ("budget updated
            # to 8 lakhs" landing in notes / other_electrical).
            _skip_keys = {
                "contact_pref", "callback_time",
                "notes", "other_electrical", "other_solar", "other_painting",
                "other_construction", "other_automation", "other_plumbing",
            }
            _skip_values = {"none", "null", "not specified", "not_specified", "web", "n/a", "na", ""}
            for k, v in params_raw.items():
                if k in _skip_keys:
                    continue
                val = v.get("value") if isinstance(v, dict) else v
                if val is not None:
                    sv = str(val).strip()
                    if sv and sv.lower() not in _skip_values:
                        brief_fields[k] = sv

    return WebMessageResponse(
        reply=response.text,
        completed=response.completed,
        fields=brief_fields if brief_fields else None,
    )
