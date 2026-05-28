"""
Project + 6-point summaries — port of quest-characters
`apps/questionnaire/src/summary-generator.ts` (generateProjectSummary,
generateSixPointSummary, fallbacks, mood line, duration).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from backend.intelligence.llm_engine import get_llm_engine
from backend.utils.perf_analytics import quest_llm_phase
from backend.questionnaire.generated.service_parameters_generated import SERVICE_PARAMS
from backend.schemas.session import MessageRole, Session

# Match quest summary-generator.ts temperatures
SUMMARY_PROJECT_TEMPERATURE = 0.2
SUMMARY_SIX_POINT_TEMPERATURE = 0.25
# Match quest `packages/ai/src/adapters/gemini-api.ts` default maxTokens=2048 for generateText
SUMMARY_MAX_OUTPUT_TOKENS = int(os.getenv("SUMMARY_MAX_OUTPUT_TOKENS", "2048"))

QUEST_META = "__quest:conversation_meta"


def _summary_max_output_tokens_for_session(session: Session) -> int:
    """Tighter cap on voice completion summaries; default path unchanged for WhatsApp / web."""
    from backend.config import get_settings

    if (session.channel or "").strip().lower() == "voice":
        cap = int(get_settings().summary_max_output_tokens_voice)
        return max(256, cap)
    return SUMMARY_MAX_OUTPUT_TOKENS

SERVICE_DISPLAY_NAMES: dict[str, str] = {
    "residential_interiors": "Residential Interiors",
    "commercial_interiors": "Commercial Interiors & Fit-Out",
    "commercial_construction": "Commercial Construction",
    "property_development": "Property Development",
    "residential_construction": "Residential Construction",
    "home_automation": "Home Automation",
    "painting": "Painting & Finishes",
    "solar_services": "Solar Services",
    "electrical_services": "Electrical Services",
    "irrigation_automation": "Irrigation Automation",
    "event_management": "Event Management",
    "farm_infrastructure": "Farm Infrastructure",
    "plumbing_services": "Plumbing Services",
}

PARAM_LABEL_MAP: dict[str, str] = {
    "project_type": "Project type",
    "rooms": "Rooms / BHK",
    "size_sqft": "Area (sqft)",
    "style": "Style",
    "budget": "Budget",
    "timeline": "Timeline",
    "contact_pref": "Contact preference",
    "must_haves": "Must-haves",
    "avoid": "Avoid",
    "notes": "Notes",
    "site_ready": "Site ready",
    "moodboard_refs": "Moodboard refs",
    "preferred_start": "Preferred start",
    "plot_size_sqft": "Plot size (sqft)",
    "floors": "Number of floors",
    "has_soil_test": "Soil test",
    "has_approvals": "Approvals",
    "space_use": "Space use",
    "brand_theme": "Brand / theme",
    "occupancy": "Occupancy",
    "construction_type": "Construction type",
    "delivery_phase": "Delivery phase",
    "contract_type": "Contract type",
    "num_units": "Number of units",
    "delivery_model": "Delivery model",
    "automation_scope": "Automation scope",
    "current_systems": "Current systems",
    "surface_type": "Surface type",
    "area_scope": "Area scope",
    "paint_type": "Paint type",
    "roof_type": "Roof type",
    "capacity_kw": "Capacity (kW)",
    "grid_type": "Grid type",
    "scope_type": "Scope",
    "load_requirement": "Load requirement",
    "current_system": "Current system",
    "safety_audit": "Safety audit",
    "water_source": "Water source",
    "current_issues": "Current issues",
    "property_age": "Property age",
    "land_size_sqft": "Land size (sqft)",
    "crop_type": "Crop type",
    "event_type": "Event type",
    "guest_count": "Guest count",
    "venue_type": "Venue type",
    "primary_use": "Primary use",
    "power_avail": "Power availability",
    "location": "Location",
    "material_grade": "Material grade",
    "power_water_avail": "Power & water availability",
    "foundation_type": "Foundation type",
}


def get_parameter_labels_for_service(service: str) -> dict[str, str]:
    s = SERVICE_PARAMS.get(service)
    if not s:
        return {}
    out: dict[str, str] = {}
    for r in s["required"]:
        out[r["id"]] = r["label"]
    for o in s["optional"]:
        out[o["id"]] = o["label"]
    return out


def param_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict) and "value" in v:
        return str(v.get("value") or "")
    return str(v)


def flatten_params_for_summary(parameters: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not parameters:
        return out
    for key, val in parameters.items():
        s = param_value(val)
        if s != "":
            out[key] = s
    return out


def build_technical_specs(parameters: dict[str, str]) -> str:
    area = (
        parameters.get("size_sqft")
        or parameters.get("plot_size_sqft")
        or parameters.get("land_size_sqft")
        or parameters.get("area_scope")
        or ""
    )
    rooms = parameters.get("rooms") or ""
    project_type = parameters.get("project_type") or parameters.get("space_use") or parameters.get("event_type") or ""
    style = parameters.get("style") or parameters.get("brand_theme") or ""
    floors = parameters.get("floors") or ""
    location = parameters.get("location") or ""
    material_grade = parameters.get("material_grade") or ""
    parts = [
        project_type,
        f"{area} sqft" if area else "",
        floors,
        rooms,
        style,
        location,
        material_grade,
    ]
    parts = [p for p in parts if p and p != "sqft"]
    if len(parts) == 0:
        return ""
    if len(parts) == 1 and len(parts[0]) < 15:
        return ""
    return " · ".join(parts)


def build_special_considerations(parameters: dict[str, str]) -> str:
    notes = parameters.get("notes") or ""
    must_haves = parameters.get("must_haves") or ""
    avoid = parameters.get("avoid") or ""
    parts = [
        f"Notes: {notes}" if notes else "",
        f"Must-haves: {must_haves}" if must_haves else "",
        f"Avoid: {avoid}" if avoid else "",
    ]
    parts = [p for p in parts if p]
    return " | ".join(parts) if parts else ""


def format_estimated_scope(parameters: dict[str, str]) -> str:
    budget_raw = (parameters.get("budget") or parameters.get("budgetRange") or "").strip()
    area = (
        parameters.get("size_sqft")
        or parameters.get("plot_size_sqft")
        or parameters.get("land_size_sqft")
        or ""
    )
    budget_str = ""
    if budget_raw:
        budget_str = (
            f"Budget: {budget_raw}"
            if re.search(r"lakh|lac|L|cr\b", budget_raw, re.I)
            else f"Budget: {budget_raw} lakhs"
        )
    area_str = f"Area: {area} sqft" if area else ""
    scope = " | ".join([s for s in [budget_str, area_str] if s])
    if scope and len(scope) > 10:
        return scope
    return ""


def _format_field_long(value: str, fallback: str) -> str:
    if not value or value.strip() in ("--", ""):
        return fallback
    if len(value) < 20:
        return f"{value}. Need more inputs"
    return value


def _format_timeline(v: str) -> str:
    if not v or not v.strip():
        return "Need more inputs"
    t = v.strip()
    return f"{t} months" if re.fullmatch(r"\d+", t) else v


def _format_short_field(value: str, fallback: str) -> str:
    return value.strip() if value and value.strip() else fallback


def _strip_json_fence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    return text.strip()


def generate_fallback_summary(
    service: str,
    flat: dict[str, str],
    technical_specs: str,
    special_considerations: str,
    estimated_scope: str,
    timeline_val: str,
    initiation_next_step: str,
) -> dict[str, str]:
    """TS generateFallbackSummary — returns camelCase keys like TypeScript ProjectSummary."""
    service_name = SERVICE_DISPLAY_NAMES.get(service, service.replace("_", " "))
    area = (
        flat.get("size_sqft")
        or flat.get("areaSqft")
        or flat.get("plot_size_sqft")
        or flat.get("land_size_sqft")
        or ""
    )
    budget = flat.get("budget") or flat.get("budgetRange") or ""
    space_type = flat.get("project_type") or flat.get("spaceType") or flat.get("eventType") or ""
    style = flat.get("style") or ""

    def format_field(value: str, fallback: str) -> str:
        if not value or value.strip() in ("--", ""):
            return fallback
        if len(value) < 20 or "." not in value:
            return f"{value}. Need more inputs"
        return value

    def format_timeline_fb(v: str) -> str:
        if not v or not v.strip():
            return "Need more inputs"
        t = v.strip()
        return f"{t} months" if re.fullmatch(r"\d+", t) else v

    def format_short(value: str, fallback: str) -> str:
        return value.strip() if value and value.strip() else fallback

    display_timeline = format_timeline_fb(timeline_val)
    overview_parts = [
        service_name,
        space_type,
        f"{area} sqft" if area else "",
        style,
        f"{budget} lakhs" if budget else "",
        display_timeline if display_timeline != "Need more inputs" else "",
    ]
    overview_parts = [p for p in overview_parts if p]
    project_overview = (
        f"A {' '.join(overview_parts)} project"
        + (f" with a {display_timeline} timeline" if display_timeline != "Need more inputs" else "")
        + "."
        if len(overview_parts) > 1
        else f"{service_name} project – need more inputs"
    )

    scope_of_work = (
        f"The work involves {technical_specs}."
        if technical_specs
        else (
            f"{service_name} scope"
            + (f" for {space_type}" if space_type else "")
            + (f" covering {area} sqft" if area else "")
            + " – need more inputs."
        )
    )

    client_requirements = (
        f"The client requested {special_considerations}."
        if special_considerations
        else (
            f"Timeline: {display_timeline if display_timeline != 'Need more inputs' else 'Flexible'}"
            + (f", Budget: {budget} lakhs" if budget else "")
            + " – need more inputs."
        )
    )

    return {
        "projectOverview": project_overview,
        "scopeOfWork": scope_of_work,
        "clientRequirements": client_requirements,
        "technicalSpecs": format_short(technical_specs, "Need more inputs"),
        "timeline": display_timeline,
        "specialConsiderations": format_field(special_considerations, "Need more inputs"),
        "estimatedScope": format_short(estimated_scope, "Need more inputs"),
        "initiationNextStep": initiation_next_step,
    }


def _ts_summary_to_project_summary_dict(session: Session, ts: dict[str, str], flat: dict[str, str]) -> dict[str, Any]:
    """Map TS ProjectSummary shape → service-agents ProjectSummary (Pydantic) dict."""
    po = ts.get("projectOverview") or ""
    scope_text = ts.get("scopeOfWork") or ""
    return {
        "session_id": session.session_id,
        "generated_at": datetime.utcnow(),
        "next_step": ts.get("initiationNextStep") or "Follow up via phone.",
        "project_overview": po,
        "scope_of_work": [scope_text] if scope_text.strip() else ["Need more inputs"],
        "client_requirements": ts.get("clientRequirements") or "Need more inputs",
        "technical_specs": ts.get("technicalSpecs") or "Need more inputs",
        "timeline": ts.get("timeline") or "Need more inputs",
        "special_considerations": ts.get("specialConsiderations") or "Need more inputs",
        "estimated_scope": ts.get("estimatedScope") or "Need more inputs",
        "design_direction": (
            (po[:220] + "...") if len(po) > 220 else (po or "Design direction follows the client brief captured in the consultation.")
        ),
        "execution_readiness": ts.get("initiationNextStep")
        or "Confirm scope on a short call, then schedule site visit or proposal as appropriate.",
        "enquiry_snapshot": flat,
    }


async def generate_project_summary_for_session(session: Session, service_id: str) -> dict[str, Any]:
    """
    Same logic as quest `generateProjectSummary(service, parameters, transcript)`.
    """
    from backend.questionnaire.conversation_engine import _get_quest_params

    parameters = _get_quest_params(session)
    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    service_labels = get_parameter_labels_for_service(service_id)
    flat = flatten_params_for_summary(parameters)

    param_summary = "\n".join(
        f"- {service_labels.get(k) or PARAM_LABEL_MAP.get(k) or k.replace('_', ' ')}: {v}"
        for k, v in flat.items()
    )

    technical_specs = build_technical_specs(flat)
    special_considerations = build_special_considerations(flat)
    estimated_scope = format_estimated_scope(flat)
    timeline_val = flat.get("timeline") or flat.get("timelineExpectation") or flat.get("preferred_start") or ""
    contact_pref = flat.get("contact_pref") or "phone"
    default_next_step = f"Follow up via {contact_pref or 'phone'}."

    transcript = session.conversation_history
    if transcript and len(transcript) > 0:
        conversation_text = "\n".join(
            f"{'User' if m.role == MessageRole.USER else 'Assistant'}: {m.content}"
            for m in transcript
            if m.role in (MessageRole.USER, MessageRole.ASSISTANT)
        )

        system_prompt = f"""You are a project consultant. Generate a structured project summary with DISTINCT sections. Each section must have different content – do not repeat the same sentence.

