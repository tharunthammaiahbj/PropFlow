"""
POST completion payload to QUESTIONNAIRE_WEBHOOK_URL — quest-characters parity
(`apps/questionnaire/src/routes.ts` + `webhook.ts`).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from backend.config import get_settings
from backend.questionnaire.summary_generator import flatten_params_for_summary
from backend.questionnaire.summary_serialization import (
    project_summary_to_quest_camel,
    six_point_summary_to_quest_camel,
)
from backend.questionnaire.conversation_engine import QUEST_CONVERSATION_FLOW
from backend.questionnaire.conversation_engine import SERVICE_DISPLAY_NAMES
from backend.schemas.session import Session
from backend.utils.logger import log_event


# Map quest service ids → the platform's website service codes (the IDs the
# external PM/enquiry backend validates against). Used as a fallback for
# `serviceId` when ENQUIRY_WEBHOOK_SERVICE_ID env override is not set.
# Source of truth for codes: backend/intelligence/service_registry.py
# (SERVICE_CODE_TO_PERSONA_KEY).
QUEST_TO_WEBHOOK_SERVICE_ID: dict[str, str] = {
    "residential_interiors": "IRRI01",
    "residential_construction": "CIRC01",
    "painting": "IRPW02",
    "solar_services": "SESR01",
    "plumbing_services": "CIPL02",
    "electrical_services": "CIEL03",
    "home_automation": "HASH01",
    "commercial_interiors": "IRCI03",
    "commercial_construction": "CICC04",
    "property_development": "RPPD01",
    "event_management": "PSEM01",
    "farm_infrastructure": "AAFI01",
    "irrigation_automation": "AAIA02",
}


def _json_safe(obj: Any) -> Any:
    """Recursively make payload JSON-serializable (datetimes → ISO)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return str(obj)


def build_completion_payload(session: Session, *, service_id: str) -> dict[str, Any]:
    """
    Same fields as quest `postCompletion(...)` plus optional `sixPointSummary` (camelCase).
    """
    from backend.questionnaire.conversation_engine import _get_quest_params

    parameters = _get_quest_params(session)
    flat = flatten_params_for_summary(parameters)
    raw_summary = session.summary if isinstance(session.summary, dict) else None
    raw_six = session.six_point_summary if isinstance(session.six_point_summary, dict) else None

    return _json_safe(
        {
            "questionnaireId": session.session_id,
            "service": service_id,
            "parameters": parameters,
            "metadata": flat,
            "summary": project_summary_to_quest_camel(raw_summary),
            "sixPointSummary": six_point_summary_to_quest_camel(raw_six),
            "characterId": session.persona_key or "",
            "userRef": session.phone_number,
            "channel": session.channel,
            "completedAt": datetime.utcnow().isoformat() + "Z",
            "serviceCode": session.service_code,
        }
    )


async def _post_once(url: str, body: bytes, *, headers: dict[str, str] | None = None) -> bool:
    try:
        import httpx
    except ImportError:
        return False
    async with httpx.AsyncClient(timeout=30.0) as client:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update({str(k): str(v) for k, v in headers.items() if v is not None})
        r = await client.post(
            url,
            content=body,
            headers=hdrs,
        )
        return 200 <= r.status_code < 300


