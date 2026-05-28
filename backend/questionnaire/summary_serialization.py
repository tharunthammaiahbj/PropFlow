"""
Quest-shaped JSON for the main platform — camelCase keys matching
quest-characters `apps/questionnaire/src/models/Questionnaire.ts`
(ProjectSummary, SixPointSummary).

Internal storage remains snake_case (session.summary, session.six_point_summary).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def _iso(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        try:
            return val.isoformat()  # type: ignore[no-any-return]
        except Exception:
            pass
    return str(val)


def project_summary_to_quest_camel(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Map stored `session.summary` (snake_case + scope_of_work list) → quest `ProjectSummary` camelCase.
    Includes extra fields `designDirection`, `executionReadiness`, `enquirySnapshot` when present.
    """
    if not summary:
        return None

    scope = summary.get("scope_of_work")
    if isinstance(scope, list):
        scope_str = " ".join(str(x) for x in scope if str(x).strip()).strip()
    else:
        scope_str = (str(scope) if scope is not None else "").strip()

    out: dict[str, Any] = {
        "projectOverview": summary.get("project_overview") or "",
        "scopeOfWork": scope_str,
        "clientRequirements": summary.get("client_requirements") or "",
        "technicalSpecs": summary.get("technical_specs") or "",
        "timeline": summary.get("timeline") or "",
        "specialConsiderations": summary.get("special_considerations") or "",
        "estimatedScope": summary.get("estimated_scope") or "",
        "initiationNextStep": summary.get("next_step")
        or summary.get("execution_readiness")
        or "",
    }

    dd = summary.get("design_direction")
    if dd:
        out["designDirection"] = dd
    er = summary.get("execution_readiness")
    if er:
        out["executionReadiness"] = er

    ga = _iso(summary.get("generated_at"))
    if ga:
        out["generatedAt"] = ga

    snap = summary.get("enquiry_snapshot")
    if snap is not None:
        out["enquirySnapshot"] = snap

    sid = summary.get("session_id")
    if sid:
        out["sessionId"] = sid

    return out


def six_point_summary_to_quest_camel(six: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map stored `session.six_point_summary` (snake_case) → quest `SixPointSummary` camelCase."""
    if not six:
        return None

    return {
        "clientProfile": six.get("client_profile") or "",
        "projectScope": six.get("project_scope") or "",
        "keyRequirements": six.get("key_requirements") or "",
        "budgetTimeline": six.get("budget_timeline") or "",
        "conversationInsights": six.get("conversation_insights") or "",
        "nextSteps": six.get("next_steps") or "",
        "generatedAt": _iso(six.get("generated_at")) or "",
        "moodSummary": six.get("mood_summary") or "",
    }


def build_quest_completion_summaries(session: Any) -> dict[str, Any]:
    """
    Payload shape convenient for a platform mirroring quest POST completion `summary` fields.
    `session` is a Session model instance with .summary, .six_point_summary, .summary_generated, etc.
    """
    summary = getattr(session, "summary", None)
    raw_summary = summary if isinstance(summary, dict) else None
    raw_six = getattr(session, "six_point_summary", None)
    raw_six_dict = raw_six if isinstance(raw_six, dict) else None

    stage = getattr(session, "conversation_stage", None)
    stage_val = stage.value if stage is not None and hasattr(stage, "value") else None

    return {
        "sessionId": session.session_id,
        "phoneNumber": getattr(session, "phone_number", None),
        "channel": getattr(session, "channel", None),
        "serviceCode": getattr(session, "service_code", None),
        "summaryGenerated": bool(getattr(session, "summary_generated", False)),
        "conversationStage": stage_val,
        "projectSummary": project_summary_to_quest_camel(raw_summary),
        "sixPointSummary": six_point_summary_to_quest_camel(raw_six_dict),
    }