CONVERSATION:
{conversation_text}

COLLECTED DATA (use for accuracy):
{param_summary or '(no labelled params)'}

SERVICE: {service_name}

Return JSON only with these exact keys. Each value: AT LEAST ONE COMPLETE SENTENCE (minimum 15 words), different from the others.

1. "projectOverview": What the project IS – type, scale, property (e.g. "A new 2BHK villa interior design project covering 1200 sqft in Japandi style. Budget is 6 lakhs with a 6-month timeline, starting next month."). Minimum 20 words, maximum 40 words.

2. "scopeOfWork": What will be DONE – which areas/rooms, what services (e.g. "The work involves full interior design and execution for living room, bedrooms, and kitchen. This includes space planning, material selection, finishes, and furniture procurement. No civil work is required."). Minimum 20 words, maximum 35 words.

3. "clientRequirements": What the CLIENT asked for – style, must-haves, preferences, timeline (e.g. "The client specifically requested Japandi style with a 6-month completion timeline, starting next month. They also want a callback tomorrow at 8 PM via phone."). Minimum 20 words, maximum 35 words.

RULES:
- projectOverview = the project in one nutshell (what + scale + budget/timeline). MUST be at least one complete sentence.
- scopeOfWork = the work scope (what we will deliver/execute). MUST be at least one complete sentence.
- clientRequirements = client's stated wants and next step. MUST be at least one complete sentence.
- No duplicate text across the three. No filler ("as discussed", "the client is interested in").
- Be concrete: numbers, rooms, style, timeline. 
- If information is missing, write "Need more inputs" instead of leaving blank or using "--".
- Return JSON only."""

        user_msg = "Generate the project summary JSON with projectOverview, scopeOfWork, clientRequirements."
        llm = get_llm_engine()
        try:
            with quest_llm_phase("summary_project"):
                raw = (
                    await llm.chat(
                        session_id=session.session_id,
                        user_message=user_msg,
                        system_prompt=system_prompt,
                        history=[],
                        temperature=SUMMARY_PROJECT_TEMPERATURE,
                        max_tokens=_summary_max_output_tokens_for_session(session),
                    )
                ).strip()
            json_str = _strip_json_fence(raw)
            parsed = json.loads(json_str)
        except Exception as err:
            err_s = str(err)
            _ = err_s  # same fallback path as quest (API error, blocked, invalid JSON)
            fb = generate_fallback_summary(
                service_id, flat, technical_specs, special_considerations,
                estimated_scope, timeline_val, default_next_step,
            )
            return _ts_summary_to_project_summary_dict(session, fb, flat)

        project_overview = (parsed.get("projectOverview") or "").strip() or f"{service_name} project – details from conversation."
        scope_of_work = (parsed.get("scopeOfWork") or "").strip() or (
            f"Work involves {technical_specs}." if technical_specs else "Need more inputs"
        )
        client_requirements = (parsed.get("clientRequirements") or "").strip() or (
            f"Client requested: {special_considerations}." if special_considerations else "Need more inputs"
        )

        ts_out = {
            "projectOverview": _format_field_long(project_overview, f"{service_name} project – need more inputs"),
            "scopeOfWork": _format_field_long(scope_of_work, "Need more inputs"),
            "clientRequirements": _format_field_long(client_requirements, "Need more inputs"),
            "technicalSpecs": _format_short_field(technical_specs, "Need more inputs"),
            "timeline": _format_timeline(timeline_val),
            "specialConsiderations": _format_field_long(special_considerations, "Need more inputs"),
            "estimatedScope": _format_short_field(estimated_scope, "Need more inputs"),
            "initiationNextStep": default_next_step,
        }
        return _ts_summary_to_project_summary_dict(session, ts_out, flat)

    fb = generate_fallback_summary(
        service_id, flat, technical_specs, special_considerations,
        estimated_scope, timeline_val, default_next_step,
    )
    return _ts_summary_to_project_summary_dict(session, fb, flat)


def get_mood_analysis_summary(mood_meta: dict[str, Any] | None) -> str:
    if not mood_meta or not mood_meta.get("moodHistory"):
        return "No mood data available"
    mood_history = list(mood_meta.get("moodHistory") or [])
    mood_counts: dict[str, int] = {}
    for mood in mood_history:
        mood_counts[str(mood)] = mood_counts.get(str(mood), 0) + 1
    dominant = sorted(mood_counts.items(), key=lambda x: -x[1])[0][0] if mood_counts else "neutral"
    frustration_level = mood_counts.get("frustrated", 0)
    positive_level = mood_counts.get("positive", 0)
    total_turns = len(mood_history)
    sentiment = "neutral"
    if total_turns and positive_level > total_turns * 0.5:
        sentiment = "positive"
    elif frustration_level > 0:
        sentiment = "had friction"
    elif mood_counts.get("rushed", 0) > total_turns * 0.3:
        sentiment = "was rushed"
    elif mood_counts.get("uncertain", 0) > total_turns * 0.3:
        sentiment = "needed guidance"
    return (
        f"Dominant mood: {dominant} | Overall sentiment: {sentiment} | "
        f"Frustration points: {frustration_level} | Positive moments: {positive_level}"
    )


def get_conversation_duration(session: Session) -> str:
    try:
        start = session.created_at.timestamp() if session.created_at else None
        end = session.last_active.timestamp() if session.last_active else None
        if start is None or end is None:
            return "Unknown"
        duration_ms = (end - start) * 1000
        if duration_ms < 60000:
            return "Less than 1 minute"
        if duration_ms < 3600000:
            return f"{max(1, round(duration_ms / 60000))} minutes"
        return f"{max(1, round(duration_ms / 3600000))} hours"
    except Exception:
        return "Unknown"


def generate_fallback_six_point_summary(
    session: Session,
    service_id: str,
    flat: dict[str, str],
    mood_summary: str,
) -> dict[str, Any]:
    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    ch = session.channel or "web"
    turns = len([m for m in session.conversation_history if m.role in (MessageRole.USER, MessageRole.ASSISTANT)])
    return {
        "client_profile": f"{ch} inquiry | Contact: {flat.get('contact_pref') or 'Not specified'}",
        "project_scope": (
            f"{service_name} - {flat.get('project_type') or flat.get('spaceType') or 'Type not specified'} | "
            f"{flat.get('rooms') or ''} | {flat.get('size_sqft') or flat.get('areaSqft') or 'Size not specified'}"
        ),
        "key_requirements": (
            f"Style: {flat.get('style') or 'Not specified'} | "
            f"Focus: {flat.get('notes') or flat.get('must_haves') or 'None specified'}"
        ),
        "budget_timeline": (
            f"Budget: {flat.get('budget') or flat.get('budgetRange') or 'Not specified'} | "
            f"Timeline: {flat.get('timeline') or 'Flexible'}"
        ),
        "conversation_insights": f"{turns} turns | {mood_summary}",
        "next_steps": f"Follow up via {flat.get('contact_pref') or 'phone'}",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mood_summary": mood_summary,
    }


async def generate_six_point_summary_for_session(session: Session, service_id: str) -> dict[str, Any]:
    """Port of quest `generateSixPointSummary(doc)`."""
    from backend.questionnaire.conversation_engine import _get_quest_params

    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    parameters = _get_quest_params(session)
    flat = flatten_params_for_summary(parameters)
    param_summary = "\n".join(f"- {k}: {v}" for k, v in flat.items())

    conversation_length = len(session.conversation_history)
    user_messages = len([m for m in session.conversation_history if m.role == MessageRole.USER])
    mood_meta = session.extracted_fields.get(QUEST_META)
    if not isinstance(mood_meta, dict):
        mood_meta = {}
    mood_summary = get_mood_analysis_summary(mood_meta)

    system_prompt = f"""You are an executive assistant creating a concise 6-point summary for a project manager.