async def _post_once_with_response(
    url: str,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[bool, int, dict[str, Any] | None, str | None]:
    try:
        import httpx
    except ImportError:
        return False, 0, None, "httpx_not_installed"
    async with httpx.AsyncClient(timeout=30.0) as client:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update({str(k): str(v) for k, v in headers.items() if v is not None})
        r = await client.post(url, content=body, headers=hdrs)
        resp_json: dict[str, Any] | None = None
        text: str | None = None
        try:
            resp_json = r.json() if isinstance(r.json(), dict) else None
        except Exception:
            try:
                text = r.text
            except Exception:
                text = None
        return (200 <= r.status_code < 300), int(r.status_code), resp_json, text


async def post_questionnaire_completion(session: Session, *, service_id: str) -> None:
    """
    Retry with backoff (3 attempts), matching quest `webhook.ts`.
    Does nothing if QUESTIONNAIRE_WEBHOOK_URL is unset.
    """
    settings = get_settings()
    url = (settings.questionnaire_webhook_url or "").strip()
    if not url:
        return

    payload = build_completion_payload(session, service_id=service_id)
    body = json.dumps(payload, default=str).encode("utf-8")

    delay = 0.5
    for attempt in range(3):
        try:
            ok = await _post_once(url, body)
            if ok:
                await log_event(
                    "QUESTIONNAIRE_WEBHOOK_OK",
                    session_id=session.session_id,
                    data={"url": url.split("?")[0], "attempt": attempt + 1},
                )
                return
        except Exception as e:
            await log_event(
                "QUESTIONNAIRE_WEBHOOK_ERR",
                session_id=session.session_id,
                data={"attempt": attempt + 1, "error": str(e)[:200]},
            )
        if attempt < 2:
            await asyncio.sleep(delay)
            delay *= 2

    await log_event(
        "QUESTIONNAIRE_WEBHOOK_FAIL",
        session_id=session.session_id,
        data={"url": url.split("?")[0]},
    )


def schedule_questionnaire_completion_webhook(session: Session, *, service_id: str) -> None:
    """Fire-and-forget: do not block Twilio / Vapi response."""
    url = (get_settings().questionnaire_webhook_url or "").strip()
    if not url:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run():
        try:
            await post_questionnaire_completion(session, service_id=service_id)
        except Exception as e:
            await log_event(
                "QUESTIONNAIRE_WEBHOOK_ERR",
                session_id=session.session_id,
                data={"phase": "schedule", "error": str(e)[:200]},
            )

    loop.create_task(_run())


def build_enquiry_payload_like_quest(session: Session, *, service_id: str) -> dict[str, Any]:
    """
    Quest-like payload shape expected by external backends:
    - userId, serviceName, serviceId
    - conversationFlow (question+answer)
    - status
    - summary
    - metadata (parameters with {value, confidence, ts})
    """
    from backend.questionnaire.conversation_engine import _get_quest_params

    s = get_settings()
    parameters = _get_quest_params(session)
    raw_summary = session.summary if isinstance(session.summary, dict) else None
    flow = None
    if isinstance(session.extracted_fields, dict):
        flow = session.extracted_fields.get(QUEST_CONVERSATION_FLOW)
    if not isinstance(flow, list):
        flow = []
    # serviceId fallback chain:
    #   1. env override (ENQUIRY_WEBHOOK_SERVICE_ID) — pin to one code for tests
    #   2. session.service_code — set by website routing (e.g. "SESR01")
    #   3. QUEST_TO_WEBHOOK_SERVICE_ID[quest_id] — map quest engine id → website code
    #   4. raw quest service id (legacy fallback; will likely fail strict PM validation)
    mapped_service_id = QUEST_TO_WEBHOOK_SERVICE_ID.get(service_id)
    resolved_service_id = (
        s.enquiry_webhook_service_id
        or (session.service_code or "").strip()
        or mapped_service_id
        or service_id
    )
    return _json_safe(
        {
            "userId": (s.enquiry_webhook_user_id or session.phone_number),
            "serviceName": (s.enquiry_webhook_service_name or SERVICE_DISPLAY_NAMES.get(service_id, service_id)),
            "serviceId": resolved_service_id,
            "conversationFlow": flow,
            "status": "completed" if getattr(session, "summary_generated", False) else "in_progress",
            "summary": project_summary_to_quest_camel(raw_summary),
            "metadata": parameters,
        }
    )


async def post_enquiry_payload(session: Session, *, service_id: str) -> None:
    """
    Post Quest-like enquiry payload to ENQUIRY_WEBHOOK_URL and store response in session.extracted_fields.
    This is fire-and-forget; on failure we log but do not break the user experience.
    """
    settings = get_settings()
    url = (settings.enquiry_webhook_url or "").strip()
    if not url:
        await log_event(
            "ENQUIRY_WEBHOOK_DISABLED",
            session_id=session.session_id,
            data={"reason": "ENQUIRY_WEBHOOK_URL_unset"},
        )
        return

    payload = build_enquiry_payload_like_quest(session, service_id=service_id)
    body = json.dumps(payload, default=str).encode("utf-8")
    headers: dict[str, str] = {}
    token = (getattr(settings, "enquiry_webhook_bearer_token", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/json"
    else:
        # If the integration expects auth, this will fail with 401/403; make it explicit in logs.
        await log_event(
            "ENQUIRY_WEBHOOK_MISCONFIGURED",
            session_id=session.session_id,
            data={"reason": "ENQUIRY_WEBHOOK_BEARER_TOKEN_unset"},
        )
        # Hard stop when the operator has opted into fail-closed mode. Avoids hammering the
        # PM backend with anonymous requests that will be rejected.
        if bool(getattr(settings, "enquiry_webhook_require_auth", False)):
            return

    # Mark in-flight BEFORE the HTTP call so a parallel/duplicate completion turn
    # (Vapi sometimes retries) does not race and POST a second time.
    if isinstance(session.extracted_fields, dict):
        session.extracted_fields["__enquiry:webhook:sent"] = "sending"
        session.extracted_fields["__enquiry:webhook:lastAt"] = datetime.utcnow().isoformat() + "Z"

    ok, status, resp_json, resp_text = await _post_once_with_response(url, body, headers=headers)

    if isinstance(session.extracted_fields, dict):
        session.extracted_fields["__enquiry:webhook:lastPayload"] = payload
        session.extracted_fields["__enquiry:webhook:lastResponse"] = resp_json or {"text": (resp_text or "")[:4000]}
        session.extracted_fields["__enquiry:webhook:lastStatus"] = status
        session.extracted_fields["__enquiry:webhook:lastOk"] = ok
        session.extracted_fields["__enquiry:webhook:lastAt"] = datetime.utcnow().isoformat() + "Z"
        if ok:
            # Idempotency flag: once the external PM/backend accepts the enquiry payload (2xx),
            # do not re-post on repeated "ok/done" messages after completion.
            session.extracted_fields["__enquiry:webhook:sent"] = True
        else:
            # Allow another attempt on the next completion event by clearing the in-flight flag.
            session.extracted_fields["__enquiry:webhook:sent"] = False

    await log_event(
        "ENQUIRY_WEBHOOK_OK" if ok else "ENQUIRY_WEBHOOK_FAIL",
        session_id=session.session_id,
        data={
            "url": url.split("?")[0],
            "status": status,
            "resp_preview": (json.dumps(resp_json)[:500] if resp_json else (resp_text or "")[:500]),
        },
    )


def schedule_enquiry_webhook(session: Session, *, service_id: str) -> None:
    """Fire-and-forget enquiry webhook post; safe for voice/whatsapp handlers."""
    # Idempotency: do not post multiple times for the same session after a successful send,
    # AND skip while a previous post is still in-flight ("sending") to prevent the duplicate
    # POST seen when Vapi retries a completion turn.
    if isinstance(session.extracted_fields, dict):
        flag = session.extracted_fields.get("__enquiry:webhook:sent")
        if flag is True or flag == "sending":
            return
    url = (get_settings().enquiry_webhook_url or "").strip()
    if not url:
        # Log once so it's obvious why PM backend never sees a POST.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            log_event(
                "ENQUIRY_WEBHOOK_DISABLED",
                session_id=session.session_id,
                data={"reason": "ENQUIRY_WEBHOOK_URL_unset_at_schedule"},
            )
        )
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run():
        try:
            await log_event(
                "ENQUIRY_WEBHOOK_START",
                session_id=session.session_id,
                data={"url": url.split("?")[0]},
            )
            await post_enquiry_payload(session, service_id=service_id)
        except Exception as e:
            await log_event(
                "ENQUIRY_WEBHOOK_ERR",
                session_id=session.session_id,
                data={"error": str(e)[:200]},
            )

    loop.create_task(_run())