SERVICE: {service_name}
CHANNEL: {session.channel or 'web'}

COLLECTED DATA:
{param_summary or '(none)'}

CONVERSATION STATS:
- Total turns: {conversation_length}
- User messages: {user_messages}
- Duration: {get_conversation_duration(session)}

MOOD ANALYSIS:
{mood_summary}

Generate a JSON with exactly 6 fields. Each field: AT LEAST ONE COMPLETE SENTENCE (minimum 10 words, maximum 25 words). No filler. Factual only. If information is missing, write "Need more inputs" instead of leaving blank or using "--".

{{
  "clientProfile": "Brief client description - contact preference, communication style, urgency level. Must be at least one complete sentence.",
  "projectScope": "What they want - type, size, style in one complete sentence.",
  "keyRequirements": "Must-haves, special focus areas, things to avoid. Must be at least one complete sentence.",
  "budgetTimeline": "Budget and timeline in simple format. Must be at least one complete sentence.",
  "conversationInsights": "How the conversation went - was client clear, confused, rushed? Any friction points? Must be at least one complete sentence.",
  "nextSteps": "Recommended follow-up action based on their contact preference and callback time. Must be at least one complete sentence."
}}

Be factual and concise. Each field must be a complete sentence. Return JSON only."""

    llm = get_llm_engine()
    try:
        with quest_llm_phase("summary_six_point"):
            raw = (
                await llm.chat(
                    session_id=session.session_id,
                    user_message="Generate the 6-point summary JSON.",
                    system_prompt=system_prompt,
                    history=[],
                    temperature=SUMMARY_SIX_POINT_TEMPERATURE,
                    max_tokens=_summary_max_output_tokens_for_session(session),
                )
            ).strip()
        json_str = _strip_json_fence(raw)
        parsed = json.loads(json_str)
    except Exception as err:
        err_s = str(err)
        is_blocked = any(x in err_s for x in ("blocked", "SAFETY", "RECITATION"))
        if not is_blocked:
            pass
        return generate_fallback_six_point_summary(session, service_id, flat, mood_summary)

    def fmt(v: str) -> str:
        s = (v or "").strip()
        if not s or s == "--":
            return "Need more inputs"
        return s

    return {
        "client_profile": fmt(parsed.get("clientProfile")),
        "project_scope": fmt(parsed.get("projectScope")),
        "key_requirements": fmt(parsed.get("keyRequirements")),
        "budget_timeline": fmt(parsed.get("budgetTimeline")),
        "conversation_insights": fmt(parsed.get("conversationInsights")),
        "next_steps": fmt(parsed.get("nextSteps")),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mood_summary": mood_summary,
    }
