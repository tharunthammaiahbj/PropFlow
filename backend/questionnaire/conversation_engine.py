"""
Quest questionnaire engine — faithful port of quest-characters
`apps/questionnaire/src/engine/conversation.ts` + message flow from
`apps/questionnaire/src/routes.ts` (confirmation filter, agreed-to-call).

Session mapping:
- `Session.conversation_history` ↔ QuestionnaireDoc.transcript
- `Session.extracted_fields[QUEST_PARAMETERS]` ↔ parameters
- `Session.extracted_fields[QUEST_META]` ↔ conversationMeta (mood, moodHistory, …;
  `lastNeedsConfirmation` is preserved on merge)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal, Optional

from backend.config import get_settings
from backend.intelligence.llm_engine import get_llm_engine
from backend.utils.logger import log_event
from backend.utils.perf_analytics import quest_llm_phase
from backend.intelligence.persona import get_base_identity_by_persona_key
from backend.questionnaire.coverage_policy import get_required_fields_for_service, is_coverage_satisfied
from backend.questionnaire.generated.service_parameters_generated import SERVICE_PARAMS
from backend.questionnaire.service_codes import get_display_name_by_service_code
from backend.schemas.session import ConversationStage, MessageRole, Session

GEN_DIR = Path(__file__).resolve().parent / "generated"

QUEST_SERVICE_ID = "__quest:service_id"
QUEST_PARAMETERS = "__quest:parameters"
QUEST_META = "__quest:conversation_meta"
QUEST_SUMMARY = "__quest:project_summary"
QUEST_CONVERSATION_FLOW = "__quest:conversationFlow"
QUEST_LAST_ASK = "__quest:lastAsk"
# Fix #7: ask-count guard. Per-field counter stored under session.extracted_fields.
# When the same field has been asked N consecutive times without the user
# answering (extraction kept dropping signal), we auto-skip it by injecting
# a low-confidence placeholder so we don't loop on it forever.
QUEST_ASK_COUNTS = "__quest:askCounts"
ASK_COUNT_SKIP_THRESHOLD = int(os.getenv("QUEST_ASK_COUNT_SKIP_THRESHOLD", "2"))
# Voice ack-rotation: track the leading acknowledgement ("got it"/"nice"/...)
# from the previous assistant turn so we can dedupe consecutive identical acks.
VOICE_LAST_ACK = "__voice:lastAck"

UserMood = Literal["positive", "neutral", "confused", "frustrated", "rushed", "uncertain"]

EXTRACTION_CONFIDENCE_THRESHOLD_AUTO = float(os.getenv("EXTRACTION_CONFIDENCE_THRESHOLD_AUTO", "0.65"))
EXTRACTION_CONFIDENCE_THRESHOLD_TENTATIVE = float(os.getenv("EXTRACTION_CONFIDENCE_THRESHOLD_TENTATIVE", "0.4"))
MAX_TURNS_BEFORE_DIRECT_ASK = int(os.getenv("MAX_TURNS_BEFORE_DIRECT_ASK", "3"))
QUEST_LLM_TEMPERATURE = float(os.getenv("QUEST_LLM_TEMPERATURE", "0.35"))
# Match quest-characters `packages/ai/src/adapters/gemini-api.ts` generateJSON default `maxTokens = 2048`
# (assistant `generateText` does not pass maxTokens, so 2048 applies). Override via env if needed.
QUEST_GEMINI_MAX_OUTPUT_DEFAULT = int(os.getenv("QUEST_GEMINI_MAX_OUTPUT_DEFAULT", "2048"))
# NOTE on VOICE cap bump from 220 → 320:
# On reasoning-capable Groq models (gpt-oss-20b), the hidden chain-of-thought
# consumes part of the max_tokens budget even for short spoken replies. At 220
# we saw production truncations like "Got it. Roughly how many square feet is
# the carpet" — the final word "area?" got cut off. 320 leaves ~100 extra
# tokens of headroom while keeping voice replies well under the TTS budget
# (optimize_for_voice trims to 65 words regardless).
QUEST_GEMINI_MAX_OUTPUT_VOICE = int(os.getenv("QUEST_GEMINI_MAX_OUTPUT_VOICE", "320"))
# Max tokens for the extraction JSON LLM call (lower = faster; too low may truncate JSON).
QUEST_EXTRACTION_MAX_OUTPUT = int(os.getenv("QUEST_EXTRACTION_MAX_OUTPUT", "1024"))
# Voice-specific extraction cap. Voice turns extract one (sometimes two) parameters per turn,
# never more than ~150 output tokens of JSON. A tighter cap reduces tail-latency variance from
# ~300–1300 ms down to a much narrower band (Gemini's response time scales with completion size).
QUEST_EXTRACTION_MAX_OUTPUT_VOICE = int(os.getenv("QUEST_EXTRACTION_MAX_OUTPUT_VOICE", "384"))
# Single LLM call: extraction + main assistant prompt in one JSON response (fallback to two-call path on failure / ineligible turns).
# Default on for latency; set QUEST_MERGED_EXTRACT_REPLY=false to force classic extraction + reply only.
_merged_env = (os.getenv("QUEST_MERGED_EXTRACT_REPLY", "true") or "true").strip().lower()
QUEST_MERGED_EXTRACT_REPLY = _merged_env not in ("0", "false", "no", "off")
_voice_merged_env = (
    os.getenv("VOICE_USE_MERGED_EXTRACT_REPLY", "false") or "false"
).strip().lower()
VOICE_USE_MERGED_EXTRACT_REPLY = _voice_merged_env not in ("0", "false", "no", "off")
QUEST_MERGED_MAX_OUTPUT = int(os.getenv("QUEST_MERGED_MAX_OUTPUT", "1536"))
# Prompt size caps (override via env if quality regresses on long threads).
MAX_CONTEXT_TURNS = int(os.getenv("MAX_CONTEXT_TURNS", "4"))
QUEST_PERSONA_PROMPT_CHARS = int(os.getenv("QUEST_PERSONA_PROMPT_CHARS", "450"))
QUEST_TRANSCRIPT_LINE_MAX_CHARS = int(os.getenv("QUEST_TRANSCRIPT_LINE_MAX_CHARS", "360"))
QUEST_TRANSCRIPT_TOTAL_MAX_CHARS = int(os.getenv("QUEST_TRANSCRIPT_TOTAL_MAX_CHARS", "2800"))

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

MOOD_INDICATORS: dict[str, list[str]] = {
    "positive": [
        "great", "wonderful", "love", "excited", "yes", "perfect", "awesome", "sure",
        "definitely", "amazing", "happy",
    ],
    "confused": [
        "what", "huh", "dont understand", "don't understand", "confused", "not sure",
        "unclear", "explain", "like?", "meaning", "how",
    ],
    "frustrated": [
        "already said", "told you", "again", "why", "stop", "enough", "too many",
        "long", "heavy", "boring",
    ],
    "rushed": ["quick", "fast", "hurry", "asap", "urgent", "immediately", "now", "today"],
    "uncertain": [
        "maybe", "not sure", "no idea", "suggest", "help me", "idk", "dont know",
        "don't know", "later", "decide later",
    ],
}

AMBIGUITY_PHRASES = [
    "something like that", "maybe", "kind of", "sort of", "not sure", "i guess",
    "probably", "around", "approximately", "more or less", "depends", "flexible",
    "later", "will decide", "not decided", "no idea",
]

CLARIFICATION_REQUEST_PHRASES = [
    "like?", "like ?", "like what", "such as", "for example", "examples?",
    "suggest me", "suggest", "you tell me", "what do you mean", "explain",
    "options?", "what options", "can you explain", "meaning?", "which ones",
    "help me", "help me decide", "what should i", "what would you",
    "hmm", "umm", "not sure what",
]

PREFERRED_ORDER = [
    "project_type",
    "size_sqft",
    "rooms",
    "style",
    "must_haves",
    "avoid",
    "site_ready",
    "lighting_pref",
    "materials",
    "design_style",
    "moodboard_refs",
    "notes",
    "budget",
    "timeline",
    "contact_pref",
    "preferred_start",
]

_last_used_starter = ""


def _read_template(name: str) -> str:
    return (GEN_DIR / f"{name}.txt").read_text(encoding="utf-8")


ASSISTANT_PROMPT_TEMPLATE = _read_template("ASSISTANT_PROMPT_TEMPLATE")
OPENING_PROMPT_TEMPLATE = _read_template("OPENING_PROMPT_TEMPLATE")
CLOSING_PROMPT_TEMPLATE = _read_template("CLOSING_PROMPT_TEMPLATE")
EXTRACTION_PROMPT_TEMPLATE = _read_template("EXTRACTION_PROMPT_TEMPLATE")


def _has_service_params(service: str) -> bool:
    return service in SERVICE_PARAMS


def get_required_ids_for_service(service: str) -> list[str]:
    s = SERVICE_PARAMS.get(service)
    return [p["id"] for p in s["required"]] if s else []


def get_optional_ids_for_service(service: str) -> list[str]:
    s = SERVICE_PARAMS.get(service)
    return [p["id"] for p in s["optional"]] if s else []


def get_datapoints_for_service(service: str) -> list[dict[str, Any]]:
    s = SERVICE_PARAMS.get(service)
    if not s:
        return []
    points = [{**p, "priority": 1} for p in s["required"]] + [{**p, "priority": 2} for p in s["optional"]]
    # callback_time is deprecated; never collect it.
    points = [p for p in points if p.get("id") != "callback_time"]
    return points


_POST_COMPLETION_REOPEN_PATTERN = re.compile(
    r"\b(wrong|mistake|change|update|correct|instead|different|actually|"
    r"not what|meant to|new number|another number|call me at|reach me at|"
    r"whatsapp is|email is|reschedule|cancel)\b",
    re.I,
)


def post_completion_user_requests_data_change(message: str) -> bool:
    """
    After summaries ran, only re-open the full quest pipeline when the user is clearly
    correcting data or adding contact / schedule info. Casual follow-ups ("cool", "nice")
    must not trigger optional-field questions again.
    """
    s = (message or "").strip()
    if not s:
        return False
    if len(s) > 280:
        return True
    return bool(_POST_COMPLETION_REOPEN_PATTERN.search(s))


def shuffle(arr: list) -> list:
    out = list(arr)
    for i in range(len(out) - 1, 0, -1):
        j = random.randint(0, i)
        out[i], out[j] = out[j], out[i]
    return out


def _get_service_id(session: Session) -> str:
    sid = session.extracted_fields.get(QUEST_SERVICE_ID)
    if isinstance(sid, str) and sid:
        return sid
    if session.service_code:
        from backend.questionnaire.service_codes import resolve_service_id

        return resolve_service_id(session.service_code)
    return "residential_interiors"


def ensure_quest_service(session: Session) -> str:
    if isinstance(session.extracted_fields.get(QUEST_SERVICE_ID), str) and session.extracted_fields.get(QUEST_SERVICE_ID):
        return str(session.extracted_fields[QUEST_SERVICE_ID])
    if session.service_code:
        from backend.questionnaire.service_codes import resolve_service_id

        sid = resolve_service_id(session.service_code)
        session.extracted_fields[QUEST_SERVICE_ID] = sid
        return sid
    sid = "residential_interiors"
    session.extracted_fields[QUEST_SERVICE_ID] = sid
    return sid


def _get_quest_params(session: Session) -> dict[str, Any]:
    raw = session.extracted_fields.get(QUEST_PARAMETERS, {})
    return dict(raw) if isinstance(raw, dict) else {}


def _set_quest_params(session: Session, params: dict[str, Any]) -> None:
    session.extracted_fields[QUEST_PARAMETERS] = params


def _merge_meta(session: Session, updates: dict[str, Any]) -> None:
    meta = dict(session.extracted_fields.get(QUEST_META) or {})
    preserve_lnc = meta.get("lastNeedsConfirmation")
    meta.update(updates)
    if preserve_lnc is not None and "lastNeedsConfirmation" not in updates:
        meta["lastNeedsConfirmation"] = preserve_lnc
    session.extracted_fields[QUEST_META] = meta


def get_conversation_state(session: Session) -> dict[str, Any]:
    meta = session.extracted_fields.get(QUEST_META) or {}
    return {
        "mood": meta.get("mood", "neutral"),
        "moodHistory": list(meta.get("moodHistory") or []),
        "ambiguousFields": list(meta.get("ambiguousFields") or []),
        "clarificationCount": int(meta.get("clarificationCount") or 0),
        "turnCount": len(session.conversation_history),
        "lastNeedsConfirmation": meta.get("lastNeedsConfirmation"),
    }


def update_conversation_state_preserve_confirmation(session: Session, state: dict[str, Any]) -> None:
    lnc = state.pop("lastNeedsConfirmation", None)
    prev = dict(session.extracted_fields.get(QUEST_META) or {})
    if lnc is None and "lastNeedsConfirmation" in prev:
        lnc = prev["lastNeedsConfirmation"]
    prev.update(state)
    if lnc is not None:
        prev["lastNeedsConfirmation"] = lnc
    session.extracted_fields[QUEST_META] = prev


def detect_mood(message: str, previous_mood: str) -> UserMood:
    lower = message.lower()
    for mood, indicators in MOOD_INDICATORS.items():
        if any(ind in lower for ind in indicators):
            return mood  # type: ignore[return-value]
    if len(message) < 15 and "?" not in lower:
        return "neutral"
    return (previous_mood or "neutral")  # type: ignore[return-value]


def detect_ambiguity(message: str) -> bool:
    lower = message.lower()
    return any(phrase in lower for phrase in AMBIGUITY_PHRASES)


def is_asking_for_clarification(message: str) -> bool:
    lower = message.lower().strip()
    if len(lower) < 15 and ("?" in lower or "like" in lower):
        return True
    return any(phrase in lower for phrase in CLARIFICATION_REQUEST_PHRASES)


def sort_pending(pending: list[dict[str, Any]], service_id: str = "") -> list[dict[str, Any]]:
    # Build service-defined position index (required fields first in their defined order, then optional).
    service_order: dict[str, int] = {}
    if service_id and service_id in SERVICE_PARAMS:
        svc = SERVICE_PARAMS[service_id]
        all_fields = list(svc.get("required") or []) + list(svc.get("optional") or [])
        service_order = {str(p.get("id") or ""): i for i, p in enumerate(all_fields) if p.get("id")}

    def key_fn(p: dict[str, Any]) -> tuple:
        # Primary: service-defined position.
        svc_pos = service_order.get(p["id"], 10**6)
        # Secondary: generic cross-service tiebreaker.
        ia = PREFERRED_ORDER.index(p["id"]) if p["id"] in PREFERRED_ORDER else 10**6
        pa = p.get("priority") or 99
        return (svc_pos, pa, ia, p["id"])

    return sorted(pending, key=key_fn)


def collect_pending_datapoints(service_id: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    points = get_datapoints_for_service(service_id)
    # Policy: callback_time is not collected on voice/WhatsApp. Never ask it.
    points = [p for p in points if p.get("id") != "callback_time"]
    pending = [p for p in points if p["id"] not in (parameters or {})]
    # Conditional schema-driven filtering (e.g., solar ground-mount vs rooftop).
    # `project_type` may be stored as a plain string or as {"value": "..."}.
    project_type_raw = (parameters or {}).get("project_type")
    project_type_val = None
    if isinstance(project_type_raw, dict):
        project_type_val = project_type_raw.get("value")
    else:
        project_type_val = project_type_raw
    if isinstance(project_type_val, str):
        project_type_val = project_type_val.strip()
    else:
        project_type_val = None

    if project_type_val:
        filtered: list[dict[str, Any]] = []
        for p in pending:
            # Remove any field that has skip_if_project_type matching captured project_type.
            if str(p.get("skip_if_project_type") or "").strip() == project_type_val:
                continue
            # Remove any field that has only_if_project_type that does NOT match captured project_type.
            only_if = str(p.get("only_if_project_type") or "").strip()
            if only_if and only_if != project_type_val:
                continue
            filtered.append(p)
        pending = filtered
    # IMPORTANT: keep pending ordering deterministic.
    # Random shuffles can cause the engine to "think" it asked for a different field than what
    # the assistant actually asked, which leads to repeated questions (e.g., wardrobes/lighting/BHK).
    if _has_service_params(service_id):
        return sort_pending(pending, service_id)
    return sort_pending(pending, service_id)


def build_transcript(session: Session) -> str:
    turns = [m for m in session.conversation_history if m.role in (MessageRole.USER, MessageRole.ASSISTANT)]
    tail = turns[-MAX_CONTEXT_TURNS:]
    lines = []
    line_max = max(120, QUEST_TRANSCRIPT_LINE_MAX_CHARS)
    for t in tail:
        label = "User" if t.role == MessageRole.USER else "Assistant"
        raw = t.content or ""
        if len(raw) > line_max:
            raw = raw[: line_max - 1] + "…"
        lines.append(f"{label}: {raw}")
    out = "\n".join(lines)
    cap = max(800, QUEST_TRANSCRIPT_TOTAL_MAX_CHARS)
    if len(out) > cap:
        out = out[-cap:]
    return out


def format_pending(pending: list[dict[str, Any]]) -> str:
    lst = "\n".join(
        f"- [{p['id']}] {p.get('label') or p['id']}{((': ' + p['hint']) if p.get('hint') else '')}"
        for p in pending
    )
    return f"Ask these fields in EXACTLY this order. Do not skip, reorder, or invent any question not in this list:\n{lst}"


def format_collected_params(parameters: dict[str, Any]) -> str:
    if not parameters:
        return "None yet"
    lines = []
    for key, val in parameters.items():
        v = val["value"] if isinstance(val, dict) and "value" in val else val
        lines.append(f"- {key}: {v}")
    return "\n".join(lines)


def _format_whatsapp_review_recap(service_id: str, parameters: dict[str, Any]) -> str:
    """
    User-facing WhatsApp recap:
    - schema-driven labels (no raw keys)
    - consistent ordering across services
    - compress related info onto fewer lines for aesthetics
    """
    if not parameters:
        return ""

    flat: dict[str, str] = {}
    for k, v in (parameters or {}).items():
        if v is None:
            continue
        if isinstance(v, dict) and "value" in v:
            flat[k] = str(v.get("value") or "").strip()
        else:
            flat[k] = str(v).strip()

    def nice_value(k: str, raw: str) -> str:
        low = (raw or "").strip().lower()
        if low in {"not specified", "not provided", "not mentioned"}:
            return "Not shared yet"
        return (raw or "").strip()

    # Build labeled values (schema-driven).
    labeled: dict[str, str] = {}
    for k, raw in flat.items():
        if raw == "":
            continue
        label = _get_param_label(service_id, k) or k.replace("_", " ").strip().title()
        labeled[k] = f"{label}: {nice_value(k, raw)}"

    # Cross-service consistent “core first” ordering for recap.
    core_order = [
        "project_type",
        "rooms",
        "size_sqft",
        "plot_size_sqft",
        "floors",
        "roof_type",
        "capacity_kw",
        "grid_type",
        "budget",
        "financing",
        "timeline",
        "preferred_start",
        "location",
        "contact_pref",
    ]
    ordered_keys = [k for k in core_order if k in labeled] + [k for k in labeled.keys() if k not in core_order]

    # Lightweight grouping to reduce “key spam”.
    lines: list[str] = []
    # Property / scope line.
    prop_parts = []
    for k in ("project_type", "rooms"):
        if k in flat and flat.get(k):
            prop_parts.append(nice_value(k, flat[k]))
    # Add floors/area hints when present.
    for k in ("floors", "plot_size_sqft", "size_sqft"):
        if k in flat and flat.get(k):
            v = nice_value(k, flat[k])
            if k.endswith("_sqft") and re.fullmatch(r"\d+(\.\d+)?", v):
                v = f"{v} sqft"
            prop_parts.append(v)
    if prop_parts:
        lines.append(f"- Property: " + ", ".join(prop_parts[:4]))

    # Approvals / soil test line (construction-heavy, but safe across services).
    approvals = []
    if "has_soil_test" in flat and flat.get("has_soil_test"):
        approvals.append(f"Soil test: {nice_value('has_soil_test', flat['has_soil_test'])}")
    if "has_approvals" in flat and flat.get("has_approvals"):
        approvals.append(f"Approvals: {nice_value('has_approvals', flat['has_approvals'])}")
    if approvals:
        lines.append("- " + " / ".join(approvals))

    # Budget / finance line.
    bf = []
    if "budget" in flat and flat.get("budget"):
        bf.append(f"Budget: {nice_value('budget', flat['budget'])}")
    if "financing" in flat and flat.get("financing"):
        bf.append(f"Financing: {nice_value('financing', flat['financing'])}")
    if bf:
        lines.append("- " + " | ".join(bf))

    # Timeline / start line.
    ts = []
    if "timeline" in flat and flat.get("timeline"):
        ts.append(f"Timeline: {nice_value('timeline', flat['timeline'])}")
    if "preferred_start" in flat and flat.get("preferred_start"):
        ts.append(f"Start: {nice_value('preferred_start', flat['preferred_start'])}")
    if ts:
        lines.append("- " + " | ".join(ts))

    # Location / contact line.
    lc = []
    if "location" in flat and flat.get("location"):
        lc.append(f"Location: {nice_value('location', flat['location'])}")
    if "contact_pref" in flat and flat.get("contact_pref"):
        lc.append(f"Contact: {nice_value('contact_pref', flat['contact_pref'])}")
    if lc:
        lines.append("- " + " | ".join(lc))

    # Add remaining fields (not already represented) in a stable, labeled way.
    represented = set()
    for k in ("project_type", "rooms", "floors", "plot_size_sqft", "size_sqft", "has_soil_test", "has_approvals",
              "budget", "financing", "timeline", "preferred_start", "location", "contact_pref"):
        represented.add(k)
    for k in ordered_keys:
        if k in represented:
            continue
        lines.append(f"- {labeled[k]}")

    # Cap to keep it WhatsApp-friendly.
    return "\n".join(lines[:8]).strip()

def get_last_user_message(session: Session) -> str:
    for m in reversed(session.conversation_history):
        if m.role == MessageRole.USER:
            return m.content
    return ""


def get_last_assistant_message(session: Session) -> str:
    for m in reversed(session.conversation_history):
        if m.role == MessageRole.ASSISTANT:
            return m.content
    return ""


def clean_json_result(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


def flatten_parameters(parameters: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, val in (parameters or {}).items():
        if val is None:
            continue
        if isinstance(val, dict) and "value" in val:
            out[k] = str(val.get("value", ""))
        else:
            out[k] = str(val)
    return out


def get_param_value(parameters: dict[str, Any], key: str) -> Any:
    val = parameters.get(key)
    if val is None:
        return None
    if isinstance(val, dict) and "value" in val:
        return val.get("value")
    return val


def _get_param_label(service_id: str, param_id: str) -> str:
    try:
        svc = SERVICE_PARAMS.get(service_id) or {}
        for p in (svc.get("required") or []) + (svc.get("optional") or []):
            if p.get("id") == param_id:
                return str(p.get("label") or "")
    except Exception:
        pass
    return ""


def _append_conversation_flow_answer(session: Session, *, service_id: str, user_answer: str) -> None:
    """
    Build quest-style conversationFlow (question+answer pairs).
    We keep a single pending "last ask" record, and on the next user message we append it.
    """
    meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    last_ask = meta.get(QUEST_LAST_ASK)
    if not isinstance(last_ask, dict):
        return
    if last_ask.get("answered"):
        return
    q = str(last_ask.get("question") or "").strip()
    if not q:
        return
    asked_param = str(last_ask.get("askedParam") or "").strip()
    label = str(last_ask.get("parameterLabel") or "").strip()
    if asked_param and not label:
        label = _get_param_label(service_id, asked_param)

    flow = meta.get(QUEST_CONVERSATION_FLOW)
    if not isinstance(flow, list):
        flow = []
    flow.append(
        {
            "askedParam": asked_param,
            "parameterLabel": label,
            "question": q,
            "answer": (user_answer or "").strip(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "files": [],
        }
    )
    meta[QUEST_CONVERSATION_FLOW] = flow
    last_ask["answered"] = True
    meta[QUEST_LAST_ASK] = last_ask
    session.extracted_fields = meta


def _looks_like_suggestion_request(message: str) -> bool:
    """
    Detect "you tell me / suggest" style requests. These are NOT domain questions
    mid-questionnaire — they mean "recommend a value for the current field".
    """
    s = " ".join((message or "").strip().lower().split())
    if not s:
        return False
    triggers = (
        "you tell me",
        "you decide",
        "you choose",
        "up to you",
        "your call",
        "whatever you think",
        "suggest",
        "recommend",
        "give me a suggestion",
        "give me a recommendation",
        "what do you recommend",
        "what would you suggest",
        "help me decide",
        "help me choose",
        "any idea",
        "any recommendation",
    )
    return any(t in s for t in triggers)


def _suggest_capacity_kw(parameters: dict[str, Any]) -> int | None:
    """
    Conservative kW suggestion from existing context.
    Priority: consumption_units (if numeric) → size_sqft → None.
    """
    def gv(fid: str) -> str:
        v = parameters.get(fid)
        if isinstance(v, dict) and "value" in v:
            return str(v.get("value") or "").strip()
        return str(v or "").strip()

    # 1) consumption_units (units/month) → ~ units/120 kW heuristic
    cu = gv("consumption_units")
    m = re.search(r"(\d+)", cu)
    if m:
        units = int(m.group(1))
        if 30 <= units <= 5000:
            kw = max(1, min(20, round(units / 120)))
            return int(kw)

    # 2) size_sqft → ~ sqft/600 kW heuristic (roof area proxy)
    ss = gv("size_sqft")
    m2 = re.search(r"(\d{2,6})", ss)
    if m2:
        sqft = int(m2.group(1))
        if 100 <= sqft <= 200000:
            kw = max(1, min(20, round(sqft / 600)))
            return int(kw)

    return None


def normalize_extraction_keys_ts(
    parsed: dict[str, Any],
    allowed_ids: set[str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in (parsed or {}).items():
        if not val:
            continue
        normalized = re.sub(r"[^a-z0-9_]", "", key.replace(" ", "_").lower())
        exact_id = None
        if key in allowed_ids:
            exact_id = key
        elif normalized in allowed_ids:
            exact_id = normalized
        else:
            for aid in allowed_ids:
                if aid.replace("_", "") == normalized.replace("_", ""):
                    exact_id = aid
                    break
        if exact_id:
            out[exact_id] = val
    return out


def fallback_regex_extraction(
    message: str,
    is_ambiguous: bool,
    allowed_ids: set[str],
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    base_confidence = 0.5 if is_ambiguous else 0.8

    def allow(fid: str) -> bool:
        return len(allowed_ids) == 0 or fid in allowed_ids

    def pick_sqft_id() -> str:
        for fid in allowed_ids:
            if re.search(r"sqft|size_sqft|plot_size|land_size", fid):
                return fid
        return "size_sqft"

    if allow("budget"):
        budget_match = re.search(r"(\d[\d,\.]*)\s*(lakhs?|lacs?|l\b|rs|inr|usd|k\b)", message, re.I)
        if budget_match:
            parsed["budget"] = {"value": budget_match.group(0), "confidence": base_confidence, "isAmbiguous": is_ambiguous}
    if allow("timeline"):
        duration_match = re.search(r"(\d+)\s*(days?|weeks?|months?)", message, re.I)
        if duration_match:
            parsed["timeline"] = {"value": duration_match.group(0), "confidence": base_confidence, "isAmbiguous": is_ambiguous}
    if allow("rooms"):
        bhk_match = re.search(r"(\d+)\s*bhk", message, re.I)
        if bhk_match:
            parsed["rooms"] = {"value": bhk_match.group(0).upper(), "confidence": 0.95, "isAmbiguous": False}
    sqft_match = re.search(r"(\d{3,6})\s*(sqft|sq\.?\s*ft|square\s*feet?|sft)", message, re.I)
    if sqft_match:
        sid = pick_sqft_id()
        if allow(sid):
            parsed[sid] = {"value": int(sqft_match.group(1)), "confidence": 0.9, "isAmbiguous": False}
    if allow("project_type") and not re.search(r"\b(for\s+my|for\s+our|support\s+for)\s+home\b", message, re.I):
        low = message.lower()
        if re.search(r"\b(villa|bungalow)\b", low):
            parsed["project_type"] = {"value": "villa", "confidence": 0.95, "isAmbiguous": False}
        elif re.search(r"\b(apartment|flat|apt)\b", low):
            parsed["project_type"] = {"value": "apartment", "confidence": 0.95, "isAmbiguous": False}
        elif re.search(r"\b(house|home|independent)\b", low):
            parsed["project_type"] = {"value": "independent house", "confidence": 0.85, "isAmbiguous": False}
    if allow("style"):
        low = message.lower()
        if re.search(r"\b(traditional|classic|old\s*style|vintage|heritage)\b", low):
            parsed["style"] = {"value": "traditional", "confidence": 0.85, "isAmbiguous": is_ambiguous}
        elif re.search(r"\b(modern|contemporary|minimal)", low):
            parsed["style"] = {"value": "modern", "confidence": 0.85, "isAmbiguous": is_ambiguous}
    if allow("contact_pref"):
        low = message.lower()
        if re.search(r"\b(phone|call|mobile)\b", low):
            parsed["contact_pref"] = {"value": "phone", "confidence": 0.95, "isAmbiguous": False}
        elif re.search(r"\b(whatsapp|wa)\b", low):
            parsed["contact_pref"] = {"value": "whatsapp", "confidence": 0.95, "isAmbiguous": False}
        elif re.search(r"\b(email|mail)\b", low):
            parsed["contact_pref"] = {"value": "email", "confidence": 0.95, "isAmbiguous": False}
    if allow("callback_time"):
        low = message.lower()
        if re.search(r"\b(now|right now|immediately|right away|asap)\b", low):
            parsed["callback_time"] = {"value": "now", "confidence": 0.95, "isAmbiguous": False}
        else:
            time_match = re.search(
                r"\b(tomorrow|today|evening|morning|afternoon|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|(\d{1,2})\s*(pm|am)?)\b",
                message,
                re.I,
            )
            if time_match:
                parsed["callback_time"] = {"value": time_match.group(0), "confidence": 0.85, "isAmbiguous": is_ambiguous}
    if allow("floors"):
        floors_match = re.search(r"(G\+?\s*\d+|\d+\s*floors?)", message, re.I)
        if floors_match:
            parsed["floors"] = {"value": re.sub(r"\s+", "", floors_match.group(0)), "confidence": 0.9, "isAmbiguous": False}
    if allow("has_soil_test"):
        if re.search(r"\b(yes|done|completed)\b.*\b(soil|test)\b", message, re.I) or re.search(
            r"\b(soil|test)\b.*\b(yes|done)\b", message, re.I
        ):
            parsed["has_soil_test"] = {"value": "yes", "confidence": 0.85, "isAmbiguous": False}
        elif re.search(r"\b(no|not yet)\b.*\b(soil|test)\b", message, re.I):
            parsed["has_soil_test"] = {"value": "no", "confidence": 0.85, "isAmbiguous": False}
    if allow("has_approvals"):
        if re.search(r"\b(yes|done|sanctioned)\b.*\b(approval|plan|sanction)\b", message, re.I) or re.search(
            r"\b(approval|plan)\b.*\b(yes|done)\b", message, re.I
        ):
            parsed["has_approvals"] = {"value": "yes", "confidence": 0.85, "isAmbiguous": False}
        elif re.search(r"\b(no|pending)\b.*\b(approval|plan)\b", message, re.I):
            parsed["has_approvals"] = {"value": "no", "confidence": 0.85, "isAmbiguous": False}
    return parsed


def validate_extraction_context(
    parsed: dict[str, Any],
    last_bot_msg: str,
    user_msg: str,
    service_id: str = "",
) -> dict[str, Any]:
    lower = last_bot_msg.lower()
    asked_about_callback = (
        "call" in lower
        or "contact" in lower
        or "reach" in lower
        or ("when" in lower and ("good time" in lower or "chat" in lower))
    )
    if asked_about_callback:
        if re.search(r"\b(now|right now|immediately|right away|asap)\b", user_msg, re.I):
            parsed["callback_time"] = {"value": "now", "confidence": 0.95, "isAmbiguous": False}
            parsed.pop("preferred_start", None)
        elif re.search(r"tomorrow|today|evening|morning|next week|\d+\s*(pm|am)", user_msg, re.I):
            if "callback_time" not in parsed:
                m = re.search(r"tomorrow|today|evening|morning|next week|\d+\s*(pm|am)", user_msg, re.I)
                parsed["callback_time"] = {"value": (m.group(0) if m else user_msg), "confidence": 0.85, "isAmbiguous": False}
            if "preferred_start" in parsed and "callback_time" not in parsed:
                parsed["callback_time"] = parsed.pop("preferred_start")
            parsed.pop("preferred_start", None)

    bot_asked_project_type = re.search(
        r"\b(apartment|villa|independent|property type|type of (home|property|house))\b", lower, re.I
    )
    user_intro = re.search(
        r"\b(exploring|interested|looking for|hello!?|hi!?|need (help|support)|support for (my|our) home)\b",
        user_msg.strip(),
        re.I,
    )
    # IMPORTANT: `project_type` means different things across services.
    # - Interiors/Construction: type of home/property ("apartment", "villa", ...)
    # - Solar: installation type ("residential rooftop", "commercial", "ground mount")
    #
    # The intro-detector below is intended to stop the model from guessing a
    # home/property type during a greeting like "Hi I'm looking for help" when
    # the bot did NOT ask for it. For solar_services, this would incorrectly
    # delete the user's correct installation type ("residential rooftop"), causing
    # the engine to re-ask later and frustrate callers.
    if (
        parsed.get("project_type")
        and not bot_asked_project_type
        and user_intro
        and (service_id or "").strip() != "solar_services"
    ):
        parsed.pop("project_type", None)

    asked_about_project_start = "start" in lower and ("project" in lower or "work" in lower)
    if asked_about_project_start and re.search(r"\b(now|right now|immediately|right away|asap)\b", user_msg, re.I):
        # Assistant asked when work/the project should *start* — ASAP belongs in preferred_start.
        # `timeline` is duration (weeks/months); mapping ASAP here used to overwrite "4 months"
        # and drop preferred_start, triggering false QUEST_FIELD_AUTO_SKIPPED on preferred_start.
        parsed["preferred_start"] = {"value": "ASAP", "confidence": 0.9, "isAmbiguous": False}
        tline = parsed.get("timeline")
        if isinstance(tline, dict):
            tv = str(tline.get("value") or "").strip().lower()
            if tv in ("asap", "now", "immediately", "right away"):
                parsed.pop("timeline", None)
        parsed.pop("callback_time", None)
    elif asked_about_project_start and re.search(r"next week|next month|monday|january|february", user_msg, re.I):
        if parsed.get("callback_time") and not parsed.get("preferred_start"):
            parsed["preferred_start"] = parsed.pop("callback_time")
        parsed.pop("callback_time", None)

    if (
        ("timeline" in lower or "complete" in lower or "duration" in lower or "how long" in lower)
        and re.search(r"\d+\s*(days?|weeks?|months?)", user_msg, re.I)
    ):
        duration_match = re.search(r"\d+\s*(days?|weeks?|months?)", user_msg, re.I)
        if duration_match:
            parsed["timeline"] = {"value": duration_match.group(0), "confidence": 0.9, "isAmbiguous": False}
        if parsed.get("preferred_start") and not parsed.get("timeline"):
            parsed["timeline"] = parsed.pop("preferred_start")
            parsed.pop("preferred_start", None)

    return parsed


def get_unusual_value_reason(service_id: str, parameters: dict[str, Any], field: str, value: Any) -> Optional[str]:
    def gv(key: str) -> str:
        v = parameters.get(key)
        if isinstance(v, dict) and "value" in v:
            return str(v.get("value") or "").lower()
        return str(v or "").lower()

    project_type = gv("project_type")
    val_str = str(value or "").strip()

    if field == "floors":
        g_plus = re.search(r"G\+?\s*(\d+)", val_str, re.I)
        if g_plus:
            num = int(g_plus.group(1))
            if num > 5 and ("villa" in project_type or "independent" in project_type):
                return f"G+{num} is unusual for a {project_type or 'villa'} – please confirm they meant {val_str}."
            if num > 20:
                return f"That's a high number of floors ({val_str}) – confirm with the user."

    if field in ("size_sqft", "plot_size_sqft"):
        try:
            n = int(str(value).split()[0])
            if n > 50000 and project_type:
                return f"Very large area ({n} sqft) – confirm with the user."
            if n < 200 and ("villa" in project_type or "independent" in project_type):
                return f"Area {n} sqft is small for a {project_type} – confirm."
        except ValueError:
            pass

    if field == "budget":
        # Budgets are typically discussed in lakhs ("30 lakhs").
        # Avoid flagging reasonable lakh values, and also avoid flagging INR-raw values
        # that convert to a reasonable lakh range.
        val_str_l = str(value or "").strip().lower()
        digits = re.sub(r"[^0-9.]", "", str(value))
        try:
            n = float(digits) if digits else float("nan")
        except Exception:
            n = float("nan")

        if n == n:
            # If user explicitly wrote "lakh", treat n as lakhs.
            if "lakh" in val_str_l:
                if n > 500 or n < 0.1:
                    return f"Budget {value} seems unusual — please confirm."
            else:
                # If it's a large raw number, it might be INR. Convert to lakhs for sanity.
                if n >= 1000:
                    n_lakh = n / 100000.0
                    if n_lakh > 500 or n_lakh < 0.1:
                        return f"Budget {value} seems unusual — please confirm."
                else:
                    # Treat as lakhs when it's in the common range users say aloud.
                    if n > 500 or n < 0.1:
                        return f"Budget {value} seems unusual — please confirm."

    return None


NeedsConfirmation = Optional[dict[str, Any]]


def filter_extractions_needing_confirmation(
    session: Session,
    service_id: str,
    parameters: dict[str, Any],
    extracted: dict[str, Any],
) -> tuple[dict[str, Any], NeedsConfirmation]:
    to_apply: dict[str, Any] = {}
    needs_confirmation: NeedsConfirmation = None

    for key, val in (extracted or {}).items():
        if not val or val.get("value") is None:
            continue
        reason = get_unusual_value_reason(service_id, parameters, key, val.get("value"))
        if reason:
            if not needs_confirmation:
                needs_confirmation = {"field": key, "value": val.get("value"), "reason": reason}
            continue
        # Simplified ambiguity system (LLM-first): do NOT force confirmation purely because the
        # extractor marked a value as ambiguous/low-confidence. Only confirm when the value is
        # geometrically impossible or contradictory (handled by get_unusual_value_reason above).
        to_apply[key] = {"value": val.get("value"), "confidence": float(val.get("confidence") or 0.7)}

    return to_apply, needs_confirmation


def _value_echoed_in_reply(reply: str, value: Any) -> bool:
    """Heuristic: merged reply already references the held value (avoid duplicate confirm tails)."""
    if value is None:
        return False
    s = str(value).strip()
    if len(s) < 2:
        return False
    if s.lower() in reply.lower():
        return True
    digits_reply = re.sub(r"[^0-9]", "", reply)
    d = re.sub(r"[^0-9]", "", s)
    return len(d) >= 3 and d in digits_reply


def _merged_reply_already_confirms(reply: str, needs_confirmation: dict[str, Any]) -> bool:
    r = reply.lower()
    if any(
        p in r
        for p in (
            "confirm",
            "just to confirm",
            "just to check",
            "did you mean",
            "is that right",
            "correct?",
            "right?",
        )
    ):
        return True
    return _value_echoed_in_reply(reply, needs_confirmation.get("value"))


def augment_merged_reply_for_confirmation(reply: str, needs_confirmation: dict[str, Any]) -> str:
    """
    When post-parse rules hold a field for confirmation, the merged model may not know yet.
    Avoid a second full LLM: append a short confirm line only if the reply does not already do so.
    """
    base = (reply or "").strip()
    if not base:
        base = "Got it."
    if _merged_reply_already_confirms(base, needs_confirmation):
        return base
    fld = str(needs_confirmation.get("field") or "").replace("_", " ").strip() or "that detail"
    val = needs_confirmation.get("value")
    reason = str(needs_confirmation.get("reason") or "").strip()
    if reason and len(reason) <= 160:
        tail = f" Quick check — {reason}"
    else:
        tail = f" Perfect — so {val}, correct?"
    combined = f"{base.rstrip()}{tail}"
    if not combined.endswith((".", "?", "!")):
        combined += "?"
    return combined.strip()


def apply_extracted_ts(session: Session, service_id: str, parameters: dict[str, Any], extracted: dict[str, Any]) -> None:
    if not _has_service_params(service_id):
        return
    allowed = set(get_required_ids_for_service(service_id) + get_optional_ids_for_service(service_id))
    allowed.discard("callback_time")
    for key, val in (extracted or {}).items():
        if not val or key not in allowed:
            continue
        conf = float(val.get("confidence", 0) or 0)
        if conf >= EXTRACTION_CONFIDENCE_THRESHOLD_AUTO:
            # Overwrite auto-skip placeholders when we later capture a real value.
            # This prevents recaps like "budget: not specified" after the user actually shared it.
            existing = parameters.get(key)
            if isinstance(existing, dict):
                ex_val = str(existing.get("value") or "").strip().lower()
                if existing.get("_auto_skipped") or existing.get("_user_skipped") or ex_val in {
                    "not specified",
                    "not provided",
                }:
                    pass
            parameters[key] = {
                "value": val.get("value"),
                "confidence": conf,
                "ts": datetime.utcnow().isoformat() + "Z",
            }
    # Painting inference: if project_type already implies both interior+exterior, surface_type is known.
    if service_id == "painting" and "surface_type" not in parameters:
        pt = get_param_value(parameters, "project_type")
        if isinstance(pt, str):
            pt_l = pt.lower()
            if ("interior" in pt_l and "exterior" in pt_l) or "both" in pt_l:
                parameters["surface_type"] = {
                    "value": "interior and exterior walls",
                    "confidence": 0.85,
                    "ts": datetime.utcnow().isoformat() + "Z",
                }
    _set_quest_params(session, parameters)


async def _llm_system_only(session: Session, system_prompt: str, *, max_tokens: int = 512) -> str:
    llm = get_llm_engine()
    return (
        await llm.chat(
            session_id=session.session_id,
            user_message="",
            system_prompt=system_prompt,
            history=[],
            temperature=QUEST_LLM_TEMPERATURE,
            max_tokens=max_tokens,
        )
    ).strip()


async def _llm_yes_no_correction_check(session: Session, user_message: str) -> bool | None:
    """
    Lightweight classifier: returns True if user is correcting a previous answer.
    Returns False if not a correction. Returns None on failure.
    """
    s = (user_message or "").strip()
    if not s:
        return False
    # Only call LLM if message is longer than 3 words.
    words = [w for w in s.split() if w]
    if len(words) <= 3:
        return False
    prompt = (
        "You are a binary classifier.\n"
        "Question: Is the user correcting a previous answer they gave earlier in this conversation?\n"
        "Return ONLY one token: YES or NO.\n\n"
        f"User message: {s}\n"
    )
    try:
        llm = get_llm_engine()
        out = await llm.chat(
            session_id=session.session_id,
            user_message="",
            system_prompt=prompt,
            history=[],
            temperature=0.0,
            max_tokens=8,
        )
    except Exception:
        return None
    ans = (out or "").strip().upper()
    if ans.startswith("YES"):
        return True
    if ans.startswith("NO"):
        return False
    return None


async def _llm_system_only_stream(session: Session, system_prompt: str, *, max_tokens: int = 512) -> AsyncIterator[str]:
    with quest_llm_phase("assistant_reply_stream"):
        llm = get_llm_engine()
        stream = await llm.chat_stream(
            session_id=session.session_id,
            user_message="",
            system_prompt=system_prompt,
            history=[],
            temperature=QUEST_LLM_TEMPERATURE,
            max_tokens=max_tokens,
        )
        async for piece in stream:
            if piece:
                yield piece


def get_mood_guidance(mood: str) -> str:
    guidance = {
        "positive": "User is engaged and happy. Match their energy, be enthusiastic!",
        "neutral": "Keep it friendly and professional. Move the conversation forward smoothly.",
        "confused": "User seems confused. Simplify your question, maybe give examples or options.",
        "frustrated": "User is getting frustrated. Acknowledge it briefly, be concise, skip non-essential questions.",
        "rushed": "User wants to finish quickly. Be very brief, focus only on must-have info.",
        "uncertain": "User is unsure. Offer gentle suggestions or let them know it's okay to decide later.",
    }
    return guidance.get(mood, guidance["neutral"])


def humanize_response(text: str, mood: str, turn_count: int, channel: str = "whatsapp") -> str:
    global _last_used_starter
    robotic = [
        re.compile(r"^(Understood|Excellent|Wonderful|Great|Perfect)[.!,]?\s*", re.I),
        re.compile(r"Could you (please )?(share|tell|provide)", re.I),
        re.compile(r"To help (me |us )?(understand|better)", re.I),
        re.compile(r"Thank you for sharing", re.I),
        re.compile(r"I appreciate you sharing", re.I),
        re.compile(r"^Achcha,?\s*", re.I),
        re.compile(r"^Ah,?\s+", re.I),
        re.compile(r"\bleverage\b", re.I),
        re.compile(r"\bstreamline(d|s)?\b", re.I),
        re.compile(r"\boptimize(d|s)?\b", re.I),
        re.compile(r"\b(sir|ma'am|bhai|didi|boss|dear)\b[,!.\s]*", re.I),
    ]
    result = text
    for phrase in robotic:
        result = phrase.sub("", result)

    hyphen_fixes = [
        (re.compile(r"\bwell-designed\b", re.I), "well designed"),
        (re.compile(r"\bwell-planned\b", re.I), "well planned"),
        (re.compile(r"\bhigh-quality\b", re.I), "great quality"),
        (re.compile(r"\bstate-of-the-art\b", re.I), "modern"),
        (re.compile(r"\bbest-in-class\b", re.I), "really good"),
        (re.compile(r"\buser-friendly\b", re.I), "easy to use"),
        (re.compile(r"\bready-to-use\b", re.I), "ready to use"),
        (re.compile(r"\bend-to-end\b", re.I), "full"),
        (re.compile(r"\bcutting-edge\b", re.I), "modern"),
        (re.compile(r"\bfirst-class\b", re.I), "top"),
    ]
    for rx, rep in hyphen_fixes:
        result = rx.sub(rep, result)

    mood_starters = {
        "positive": ["Lovely!", "Nice!", "Love it!", "Perfect!", "Great!", "Awesome!"],
        "neutral": ["Got it!", "Okay!", "Right!", "Alright!", "Sure!", "Noted!", "Cool!", "Sounds good!"],
        "confused": ["Let me help.", "No worries!", "Let me explain.", "Happy to clarify!"],
        "frustrated": ["I hear you.", "Let's wrap up.", "Almost there!", "Just a couple more."],
        "rushed": ["Quick one -", "Just this -", "Last thing -", "One more -"],
        "uncertain": ["No pressure!", "That's fine!", "We can decide later.", "Totally okay!"],
    }
    repetitive = re.compile(r"^(That's|That sounds|I |So,|Achcha|Ah,)", re.I)
    if turn_count > 2 and repetitive.search(result):
        starters = mood_starters.get(mood, mood_starters["neutral"])
        available = [s for s in starters if s.lower() != _last_used_starter.lower()]
        random_starter = random.choice(available) if available else starters[0]
        _last_used_starter = random_starter
        result = repetitive.sub("", result).strip()
        result = f"{random_starter} {result}"

    result = re.sub(r"Achcha,?\s+Achcha", "Achcha", result, flags=re.I)
    result = result.strip()
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\s+([.,!?])", r"\1", result)

    # Hard truncation is primarily for voice (TTS + ASR turn-taking). For WhatsApp,
    # truncating can chop off critical numerics like budgets/capacity mid-thought.
    if (channel or "").strip().lower() == "voice":
        if len(result) > 200:
            parts = re.split(r"[.!?]", result)
            result = ". ".join(parts[:2]).strip()
            if result and not re.search(r"[.!?]$", result):
                result += "."

    return result


def build_character_view(session: Session, service_id: str) -> dict[str, Any]:
    settings = get_settings()
    pk = session.persona_key or settings.consultant_persona
    name = get_display_name_by_service_code(session.service_code or service_id, "Consultant")
    return {
        "name": name,
        "tone": "",
        "persona_summary": get_base_identity_by_persona_key(pk, default_persona=settings.consultant_persona).strip()[:2000],
        "max_turns_before_direct_ask": MAX_TURNS_BEFORE_DIRECT_ASK,
    }


def _build_extraction_prompt_text(
    session: Session,
    message: str,
    service_id: str,
    parameters: dict[str, Any],
) -> tuple[str, bool, set[str]]:
    pending = collect_pending_datapoints(service_id, parameters)
    allowed_ids = {p["id"] for p in pending}
    is_ambiguous = detect_ambiguity(message)
    datapoints_block = "\n".join(f"- {p['id']}: {p.get('hint') or ''}" for p in pending)
    last_bot = get_last_assistant_message(session) or "None"
    meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    last_ask_raw = meta.get("__quest:lastAsk")
    asked_field_id = str(last_ask_raw.get("askedParam") or "").strip() if isinstance(last_ask_raw, dict) else ""
    # Determine whether the last bot question was yes/no, multi-choice, or open-ended.
    prev = (last_bot or "").strip()
    question_type = "OPEN"
    if prev.endswith("?") and re.search(r"\b(yes|no)\b", prev.lower()):
        question_type = "YES_NO"
    elif " or " in prev.lower():
        question_type = "MULTI_CHOICE"
    prompt = (
        EXTRACTION_PROMPT_TEMPLATE.replace("<MESSAGE>", message)
        .replace("<PREVIOUS_MSG>", last_bot[:300])
        .replace("<DATAPOINTS>", datapoints_block)
        .replace("<QUESTION_TYPE>", question_type)
        .replace("<ASKED_FIELD_ID>", asked_field_id[:64])
    )
    return prompt, is_ambiguous, allowed_ids


async def extract_datapoints_from_message(
    session: Session,
    message: str,
    service_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    prompt, is_ambiguous, allowed_ids = _build_extraction_prompt_text(session, message, service_id, parameters)
    last_bot = get_last_assistant_message(session) or "None"
    # Voice channel uses a tighter output cap to reduce p95 latency.
    is_voice = (getattr(session, "channel", None) or "").strip().lower() == "voice"
    extraction_max_tokens = QUEST_EXTRACTION_MAX_OUTPUT_VOICE if is_voice else QUEST_EXTRACTION_MAX_OUTPUT
    with quest_llm_phase("extraction"):
        raw = await _llm_system_only(session, prompt, max_tokens=extraction_max_tokens)
    await log_event('QUEST_EXTRACTION_RAW', session_id=session.session_id, data={'raw': raw[:500], 'message': message[:200], 'service_id': service_id})
    raw = clean_json_result(raw)
    if not raw:
        parsed = fallback_regex_extraction(message, is_ambiguous, allowed_ids)
        parsed = validate_extraction_context(parsed, last_bot, message, service_id)
        return parsed
    try:
        parsed: dict[str, Any] = json.loads(raw)
    except Exception:
        parsed = fallback_regex_extraction(message, is_ambiguous, allowed_ids)
    else:
        parsed = normalize_extraction_keys_ts(parsed, allowed_ids)
        if is_ambiguous:
            for k in list(parsed.keys()):
                v = parsed[k]
                if v and float(v.get("confidence") or 0) > 0:
                    v["isAmbiguous"] = True
                    v["confidence"] = min(float(v.get("confidence") or 0), 0.6)
                    parsed[k] = v
        if not parsed:
            parsed = fallback_regex_extraction(message, is_ambiguous, allowed_ids)

    parsed = validate_extraction_context(parsed, last_bot, message, service_id)
    return parsed


async def extract_datapoints_from_message_allow_all(
    session: Session,
    message: str,
    service_id: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Review-mode extraction: allow editing ANY service field, even when coverage is satisfied
    (pending datapoints is empty). This keeps "change X to Y" working during confirmation.
    """
    prompt, is_ambiguous, _pending_allowed_ids = _build_extraction_prompt_text(session, message, service_id, parameters)
    allowed_ids = set(get_required_ids_for_service(service_id) + get_optional_ids_for_service(service_id))
    allowed_ids.discard("callback_time")
    last_bot = get_last_assistant_message(session) or "None"
    is_voice = (getattr(session, "channel", None) or "").strip().lower() == "voice"
    extraction_max_tokens = QUEST_EXTRACTION_MAX_OUTPUT_VOICE if is_voice else QUEST_EXTRACTION_MAX_OUTPUT
    with quest_llm_phase("extraction_review"):
        raw = await _llm_system_only(session, prompt, max_tokens=extraction_max_tokens)
    await log_event(
        "QUEST_EXTRACTION_RAW",
        session_id=session.session_id,
        data={"raw": raw[:500], "message": message[:200], "service_id": service_id, "review_allow_all": True},
    )
    raw = clean_json_result(raw)
    if not raw:
        parsed = fallback_regex_extraction(message, is_ambiguous, allowed_ids)
        parsed = validate_extraction_context(parsed, last_bot, message, service_id)
        return parsed
    try:
        parsed: dict[str, Any] = json.loads(raw)
    except Exception:
        parsed = fallback_regex_extraction(message, is_ambiguous, allowed_ids)
    else:
        parsed = normalize_extraction_keys_ts(parsed, allowed_ids)
        if is_ambiguous:
            for k in list(parsed.keys()):
                v = parsed[k]
                if v and float(v.get("confidence") or 0) > 0:
                    v["isAmbiguous"] = True
                    v["confidence"] = min(float(v.get("confidence") or 0), 0.6)
                    parsed[k] = v
        if not parsed:
            parsed = fallback_regex_extraction(message, is_ambiguous, allowed_ids)
    parsed = validate_extraction_context(parsed, last_bot, message, service_id)
    return parsed


def _callback_time_for_closing(raw: str | None) -> str:
    """Spoken-friendly phrase to slot into the `{callback_time}` placeholder in
    `closing_voice` templates.

    Priorities:
    1. When the caller gave a concrete time (`"tomorrow at 3 pm"`, `"monday 10am"`,
       `"today evening"`) → use it verbatim so the closing mirrors what they said.
    2. Urgency words (`"now"`, `"asap"`) → `"right away"`.
    3. Vague / missing / `"soon"` / `"later"` → fall back to `"within 24 hours"`
       so the line still reads naturally (this was the pre-fix default).
    """
    s = (raw or "").strip()
    if not s:
        return "within 24 hours"
    low = s.lower()
    if low in {"now", "right now", "asap", "immediately"}:
        return "right away"
    if low in {"soon", "later"}:
        return "within 24 hours"
    return s


def _closing_append_signoff_warm_day(text: str) -> str:
    """Append a short warm sign-off when the closing does not already include one."""
    t = (text or "").strip()
    if not t:
        return t
    low = t.lower()
    if "great day" in low or "good day" in low or "take care" in low:
        return t
    return f"{t} Have a great day!"


def _closing_add_created_checkmark(text: str) -> str:
    """
    Add a single ✅ to the "project created" closing line for a professional WhatsApp-style status cue.
    Only applies when the message clearly indicates creation already happened.
    """
    t = (text or "").strip()
    if not t or "✅" in t:
        return t
    low = t.lower()
    if "created" not in low:
        return t
    # Prefer placing right after "Perfect" when present.
    t2 = re.sub(r"^(perfect)(\s*[—-]?\s*)", r"\1 ✅\2", t, flags=re.I)
    return t2 if t2 != t else f"✅ {t}"


async def generate_closing_message(session: Session, character: dict[str, Any], service_id: str) -> str:
    params = _get_quest_params(session)
    contact_pref = get_param_value(params, "contact_pref") or "phone"
    callback_time = get_param_value(params, "callback_time") or "soon"
    project_type = get_param_value(params, "project_type") or get_param_value(params, "rooms") or "project"
    style = get_param_value(params, "style") or ""
    user_phone = session.phone_number or "this number"

    # Prefer deterministic, service-specific closing when available (voice + WhatsApp).
    # callback_time is no longer collected; service_registry closings should not depend on it.
    if (session.channel or "").strip().lower() in ("voice", "whatsapp"):
        try:
            from backend.intelligence.service_registry import QUEST_SERVICE_REGISTRY

            manifest = QUEST_SERVICE_REGISTRY.get(service_id) or {}
            closing_voice = manifest.get("closing_voice")
            if isinstance(closing_voice, str) and closing_voice.strip():
                cb_phrase = _callback_time_for_closing(callback_time)
                base = closing_voice.replace("{callback_time}", cb_phrase).strip()
                base = _closing_add_created_checkmark(base)
                return _closing_append_signoff_warm_day(base)
        except Exception:
            # Fall back to existing LLM-based closing on any failure.
            pass

    def _callback_time_phrase(raw: str) -> str:
        s = (raw or "").strip().lower()
        if s in {"now", "right now", "asap", "immediately"}:
            return "right away"
        if s in {"today", "evening", "today evening", "tonight"}:
            return "today evening"
        if "tomorrow" in s:
            return "tomorrow"
        if s in {"soon", "later"}:
            return "soon"
        return raw or "soon"

    def _deterministic_closing() -> str:
        proj = str(project_type or "project").strip()
        base = (
            f"Perfect ✅ — I’ve created your {proj} project in our system. "
            "The right PropFlow vendor will contact you shortly."
        )[:220].strip()
        return base

    prompt = (
        CLOSING_PROMPT_TEMPLATE.replace("<CHARACTER_NAME>", character["name"])
        .replace("<PROJECT_TYPE>", str(project_type))
        .replace("<STYLE>", str(style) or "their style")
        .replace("<CONTACT_PREF>", str(contact_pref))
        .replace("<CALLBACK_TIME>", str(callback_time))
        .replace("<USER_PHONE>", str(user_phone))
    )
    max_out = (
        QUEST_GEMINI_MAX_OUTPUT_VOICE
        if (session.channel or "").strip().lower() == "voice"
        else QUEST_GEMINI_MAX_OUTPUT_DEFAULT
    )
    with quest_llm_phase("closing"):
        closing_text = await _llm_system_only(session, prompt, max_tokens=max_out)
    final_text = re.sub(r"thank you for choosing propflow", "", closing_text, flags=re.I)
    final_text = re.sub(r"\n+", " ", final_text).strip()
    if len(final_text) > 220:
        sentences = re.split(r"[.!]", final_text)
        final_text = ". ".join(sentences[:3]).strip()
        if final_text and not re.search(r"[.!]$", final_text):
            final_text += "!"
    # Ensure the closing stays aligned to the expected vendor phrasing.
    if "vendor" not in final_text.lower():
        return _closing_append_signoff_warm_day(_deterministic_closing())
    final_text = _closing_add_created_checkmark(final_text)
    return _closing_append_signoff_warm_day(final_text)


def _normalize_voice_reply(text: str) -> str:
    # Vapi/ASR commonly adds trailing punctuation like "Yes." / "Okay."
    return (text or "").strip().rstrip(".,!?;:").strip().lower()


def _is_meaningless_midturn_utterance(text: str) -> bool:
    """
    Voice ASR often yields filler mid-conversation ("hello", "um", etc.).
    If extraction applies nothing, re-ask the last question deterministically.
    """
    s = _normalize_voice_reply(text)
    if not s:
        return True
    s = re.sub(r"\s+", " ", s).strip()
    return s in {
        "hello",
        "hi",
        "hey",
        "hii",
        "um",
        "umm",
        "uh",
        "uhh",
        "hmm",
        "hm",
        "ugh",
        "sorry",
        "what",
        "just a second",
        "wait",
        "one moment",
        "hold on",
        "okay wait",
        "give me a second",
        "one sec",
        "ek second",
        "ruko",
        "thoda ruko",
        "bas ek second",
    }


def _assistant_main_prompt_only_sync(
    session: Session,
    character: dict[str, Any],
    service_id: str,
    user_message: str,
    channel: str,
) -> str | None:
    """
    Build the main-branch ASSISTANT system prompt (no opening / closing short-circuits).
    Returns None when this turn must use the classic extract-then-reply pipeline.
    """
    _ = channel
    params = _get_quest_params(session)
    pending = collect_pending_datapoints(service_id, params)
    collected_block = format_collected_params(params)

    meta_state = get_conversation_state(session)
    state_mood = str(meta_state.get("mood") or "neutral")
    last_user_msg = user_message or get_last_user_message(session) or ""
    current_mood = detect_mood(last_user_msg, state_mood)
    is_ambiguous = detect_ambiguity(last_user_msg)
    wants_clarification = is_asking_for_clarification(last_user_msg)

    recent_user = [m for m in session.conversation_history if m.role == MessageRole.USER][-3:]
    multiple_acks = len(recent_user) >= 2 and all(
        re.match(
            r"^(sure|ok|okay|yes|yeah|yep|done|great|sounds good|perfect|cool|thanks|thank you|nice|awesome|have a good day)$",
            _normalize_voice_reply(m.content or ""),
            re.I,
        )
        for m in recent_user
    )

    mood_history = list(meta_state.get("moodHistory") or [])
    mood_history.append(current_mood)

    last_bot_msg = get_last_assistant_message(session)
    # callback_time is not collected anymore (voice/WhatsApp policy).
    has_callback_time = False
    call_pat = re.compile(
        r"connect|call you|looking forward|we'll connect|schedule|talk to you|give you a call|call right away|"
        r"connecting with you|connect very soon|give you a call then|call you then|call then",
        re.I,
    )
    _coverage_done = is_coverage_satisfied(params, service_id)
    bot_just_confirmed_call = bool(_coverage_done and last_bot_msg and call_pat.search(last_bot_msg))
    user_short_ack = bool(
        re.match(
            r"^(sure|ok|okay|yes|yeah|yep|done|great|sounds good|perfect|cool|thanks|thank you|nice|awesome)$",
            _normalize_voice_reply(last_user_msg),
            re.I,
        )
    )
    recent_bot = [m for m in session.conversation_history if m.role == MessageRole.ASSISTANT][-2:]
    recent_bot_text = " ".join(m.content or "" for m in recent_bot)
    bot_has_confirmed_call = bool(_coverage_done and call_pat.search(recent_bot_text))

    if is_coverage_satisfied(params, service_id):
        return None
    if (bot_just_confirmed_call or bot_has_confirmed_call) and user_short_ack:
        return None
    if (bot_just_confirmed_call or bot_has_confirmed_call) and multiple_acks:
        return None

    required_ids = get_required_fields_for_service(service_id)
    effective_pending = pending
    if current_mood in ("frustrated", "rushed"):
        effective_pending = [p for p in pending if p["id"] in required_ids]

    persona_summary = character.get("persona_summary") or ""
    tone = character.get("tone") or ""
    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    service_role = f"{service_name} consultant"

    prior_assistant_msgs = any(m.role == MessageRole.ASSISTANT for m in session.conversation_history)
    is_opening = (not str(last_user_msg or "").strip()) and (not prior_assistant_msgs) and bool(effective_pending)
    if is_opening:
        return None

    transcript_block = build_transcript(session)
    mood_guidance = get_mood_guidance(current_mood)

    ambiguity_section = ""
    if wants_clarification:
        ambiguity_section = f"""
IMPORTANT: User said "{last_user_msg}" - they want ALL OPTIONS EXPLAINED.
Last thing you asked about: "{last_bot_msg[:100] if last_bot_msg else ''}"
Your response MUST:
1. Explain ALL available options for what YOU JUST ASKED — not just one or two
2. Keep each explanation to ONE short sentence maximum
3. DO NOT ask about a different topic
4. DO NOT move to the next datapoint
5. End with ONE question asking which option they prefer
6. Maximum 4 sentences total including the closing question"""
    elif is_ambiguous:
        ambiguity_section = f"""
CRITICAL - AMBIGUOUS OR VAGUE ANSWER: User said "{last_user_msg}". You MUST re-ask or confirm what they meant for the topic you just asked about. Do NOT move to the next parameter. Say e.g. "Perfect — so you meant X, correct?" or give 2–3 clear options. Wait for their confirmation before moving on."""

    call_confirmed_section = ""
    if (bot_just_confirmed_call or bot_has_confirmed_call) and user_short_ack:
        call_confirmed_section = """
CRITICAL - CALL ALREADY CONFIRMED: You already said you'll connect/call and the user acknowledged ("sure", "ok", etc.). The conversation is COMPLETE. Do NOT ask any new questions. Do NOT continue the conversation. Reply with ONLY a brief sign-off, e.g. "Great, see you then!" or "Talk to you tomorrow!" – one short sentence max. Then STOP."""
    elif bot_just_confirmed_call or bot_has_confirmed_call:
        call_confirmed_section = """
IMPORTANT: You just confirmed you'll call/connect with the user. Wait for their acknowledgment. If they say "ok", "sure", "yes", etc., the conversation will be complete."""

    confirm_section = ""
    max_turns = character.get("max_turns_before_direct_ask") or MAX_TURNS_BEFORE_DIRECT_ASK
    prompt = (
        ASSISTANT_PROMPT_TEMPLATE.replace("<CHARACTER_NAME>", character["name"])
        .replace("<SERVICE_ROLE>", service_role)
        .replace("<SERVICE_NAME>", service_name)
        .replace("<PERSONA_SUMMARY>", persona_summary[:QUEST_PERSONA_PROMPT_CHARS])
        .replace("<TONE>", tone or "warm, concise")
        .replace("<MOOD>", str(current_mood))
        .replace("<MOOD_GUIDANCE>", mood_guidance)
        .replace("<COLLECTED>", collected_block)
        .replace("<TRANSCRIPT>", transcript_block or "No prior context")
        .replace("<PENDING>", format_pending(effective_pending) if effective_pending else "None - all data collected!")
        .replace("<AMBIGUITY_SECTION>", ambiguity_section)
        .replace("<CONFIRM_SECTION>", confirm_section)
        .replace("<CALL_CONFIRMED_SECTION>", call_confirmed_section)
        .replace("<MAX_TURNS>", str(max_turns))
    )
    return prompt


_MERGED_JSON_FOOTER = """
--- FINAL INSTRUCTION ---
Return ONLY valid JSON (no markdown fences). Exact keys:
- "extracted": object mapping datapoint ids to objects with "value", "confidence" (0-1), and optionally "isAmbiguous" (boolean), following PART 1 rules. Use {} if nothing was extracted.
- "assistant_reply": string, your next conversational reply to the user (follow PART 2). Assume keys in "extracted" will be applied to their profile before the user sees your reply.
  If you captured an unusual budget, very large/small size, or other edge-case number, briefly confirm it in assistant_reply before asking the next question.
- "is_complete": boolean, true only if this turn is a final sign-off and the questionnaire is complete.
"""


async def _try_merged_extract_and_reply(
    session: Session,
    character: dict[str, Any],
    service_id: str,
    user_message: str,
    channel: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """
    One LLM call: extraction JSON + assistant reply JSON.
    Returns dict with keys: extracted (raw dict), raw_reply (str), model_is_complete (bool), or None to use classic path.
    """
    if not QUEST_MERGED_EXTRACT_REPLY or not (user_message or "").strip():
        return None
    assistant_prompt = _assistant_main_prompt_only_sync(session, character, service_id, user_message, channel)
    if not assistant_prompt:
        return None
    ext_prompt, is_ambiguous, allowed_ids = _build_extraction_prompt_text(session, user_message, service_id, params)
    first_turn_hook = ""
    if not any(m.role == MessageRole.ASSISTANT for m in session.conversation_history):
        first_turn_hook = (
            "FIRST USER MESSAGE (no assistant line in transcript yet): assistant_reply must briefly greet using "
            "your name and role from PART 2, then ask your next question. Keep it concise.\n\n"
        )
    merged_system = (
        first_turn_hook
        + "You perform structured extraction and the next assistant reply in a single pass.\n"
        + ext_prompt
        + "\n\nPART 2 - ASSISTANT (same rules as below; your spoken reply goes in JSON assistant_reply):\n"
        + assistant_prompt
        + _MERGED_JSON_FOOTER
    )
    with quest_llm_phase("merged_extract_reply"):
        raw = (await _llm_system_only(session, merged_system, max_tokens=QUEST_MERGED_MAX_OUTPUT)).strip()
    raw = clean_json_result(raw)
    try:
        payload: dict[str, Any] = json.loads(raw)
    except Exception:
        return None
    extracted_raw = payload.get("extracted")
    if not isinstance(extracted_raw, dict):
        return None
    assistant_reply = payload.get("assistant_reply")
    if not isinstance(assistant_reply, str) or not assistant_reply.strip():
        return None
    model_is_complete = bool(payload.get("is_complete"))

    parsed = normalize_extraction_keys_ts(extracted_raw, allowed_ids)
    if is_ambiguous:
        for k in list(parsed.keys()):
            v = parsed[k]
            if v and float(v.get("confidence") or 0) > 0:
                v["isAmbiguous"] = True
                v["confidence"] = min(float(v.get("confidence") or 0), 0.6)
                parsed[k] = v
    if not parsed:
        parsed = fallback_regex_extraction(user_message, is_ambiguous, allowed_ids)
    last_bot = get_last_assistant_message(session) or "None"
    parsed = validate_extraction_context(parsed, last_bot, user_message, service_id)

    return {
        "extracted": parsed,
        "raw_reply": assistant_reply.strip(),
        "model_is_complete": model_is_complete,
    }


def _parse_review_phase_intent(raw: str) -> str:
    ir = (raw or "").strip().upper()
    m = re.search(r"\b(YES|NO|CHANGE|SUMMARY|INFO|UNCLEAR)\b", ir)
    return m.group(1) if m else "UNCLEAR"


async def _classify_review_phase_intent(session: Session, last_user_msg: str) -> str:
    """Single-word intent for project-creation review (no accidental create on parse failure)."""
    prompt = (
        "The user was asked to confirm creating their PropFlow project (a vendor will follow up).\n"
        f"User message: {last_user_msg!r}\n\n"
        "Return EXACTLY ONE WORD in ALL CAPS from:\n"
        "YES NO CHANGE SUMMARY INFO UNCLEAR\n\n"
        "YES — they approve creation now (go ahead, create it, confirm, yes, lock it in, proceed, we're good).\n"
        "NO — they are only pausing (not yet, wait, hold on) without asking recap, edits, or an explanatory question.\n"
        "CHANGE — they want to update captured data (budget, timeline, size, location, etc.).\n"
        "SUMMARY — they want a recap or list of what they shared (summarize, what did I say, list everything).\n"
        "INFO — an in-topic question (what does X mean, difference between A and B, explain hybrid) — not direct approval.\n"
        "UNCLEAR — you cannot classify confidently.\n\n"
        "Return ONLY that word.\n"
    )
    try:
        with quest_llm_phase("project_confirm_intent_v2"):
            raw_i = await get_llm_engine().chat(
                session_id=f"{session.session_id}:review_intent",
                user_message=prompt,
                system_prompt="Return ONLY one word: YES, NO, CHANGE, SUMMARY, INFO, or UNCLEAR.",
                history=[],
                temperature=0.0,
                max_tokens=12,
            )
    except Exception:
        raw_i = ""
    parsed = _parse_review_phase_intent(raw_i)
    if parsed != "UNCLEAR":
        return parsed
    # Deterministic fallback: if the provider returns blank/garbage, still handle obvious intents.
    s = (last_user_msg or "").strip().lower()
    if not s:
        return "UNCLEAR"
    if re.search(r"\b(change|update|edit|modify|instead|actually)\b", s):
        return "CHANGE"
    if re.search(r"\b(summary|summarise|summarize|recap|list)\b", s):
        return "SUMMARY"
    if re.search(r"\b(wait|hold|not now|later|stop)\b", s):
        return "NO"
    if re.search(r"\b(create|confirm|go ahead|proceed|yes|yep|yeah|do it|ok create|okay create)\b", s):
        return "YES"
    if "?" in s:
        return "INFO"
    return "UNCLEAR"


async def _llm_natural_create_confirm_question(session: Session, character: dict[str, Any], channel: str) -> str:
    ch = (channel or "").strip().lower() or "whatsapp"
    confirm_prompt = (
        f"You are a PropFlow consultant on {ch}.\n"
        "Write ONE short, natural yes/no question so the user can confirm you should create their project "
        "so the right PropFlow vendor can reach out.\n"
        "Requirements:\n"
        "- Exactly one sentence\n"
        "- Must end with ?\n"
        "- Warm and human, like a specialist — not robotic\n"
        "- Do not mention callback time or raw phone numbers\n"
        "Return ONLY the sentence.\n"
    )
    try:
        with quest_llm_phase("confirmation"):
            confirm_q = await _llm_system_only(session, confirm_prompt, max_tokens=90)
        confirm_q = re.sub(r"\s+", " ", (confirm_q or "").strip())
    except Exception:
        confirm_q = ""
    if not confirm_q or "?" not in confirm_q:
        confirm_q = "Shall I create this project in our system so the right PropFlow vendor can reach out?"
    return confirm_q


async def _llm_review_recap_and_confirm_message(
    session: Session,
    *,
    channel: str,
    service_id: str,
    params: dict[str, Any],
) -> str:
    """
    One WhatsApp-friendly message for the REVIEW gate:
    - short recap of captured info so far
    - exactly ONE yes/no confirmation question to create the project
    """
    ch = (channel or "").strip().lower() or "whatsapp"
    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    recap = _format_whatsapp_review_recap(service_id, params)
    captured = recap or format_collected_params(params)
    prompt = (
        f"You are a PropFlow {service_name} specialist chatting on {ch}.\n"
        "We have captured the user's project details and need explicit confirmation before creating their project.\n\n"
        "Write ONE WhatsApp message that:\n"
        "1) Briefly recaps the captured details (use short lines or bullets; keep under 7 lines total)\n"
        "2) Asks EXACTLY ONE yes/no question to confirm we should create the project so the right PropFlow vendor can reach out\n\n"
        "Hard rules:\n"
        "- EXACTLY ONE question in the entire message\n"
        "- Must end with '?'\n"
        "- Do NOT say the project is already created\n"
        "- Do NOT mention callback time\n\n"
        f"CAPTURED:\n{captured}\n"
        "Return ONLY the message text.\n"
    )
    try:
        with quest_llm_phase("confirmation_recap"):
            out = await _llm_system_only(session, prompt, max_tokens=220)
        text = re.sub(r"\s+\n", "\n", (out or "").strip())
        text = re.sub(r"\n{3,}", "\n\n", text)
    except Exception:
        text = ""
    if not text or "?" not in text:
        confirm_q = "Shall I create this project in our system so the right PropFlow vendor can reach out?"
        if captured:
            text = f"Here’s what I’ve captured so far:\n{captured}\n\n{confirm_q}"
        else:
            text = confirm_q
    # Enforce "one question" invariant defensively: if the model wrote multiple questions,
    # fall back to a deterministic 1-question message.
    if len(re.findall(r"\?", text)) != 1:
        confirm_q = "Shall I create this project in our system so the right PropFlow vendor can reach out?"
        if captured:
            text = f"Here’s what I’ve captured so far:\n{captured}\n\n{confirm_q}"
        else:
            text = confirm_q
    return text


async def _process_awaiting_project_confirm(
    session: Session,
    character: dict[str, Any],
    service_id: str,
    params: dict[str, Any],
    last_user_msg: str,
    meta: dict[str, Any],
    *,
    current_mood: str,
    mood_history: list,
    meta_state: dict[str, Any],
) -> dict[str, Any]:
    """Handle a user turn while `__quest:awaiting_project_confirm` is true."""
    intent = await _classify_review_phase_intent(session, last_user_msg)

    def _save_mood() -> None:
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": mood_history[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )

    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    ch = session.channel or ""

    if intent == "YES":
        meta["__quest:awaiting_project_confirm"] = False
        meta["__quest:confirm_ask_count"] = 0
        session.extracted_fields = meta
        wants_recap = bool(
            re.search(
                r"\b(summar|recap|list what|what did i|run through|everything i|walk me through)\b",
                last_user_msg.lower(),
            )
        )
        closing = await generate_closing_message(session, character, service_id)
        if wants_recap:
            summary_text = ""
            try:
                summary_text = (
                    await get_llm_engine().chat(
                        session_id=f"{session.session_id}:confirm_summary_text_yes",
                        user_message="",
                        system_prompt=(
                            "Write a concise 2–3 sentence summary of the captured project info.\n"
                            "No questions. No site visit promises. No callback time.\n"
                            f"Captured fields:\n{format_collected_params(params)}\n"
                        ),
                        history=[],
                        temperature=0.2,
                        max_tokens=120,
                    )
                ).strip()
            except Exception:
                summary_text = ""
            if summary_text:
                closing = f"{summary_text} {closing}".strip()
        _save_mood()
        return {"reply": closing, "isComplete": True, "mood": current_mood}

    if intent == "NO":
        meta["__quest:awaiting_project_confirm"] = True
        session.extracted_fields = meta
        reply = (
            "Sure — take your time. I can give you a quick recap, tweak any detail, or answer a question — "
            "just tell me what you'd like next."
        )
        _save_mood()
        return {"reply": reply, "isComplete": False, "mood": current_mood}

    if intent == "CHANGE":
        try:
            extracted_changes = await extract_datapoints_from_message_allow_all(session, last_user_msg, service_id, params)
        except Exception:
            extracted_changes = {}
        to_apply = extracted_changes or {}
        if to_apply:
            try:
                to_apply, _needs = filter_extractions_needing_confirmation(session, service_id, params, to_apply)
            except Exception:
                pass
            apply_extracted_ts(session, service_id, params, to_apply)
            meta["__quest:parameters"] = session.extracted_fields.get("__quest:parameters", _get_quest_params(session))
        session.extracted_fields = meta
        confirm_q = await _llm_natural_create_confirm_question(session, character, ch)
        if to_apply:
            applied_note = "Updated that for you. "
        else:
            applied_note = (
                "I didn't catch exactly what to change — try e.g. \"change my budget to 6 lakhs\". "
            )
        reply = f"{applied_note}{confirm_q}".strip()
        meta["__quest:awaiting_project_confirm"] = True
        session.extracted_fields = meta
        _save_mood()
        return {"reply": reply, "isComplete": False, "mood": current_mood}

    if intent == "SUMMARY":
        summary_piece = ""
        try:
            summary_piece = (
                await get_llm_engine().chat(
                    session_id=f"{session.session_id}:confirm_summary_only",
                    user_message="",
                    system_prompt=(
                        "Write a clear, friendly recap of what we captured for this enquiry.\n"
                        "Use short lines or bullets; keep under 6 lines. No questions in the recap body. "
                        "No callback time.\n"
                        f"Captured fields:\n{format_collected_params(params)}\n"
                    ),
                    history=[],
                    temperature=0.2,
                    max_tokens=220,
                )
            ).strip()
        except Exception:
            summary_piece = ""
        confirm_q = await _llm_natural_create_confirm_question(session, character, ch)
        reply = f"{summary_piece}\n\n{confirm_q}".strip() if summary_piece else confirm_q
        meta["__quest:awaiting_project_confirm"] = True
        session.extracted_fields = meta
        _save_mood()
        return {"reply": reply, "isComplete": False, "mood": current_mood}

    if intent == "INFO":
        info_ans = ""
        try:
            info_ans = (
                await get_llm_engine().chat(
                    session_id=f"{session.session_id}:review_info_answer",
                    user_message=last_user_msg,
                    system_prompt=(
                        f"You are a PropFlow {service_name} consultant. The client is reviewing their enquiry "
                        "before we create the project in our system.\n"
                        "Answer their question briefly (max 4 short sentences).\n"
                        "Use CAPTURED only for facts about THEIR project; do not invent their numbers.\n"
                        "If it is general product knowledge, explain briefly in plain language.\n"
                        "Do NOT say the project is already created.\n\n"
                        f"CAPTURED:\n{format_collected_params(params)}\n"
                    ),
                    history=[],
                    temperature=0.25,
                    max_tokens=240,
                )
            ).strip()
        except Exception:
            info_ans = ""
        if not info_ans:
            info_ans = (
                f"Happy to help — what would you like to know about your {service_name} enquiry? "
                "I can explain terms or walk through what we captured."
            )
        confirm_q = await _llm_natural_create_confirm_question(session, character, ch)
        reply = f"{info_ans}\n\n{confirm_q}".strip()
        meta["__quest:awaiting_project_confirm"] = True
        session.extracted_fields = meta
        _save_mood()
        return {"reply": reply, "isComplete": False, "mood": current_mood}

    meta["__quest:awaiting_project_confirm"] = True
    session.extracted_fields = meta
    clarify = (
        "I didn't quite catch that — do you want me to create your project now so a PropFlow vendor can follow up, "
        "or would you like a quick recap or a change first?"
    )
    _save_mood()
    return {"reply": clarify, "isComplete": False, "mood": current_mood}


async def generate_assistant_reply(
    session: Session,
    character: dict[str, Any],
    service_id: str,
    *,
    last_user_message: str,
    channel: str,
    needs_confirmation: NeedsConfirmation = None,
) -> dict[str, Any]:
    params = _get_quest_params(session)
    # Real-expert skip policy: do not re-ask the same field in WhatsApp.
    # If the last asked param is still missing and has been asked once already, mark it not provided and move on.
    meta0 = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    session.extracted_fields = meta0
    lastask0 = meta0.get(QUEST_LAST_ASK) if isinstance(meta0, dict) else None
    asked0 = str(lastask0.get("askedParam") or "") if isinstance(lastask0, dict) else ""
    ask_counts0_raw = meta0.get(QUEST_ASK_COUNTS) if isinstance(meta0, dict) else None
    ask_counts0: dict[str, int] = ask_counts0_raw if isinstance(ask_counts0_raw, dict) else {}
    if (
        (channel or "").strip().lower() == "whatsapp"
        and asked0
        and asked0 not in params
        and int(ask_counts0.get(asked0) or 0) >= 1
    ):
        params2 = dict(params)
        params2[asked0] = {
            "value": "not provided",
            "confidence": 0.2,
            "ts": datetime.utcnow().isoformat() + "Z",
            "_user_skipped": True,
        }
        _set_quest_params(session, params2)
        params = _get_quest_params(session)
        ask_counts0[asked0] = 0
        meta0[QUEST_ASK_COUNTS] = ask_counts0
        session.extracted_fields = meta0

    pending = collect_pending_datapoints(service_id, params)
    collected_block = format_collected_params(params)

    meta_state = get_conversation_state(session)
    state_mood = str(meta_state.get("mood") or "neutral")
    # Empty string is used by _quest_pre_reply_phases for opening injection; it must not fall
    # through to get_last_user_message ("" is falsy with `or` and would skip the opening branch).
    if last_user_message is None:
        last_user_msg = get_last_user_message(session) or ""
    else:
        last_user_msg = last_user_message
    current_mood = detect_mood(last_user_msg, state_mood)
    is_ambiguous = detect_ambiguity(last_user_msg)
    wants_clarification = is_asking_for_clarification(last_user_msg)

    recent_user = [m for m in session.conversation_history if m.role == MessageRole.USER][-3:]
    multiple_acks = len(recent_user) >= 2 and all(
        re.match(
            r"^(sure|ok|okay|yes|yeah|yep|done|great|sounds good|perfect|cool|thanks|thank you|nice|awesome|have a good day)$",
            _normalize_voice_reply(m.content or ""),
            re.I,
        )
        for m in recent_user
    )

    mood_history = list(meta_state.get("moodHistory") or [])
    mood_history.append(current_mood)

    last_bot_msg = get_last_assistant_message(session)
    callback_val = params.get("callback_time")
    has_callback_time = callback_val is not None and (
        not isinstance(callback_val, dict) or callback_val.get("value") is not None
    )
    call_pat = re.compile(
        r"connect|call you|looking forward|we'll connect|schedule|talk to you|give you a call|call right away|"
        r"connecting with you|connect very soon|give you a call then|call you then|call then",
        re.I,
    )
    _coverage_done = is_coverage_satisfied(params, service_id)
    bot_just_confirmed_call = bool(_coverage_done and last_bot_msg and call_pat.search(last_bot_msg))
    user_short_ack = bool(re.match(
        r"^(sure|ok|okay|yes|yeah|yep|done|great|sounds good|perfect|cool|thanks|thank you|nice|awesome)$",
        _normalize_voice_reply(last_user_msg),
        re.I,
    ))
    recent_bot = [m for m in session.conversation_history if m.role == MessageRole.ASSISTANT][-2:]
    recent_bot_text = " ".join(m.content or "" for m in recent_bot)
    bot_has_confirmed_call = bool(_coverage_done and call_pat.search(recent_bot_text))

    # Project confirmation gate: after coverage is satisfied, require explicit user confirmation
    # before sending the "project created" closing.
    if is_coverage_satisfied(params, service_id) and not session.summary_generated:
        meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
        session.extracted_fields = meta
        awaiting = bool(meta.get("__quest:awaiting_project_confirm"))

        if awaiting:
            params_live = _get_quest_params(session)
            return await _process_awaiting_project_confirm(
                session,
                character,
                service_id,
                params_live,
                last_user_msg,
                meta,
                current_mood=current_mood,
                mood_history=mood_history,
                meta_state=meta_state,
            )

        meta["__quest:awaiting_project_confirm"] = True
        params_live = _get_quest_params(session)
        confirm_q = await _llm_review_recap_and_confirm_message(
            session,
            channel=channel,
            service_id=service_id,
            params=params_live,
        )
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": mood_history[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )
        return {"reply": confirm_q, "isComplete": False, "mood": current_mood}

    if (
        session.summary_generated
        and is_coverage_satisfied(params, service_id)
        and re.match(
            r"^(ok|okay|sure|yes|yeah|yep|thanks|thank you|done|great|perfect|cool|nice|awesome)\b",
            _normalize_voice_reply(last_user_msg),
            re.I,
        )
    ):
        return {
            "reply": _closing_append_signoff_warm_day(
                "Perfect — we already have everything. You're all set; the right PropFlow vendor will contact you shortly. 🙏"
            ),
            "isComplete": False,
            "mood": current_mood,
        }

    if (
        not session.summary_generated
        and (bot_just_confirmed_call or bot_has_confirmed_call)
        and user_short_ack
    ):
        closing = await generate_closing_message(session, character, service_id)
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": mood_history[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )
        return {"reply": closing, "isComplete": True, "mood": current_mood}

    if (
        not session.summary_generated
        and (bot_just_confirmed_call or bot_has_confirmed_call)
        and multiple_acks
    ):
        closing = await generate_closing_message(session, character, service_id)
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": mood_history[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )
        return {"reply": closing, "isComplete": True, "mood": current_mood}

    required_ids = get_required_fields_for_service(service_id)
    effective_pending = pending
    if current_mood in ("frustrated", "rushed"):
        effective_pending = [p for p in pending if p["id"] in required_ids]

    persona_summary = character.get("persona_summary") or ""
    tone = character.get("tone") or ""
    service_name = SERVICE_DISPLAY_NAMES.get(service_id, service_id.replace("_", " "))
    service_role = f"{service_name} consultant"

    prior_assistant_msgs = any(m.role == MessageRole.ASSISTANT for m in session.conversation_history)
    is_opening = (not str(last_user_msg or "").strip()) and (not prior_assistant_msgs) and bool(effective_pending)
    if is_opening:
        opening_prompt = (
            OPENING_PROMPT_TEMPLATE.replace("<CHARACTER_NAME>", character["name"])
            .replace("<SERVICE_ROLE>", service_role)
            .replace("<SERVICE_NAME>", service_name)
            .replace("<PERSONA_SUMMARY>", persona_summary[:QUEST_PERSONA_PROMPT_CHARS])
            .replace("<TONE>", tone or "warm, concise")
            .replace("<PENDING>", format_pending(effective_pending))
        )
        max_out = QUEST_GEMINI_MAX_OUTPUT_VOICE if (channel or "").strip().lower() == "voice" else QUEST_GEMINI_MAX_OUTPUT_DEFAULT
        with quest_llm_phase("opening"):
            opening_text = await _llm_system_only(session, opening_prompt, max_tokens=max_out)
        opening_text = humanize_response(opening_text.strip(), "neutral", 0, channel)
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": mood_history[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )
        return {"reply": opening_text, "isComplete": False, "mood": current_mood}

    transcript_block = build_transcript(session)
    mood_guidance = get_mood_guidance(current_mood)

    ambiguity_section = ""
    if wants_clarification:
        ambiguity_section = f"""
IMPORTANT: User said "{last_user_msg}" - they want SUGGESTIONS/EXAMPLES!
Last thing you asked about: "{last_bot_msg[:100] if last_bot_msg else ''}"
Your response MUST:
1. Give 2-3 brief options/examples for what YOU JUST ASKED
2. DO NOT ask about a different topic
3. DO NOT move to the next datapoint
4. End with something like "What feels right?" or "Any of these appeal to you?" """
    elif is_ambiguous:
        ambiguity_section = f"""
CRITICAL - AMBIGUOUS OR VAGUE ANSWER: User said "{last_user_msg}". You MUST re-ask or confirm what they meant for the topic you just asked about. Do NOT move to the next parameter. Say e.g. "Perfect — so you meant X, correct?" or give 2–3 clear options. Wait for their confirmation before moving on."""

    call_confirmed_section = ""
    if (bot_just_confirmed_call or bot_has_confirmed_call) and user_short_ack:
        call_confirmed_section = """
CRITICAL - CALL ALREADY CONFIRMED: You already said you'll connect/call and the user acknowledged ("sure", "ok", etc.). The conversation is COMPLETE. Do NOT ask any new questions. Do NOT continue the conversation. Reply with ONLY a brief sign-off, e.g. "Great, see you then!" or "Talk to you tomorrow!" – one short sentence max. Then STOP."""
    elif bot_just_confirmed_call or bot_has_confirmed_call:
        call_confirmed_section = """
IMPORTANT: You just confirmed you'll call/connect with the user. Wait for their acknowledgment. If they say "ok", "sure", "yes", etc., the conversation will be complete."""

    confirm_section = ""
    if needs_confirmation:
        fld = needs_confirmation.get("field", "")
        val = needs_confirmation.get("value", "")
        reason = needs_confirmation.get("reason", "")
        field_label = fld.replace("_", " ")
        confirm_section = f"""
CRITICAL - CONFIRM BEFORE MOVING ON: User gave "{val}" for {field_label}. {reason}
Your NEXT message MUST ask them to confirm (e.g. "Perfect — so {val}, correct?" or "Did you mean {val}?"). Do NOT move to a new topic. Do NOT ask about building plans or anything else until they confirm."""

    # Fix #7 (double-confirm loop): if the user JUST confirmed a previous needs_confirmation,
    # explicitly forbid reconfirming in the next assistant reply.
    recently_confirmed_section = ""
    try:
        meta_raw = session.extracted_fields.get(QUEST_META)
        meta_now: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
        lc = meta_now.get("lastConfirmed")
        if isinstance(lc, dict) and lc.get("field") and lc.get("value") and not needs_confirmation:
            fld = str(lc.get("field") or "").replace("_", " ").strip()
            val = str(lc.get("value") or "").strip()
            recently_confirmed_section = f"""
CRITICAL - JUST CONFIRMED: The user just confirmed {fld} = "{val}".
Do NOT ask them to confirm this again. Do NOT repeat "so you meant {val}, correct?".
Move on to the NEXT missing field in the pending list."""
    except Exception:
        recently_confirmed_section = ""

    max_turns = character.get("max_turns_before_direct_ask") or MAX_TURNS_BEFORE_DIRECT_ASK
    prompt = (
        ASSISTANT_PROMPT_TEMPLATE.replace("<CHARACTER_NAME>", character["name"])
        .replace("<SERVICE_ROLE>", service_role)
        .replace("<SERVICE_NAME>", service_name)
        .replace("<PERSONA_SUMMARY>", persona_summary[:QUEST_PERSONA_PROMPT_CHARS])
        .replace("<TONE>", tone or "warm, concise")
        .replace("<MOOD>", str(current_mood))
        .replace("<MOOD_GUIDANCE>", mood_guidance)
        .replace("<COLLECTED>", collected_block)
        .replace("<TRANSCRIPT>", transcript_block or "No prior context")
        .replace("<PENDING>", format_pending(effective_pending) if effective_pending else "None - all data collected!")
        .replace("<AMBIGUITY_SECTION>", ambiguity_section)
        .replace("<CONFIRM_SECTION>", confirm_section)
        .replace("<RECENTLY_CONFIRMED_SECTION>", recently_confirmed_section)
        .replace("<CALL_CONFIRMED_SECTION>", call_confirmed_section)
        .replace("<MAX_TURNS>", str(max_turns))
    )

    max_out = QUEST_GEMINI_MAX_OUTPUT_VOICE if channel == "voice" else QUEST_GEMINI_MAX_OUTPUT_DEFAULT
    with quest_llm_phase("assistant_reply"):
        raw_reply = (await _llm_system_only(session, prompt, max_tokens=max_out)).strip()
    text = humanize_response(
        raw_reply,
        str(current_mood),
        meta_state.get("turnCount") or len(session.conversation_history),
        channel,
    )

    if get_settings().log_quest_reply_pipeline:
        punct_parts = [p.strip() for p in re.split(r"[.!?]", raw_reply) if p.strip()]
        over_200 = len(raw_reply) > 200
        await log_event(
            "QUEST_REPLY_PIPELINE",
            session_id=session.session_id,
            data={
                "channel": channel,
                "max_output_tokens": max_out,
                "raw_len": len(raw_reply),
                "humanized_len": len(text),
                "raw_over_200_chars": over_200,
                "punct_split_segment_count": len(punct_parts),
                "likely_humanize_two_segment_cap": over_200 and len(punct_parts) > 2,
                "raw_reply": raw_reply[:4000],
                "humanized_reply": text[:4000],
            },
        )

    update_conversation_state_preserve_confirmation(
        session,
        {
            "mood": current_mood,
            "moodHistory": mood_history[-20:],
            "ambiguousFields": meta_state.get("ambiguousFields") or [],
            "clarificationCount": meta_state.get("clarificationCount") or 0,
            "turnCount": len(session.conversation_history),
        },
    )
    return {"reply": text, "isComplete": False, "mood": current_mood}


@dataclass
class QuestTurnResult:
    assistant_text: str
    completed: bool
    summary_generated: bool


@dataclass
class QuestPreReplyState:
    service_id: str
    character: dict[str, Any]
    merged_out: dict[str, Any] | None
    merged_turn: bool
    needs_confirmation: NeedsConfirmation
    opening_text: str | None
    opening_ms: float
    extraction_ms: float
    reask_last_question: bool
    # High-confidence fields applied this turn (from to_apply). Used so ask-count / auto-skip
    # never fires for a slot the user actually answered on the same turn.
    applied_param_ids: frozenset[str] = field(default_factory=frozenset)


async def _quest_pre_reply_phases(
    session: Session, user_message: str, channel: str
) -> QuestPreReplyState:
    opening_ms = 0.0
    service_id = ensure_quest_service(session)
    params = _get_quest_params(session)
    character = build_character_view(session, service_id)

    # Record the previous assistant question + this user answer into conversationFlow.
    # (The assistant "ask" is stored after each assistant reply.)
    _append_conversation_flow_answer(session, service_id=service_id, user_answer=user_message)

    prior_assistant = any(m.role == MessageRole.ASSISTANT for m in session.conversation_history)
    opening_text: str | None = None
    # Opening injection rules:
    # - Voice MUST always have an intro, because Vapi plays firstMessage and the quest engine should not
    #   skip/omit the opening due to merged settings (voice does not use merged extract+reply anyway).
    # - For non-voice channels, keep quest behavior: if merged extract+reply is enabled, let it handle
    #   the first-turn greeting in the merged call (saves an LLM round trip).
    if user_message.strip() and not prior_assistant and (channel == "voice" or not QUEST_MERGED_EXTRACT_REPLY):
        t_open = time.perf_counter()
        opening_res = await generate_assistant_reply(
            session,
            character,
            service_id,
            last_user_message="",
            channel=channel,
            needs_confirmation=None,
        )
        # IMPORTANT: do NOT append this to the transcript yet.
        # For voice, we want the opening to be the *actual* assistant reply for this turn
        # (otherwise it gets immediately followed by a second "assistant_reply_stream" question,
        # and the user never hears the introduction).
        opening_text = str(opening_res.get("reply") or "").strip() or None
        opening_ms = (time.perf_counter() - t_open) * 1000.0
        if channel == "voice" and opening_text:
            # Short-circuit: the opening prompt already includes a greeting + first question.
            # Returning it as the single assistant message avoids "no intro" in voice.
            return QuestPreReplyState(
                service_id=service_id,
                character=character,
                merged_out=None,
                merged_turn=False,
                needs_confirmation=None,
                opening_text=opening_text,
                opening_ms=opening_ms,
                extraction_ms=0.0,
                reask_last_question=False,
                applied_param_ids=frozenset(),
            )

    meta = dict(session.extracted_fields.get(QUEST_META) or {})
    last_needs = meta.get("lastNeedsConfirmation")
    user_confirmed = bool(
        re.match(
            r"^(yes|yeah|yep|sure|ok|okay|correct|that's right|that is right|right|exactly)$",
            _normalize_voice_reply(user_message),
            re.I,
        )
    )
    if last_needs and user_confirmed:
        field = last_needs.get("field")
        value = last_needs.get("value")
        if field:
            params[field] = {"value": value, "confidence": 0.95, "ts": datetime.utcnow().isoformat() + "Z"}
            _set_quest_params(session, params)
            # Fix #7 (double-confirm loop): record a one-turn "just confirmed" marker
            # so the reply prompt can forbid reconfirming the same field again.
            meta["lastConfirmed"] = {"field": field, "value": value, "ts": datetime.utcnow().isoformat() + "Z"}
        meta.pop("lastNeedsConfirmation", None)
        session.extracted_fields[QUEST_META] = meta

    # Voice/text correction detector (ASR correction handling).
    # Must run before extraction so we can clear the prior asked field and re-ask the same question.
    is_correction = await _llm_yes_no_correction_check(session, user_message)
    if is_correction is True:
        meta_lastask_raw = (
            session.extracted_fields.get(QUEST_LAST_ASK) if isinstance(session.extracted_fields, dict) else None
        )
        meta_lastask = meta_lastask_raw if isinstance(meta_lastask_raw, dict) else {}
        asked_param = str(meta_lastask.get("askedParam") or "").strip()
        if asked_param:
            params2 = _get_quest_params(session)
            if asked_param in params2:
                del params2[asked_param]
                _set_quest_params(session, params2)
            await log_event("QUEST_CORRECTION_DETECTED", session_id=session.session_id, data={"field": asked_param})
        # Force re-ask: if correction detected, do not attempt extraction this turn.
        return QuestPreReplyState(
            service_id=service_id,
            character=character,
            merged_out=None,
            merged_turn=False,
            needs_confirmation=None,
            opening_text=None,
            opening_ms=opening_ms,
            extraction_ms=0.0,
            reask_last_question=True,
            applied_param_ids=frozenset(),
        )

    # Fix #6: "you tell me / suggest" should produce a recommendation for the
    # CURRENT asked field, not bounce to a domain-answer revert loop.
    if (channel or "").strip().lower() == "voice" and _looks_like_suggestion_request(user_message):
        meta_lastask_raw = (
            session.extracted_fields.get(QUEST_LAST_ASK) if isinstance(session.extracted_fields, dict) else None
        )
        meta_lastask = meta_lastask_raw if isinstance(meta_lastask_raw, dict) else {}
        asked_param = str(meta_lastask.get("askedParam") or "").strip()
        params_now = _get_quest_params(session)
        if asked_param == "capacity_kw":
            sug = _suggest_capacity_kw(params_now)
            if sug is not None:
                needs_confirmation = {
                    "field": "capacity_kw",
                    "value": sug,
                    "reason": "based on what you've shared so far",
                }
                # Return without extraction: the reply phase will ask for confirmation.
                return QuestPreReplyState(
                    service_id=service_id,
                    character=character,
                    merged_out=None,
                    merged_turn=False,
                    needs_confirmation=needs_confirmation,
                    opening_text=None,
                    opening_ms=opening_ms,
                    extraction_ms=0.0,
                    reask_last_question=False,
                    applied_param_ids=frozenset(),
                )

    t_ext = time.perf_counter()
    merged_turn = False
    merged_out: dict[str, Any] | None = None
    # Voice: keep the pipeline stream-friendly by using classic extraction.
    # Merged extract+reply currently disables main reply streaming and increases perceived latency.
    voice_can_use_merged = (
        channel == "voice"
        and VOICE_USE_MERGED_EXTRACT_REPLY
        and QUEST_MERGED_EXTRACT_REPLY
    )
    if (
        (channel != "voice" or voice_can_use_merged)
        and QUEST_MERGED_EXTRACT_REPLY
        and (user_message or "").strip()
    ):
        merged_out = await _try_merged_extract_and_reply(
            session, character, service_id, user_message.strip(), channel, params
        )
    if merged_out is None:
        extracted = await extract_datapoints_from_message(session, user_message, service_id, params)
    else:
        merged_turn = True
        extracted = merged_out["extracted"]
    extraction_ms = (time.perf_counter() - t_ext) * 1000.0

    to_apply, needs_confirmation = filter_extractions_needing_confirmation(session, service_id, params, extracted)
    # WhatsApp/text normalization for solar roof orientation: users often say "east facing".
    # Our parameter hint includes "east-west", but we should not coerce "east" into "east-west".
    if "orientation" in to_apply and isinstance(to_apply.get("orientation"), dict):
        uv = str(user_message or "").strip().lower()
        v = str(to_apply["orientation"].get("value") or "").strip().lower()
        if uv:
            has_east = "east" in uv
            has_west = "west" in uv
            has_north = "north" in uv
            has_south = "south" in uv
            # Only override when the user was unambiguous.
            if has_east and not has_west and not has_north and not has_south:
                to_apply["orientation"]["value"] = "east"
            elif has_west and not has_east and not has_north and not has_south:
                to_apply["orientation"]["value"] = "west"
            elif has_south and not has_east and not has_west and not has_north:
                to_apply["orientation"]["value"] = "south"
            elif has_north and not has_east and not has_west and not has_south:
                to_apply["orientation"]["value"] = "north"
            else:
                # If model guessed "east-west" but user didn't say both, don't force it.
                if v in ("east-west", "east west") and (has_east ^ has_west):
                    to_apply["orientation"]["value"] = "east" if has_east else "west"
    apply_extracted_ts(session, service_id, params, to_apply)
    params = _get_quest_params(session)
    applied_param_ids = frozenset((to_apply or {}).keys())

    reask_last_question = (
        not needs_confirmation
        and not to_apply
        and _is_meaningless_midturn_utterance(user_message)
    )

    # Voice: 1–2 word non-answers often appear when user is pausing or ASR truncates.
    # If extraction applied nothing, treat these as meaningless and re-ask last question,
    # unless the utterance looks like it is trying to answer something meaningful.
    if (channel or "").strip().lower() == "voice" and not needs_confirmation and not to_apply:
        norm = _normalize_voice_reply(user_message)
        words = [w for w in re.split(r"\s+", norm) if w]
        if 1 <= len(words) <= 2:
            # conservative allowlist of short meaningful replies
            short_meaningful = {
                "yes", "no", "yeah", "yep", "nope",
                "ok", "okay", "sure",
                "done", "thanks", "thank you",
            }
            if norm not in short_meaningful:
                reask_last_question = True

    # Voice-only: if the active question was contact preference and we still don't have it,
    # re-ask the same question instead of advancing to other fields.
    if (channel or "").strip().lower() == "voice" and not needs_confirmation:
        meta_lastask_raw = (
            session.extracted_fields.get(QUEST_LAST_ASK) if isinstance(session.extracted_fields, dict) else None
        )
        meta_lastask = meta_lastask_raw if isinstance(meta_lastask_raw, dict) else {}
        asked_param = str(meta_lastask.get("askedParam") or "").strip()
        if (
            asked_param == "contact_pref"
            and not get_param_value(params, "contact_pref")
            and "contact_pref" not in to_apply
        ):
            reask_last_question = True

    if needs_confirmation:
        meta = dict(session.extracted_fields.get(QUEST_META) or {})
        meta["lastNeedsConfirmation"] = {
            "field": needs_confirmation["field"],
            "value": needs_confirmation["value"],
        }
        session.extracted_fields[QUEST_META] = meta
    else:
        meta = dict(session.extracted_fields.get(QUEST_META) or {})
        if last_needs and not user_confirmed:
            meta.pop("lastNeedsConfirmation", None)
        if last_needs and last_needs.get("field") in to_apply:
            meta.pop("lastNeedsConfirmation", None)
        session.extracted_fields[QUEST_META] = meta

    last_bot_after = get_last_assistant_message(session)
    agreed_to_call = bool(
        re.search(r"\b(yes|sure|ok|yeah|yep)\b", user_message.strip(), re.I)
    ) and bool(
        re.search(
            r"schedule|connect|call you|give you a call|call right away|quick chat|when would|looking forward|we'll connect|connecting with you",
            last_bot_after or "",
            re.I,
        )
    )
    if agreed_to_call:
        if not get_param_value(params, "contact_pref"):
            params["contact_pref"] = {"value": "phone", "confidence": 0.9, "ts": datetime.utcnow().isoformat() + "Z"}
        if not get_param_value(params, "callback_time") and re.search(
            r"right away|asap|very soon|soon\b|connecting with you",
            last_bot_after or "",
            re.I,
        ):
            val = "now" if re.search(r"right away|asap", last_bot_after or "", re.I) else "soon"
            params["callback_time"] = {"value": val, "confidence": 0.9, "ts": datetime.utcnow().isoformat() + "Z"}
        _set_quest_params(session, params)

    return QuestPreReplyState(
        service_id=service_id,
        character=character,
        merged_out=merged_out,
        merged_turn=merged_turn,
        needs_confirmation=needs_confirmation,
        opening_text=opening_text,
        opening_ms=opening_ms,
        extraction_ms=extraction_ms,
        reask_last_question=reask_last_question,
        applied_param_ids=applied_param_ids,
    )


async def _quest_compute_gen_dict(
    session: Session,
    user_message: str,
    channel: str,
    pre: QuestPreReplyState,
) -> dict[str, Any]:
    params = _get_quest_params(session)
    merged_out = pre.merged_out
    needs_confirmation = pre.needs_confirmation
    character = pre.character
    service_id = pre.service_id

    if pre.reask_last_question:
        last_q = get_last_assistant_message(session) or ""
        meta_state = get_conversation_state(session)
        state_mood = str(meta_state.get("mood") or "neutral")
        current_mood = detect_mood(user_message.strip(), state_mood)
        _mh = list(meta_state.get("moodHistory") or [])
        _mh.append(current_mood)
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": _mh[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )
        return {"reply": last_q or "Sorry—could you repeat that?", "isComplete": False, "mood": current_mood}

    if merged_out is not None:
        meta_state = get_conversation_state(session)
        state_mood = str(meta_state.get("mood") or "neutral")
        current_mood = detect_mood(user_message.strip(), state_mood)
        raw_reply = merged_out["raw_reply"]
        reply_text = humanize_response(
            raw_reply,
            str(current_mood),
            meta_state.get("turnCount") or len(session.conversation_history),
            channel,
        )
        # IMPORTANT: when we are holding a value for confirmation, do NOT let the merged model
        # move on to the next question in the same breath. That pattern causes users to answer,
        # then later get asked again because the held value was never confirmed/applied.
        if needs_confirmation:
            fld = str(needs_confirmation.get("field") or "").replace("_", " ").strip() or "that detail"
            val = needs_confirmation.get("value")
            reason = str(needs_confirmation.get("reason") or "").strip()
            if reason and len(reason) <= 160:
                reply_text = f"Quick check — {reason} Should I record {val} for {fld}?"
            else:
                reply_text = f"Perfect — so {val}, correct?"
            is_complete_merged = False
        else:
            is_complete_merged = bool(merged_out.get("model_is_complete"))
        # IMPORTANT: never bypass the project confirmation gate in merged mode.
        if is_coverage_satisfied(params, service_id) and not session.summary_generated:
            meta_conf = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
            session.extracted_fields = meta_conf
            awaiting_conf = bool(meta_conf.get("__quest:awaiting_project_confirm"))
            _mh_rev = list(meta_state.get("moodHistory") or [])
            _mh_rev.append(current_mood)
            if not awaiting_conf:
                meta_conf["__quest:awaiting_project_confirm"] = True
                params_live = _get_quest_params(session)
                confirm_q = await _llm_review_recap_and_confirm_message(
                    session,
                    channel=channel,
                    service_id=service_id,
                    params=params_live,
                )
                update_conversation_state_preserve_confirmation(
                    session,
                    {
                        "mood": current_mood,
                        "moodHistory": _mh_rev[-20:],
                        "ambiguousFields": meta_state.get("ambiguousFields") or [],
                        "clarificationCount": meta_state.get("clarificationCount") or 0,
                        "turnCount": len(session.conversation_history),
                    },
                )
                return {"reply": confirm_q, "isComplete": False, "mood": current_mood}

            params_live = _get_quest_params(session)
            review_out = await _process_awaiting_project_confirm(
                session,
                character,
                service_id,
                params_live,
                user_message,
                meta_conf,
                current_mood=current_mood,
                mood_history=_mh_rev,
                meta_state=meta_state,
            )
            reply_text = humanize_response(
                (review_out.get("reply") or "").strip(),
                str(review_out.get("mood", current_mood)),
                meta_state.get("turnCount") or len(session.conversation_history),
                channel,
            )
            is_complete_merged = bool(review_out.get("isComplete"))
            return {
                "reply": reply_text,
                "isComplete": is_complete_merged,
                "mood": review_out.get("mood", current_mood),
            }
        _mh = list(meta_state.get("moodHistory") or [])
        _mh.append(current_mood)
        update_conversation_state_preserve_confirmation(
            session,
            {
                "mood": current_mood,
                "moodHistory": _mh[-20:],
                "ambiguousFields": meta_state.get("ambiguousFields") or [],
                "clarificationCount": meta_state.get("clarificationCount") or 0,
                "turnCount": len(session.conversation_history),
            },
        )
        return {"reply": reply_text, "isComplete": is_complete_merged, "mood": current_mood}
    return await generate_assistant_reply(
        session,
        character,
        service_id,
        last_user_message=user_message,
        channel=channel,
        needs_confirmation=needs_confirmation,
    )


async def _finalize_main_stream_raw_to_gen(session: Session, user_message: str, channel: str, raw_reply_full: str) -> dict[str, Any]:
    meta_state = get_conversation_state(session)
    state_mood = str(meta_state.get("mood") or "neutral")
    current_mood = detect_mood(user_message.strip(), state_mood)
    max_out = QUEST_GEMINI_MAX_OUTPUT_VOICE if channel == "voice" else QUEST_GEMINI_MAX_OUTPUT_DEFAULT
    raw_reply = raw_reply_full.strip()
    text = humanize_response(
        raw_reply,
        str(current_mood),
        meta_state.get("turnCount") or len(session.conversation_history),
        channel,
    )

    if get_settings().log_quest_reply_pipeline:
        punct_parts = [p.strip() for p in re.split(r"[.!?]", raw_reply) if p.strip()]
        over_200 = len(raw_reply) > 200
        await log_event(
            "QUEST_REPLY_PIPELINE",
            session_id=session.session_id,
            data={
                "channel": channel,
                "max_output_tokens": max_out,
                "raw_len": len(raw_reply),
                "humanized_len": len(text),
                "raw_over_200_chars": over_200,
                "punct_split_segment_count": len(punct_parts),
                "likely_humanize_two_segment_cap": over_200 and len(punct_parts) > 2,
                "raw_reply": raw_reply[:4000],
                "humanized_reply": text[:4000],
                "streamed_main_llm": True,
            },
        )

    _mh = list(meta_state.get("moodHistory") or [])
    _mh.append(current_mood)
    update_conversation_state_preserve_confirmation(
        session,
        {
            "mood": current_mood,
            "moodHistory": _mh[-20:],
            "ambiguousFields": meta_state.get("ambiguousFields") or [],
            "clarificationCount": meta_state.get("clarificationCount") or 0,
            "turnCount": len(session.conversation_history),
        },
    )
    return {"reply": text, "isComplete": False, "mood": current_mood}


async def _quest_turn_finalize(
    session: Session,
    user_message: str,
    channel: str,
    pre: QuestPreReplyState,
    gen: dict[str, Any],
    t_turn0: float,
    reply_ms: float,
    *,
    voice_streamed_main: bool = False,
) -> QuestTurnResult:
    reply = gen["reply"]
    is_complete = bool(gen.get("isComplete"))

    # Voice ack-dedup: if this turn's opening ack ("Got it.", "Nice.", etc.)
    # matches the previous turn's ack, drop it from the spoken reply. The
    # streaming path in vapi_handler applies the SAME rule on the same
    # prev_ack source-of-truth (session.extracted_fields["__voice:lastAck"]),
    # so audio and stored transcript stay in sync. State is updated here
    # ONCE per turn so both paths read the same prev_ack during the turn.
    if (channel or "").strip().lower() == "voice" and reply and not is_complete:
        from backend.agents.voice.voice_response_optimizer import (
            detect_leading_ack,
            strip_leading_ack,
        )

        meta_ack = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
        prev_ack = str(meta_ack.get(VOICE_LAST_ACK) or "").strip().lower()
        current_ack = detect_leading_ack(reply)
        if current_ack and prev_ack and current_ack == prev_ack:
            stripped = strip_leading_ack(reply)
            if stripped and stripped != reply:
                reply = stripped
                gen["reply"] = reply
                meta_ack[VOICE_LAST_ACK] = ""
                await log_event(
                    "VOICE_ACK_DEDUPED",
                    session_id=session.session_id,
                    data={"ack": current_ack},
                )
            else:
                meta_ack[VOICE_LAST_ACK] = current_ack
        else:
            meta_ack[VOICE_LAST_ACK] = current_ack or ""
        session.extracted_fields = meta_ack

    summary_ms = 0.0
    if is_complete and session.summary_generated:
        already_done = (
            "You're all set — we already have your details. "
            "We'll connect at the time you shared. 🙏"
        )
        session.add_message(MessageRole.ASSISTANT, already_done)
        return QuestTurnResult(assistant_text=already_done, completed=True, summary_generated=False)

    if is_complete:
        from backend.questionnaire import summary_generator as summary_gen

        t_sum = time.perf_counter()
        voice = (channel or "").strip().lower() == "voice"
        defer_six = voice and get_settings().voice_defer_six_point_summary

        if defer_six:

            async def _deferred_voice_six_point() -> None:
                from backend.storage.redis_store import save_session as _save_voice_session

                try:
                    sp = await summary_gen.generate_six_point_summary_for_session(session, pre.service_id)
                    session.six_point_summary = sp
                    await _save_voice_session(session)
                except Exception as err:  # noqa: BLE001
                    await log_event(
                        "QUEST_SUMMARY_ERROR",
                        session_id=session.session_id,
                        data={"phase": "six_point_summary_deferred", "error": str(err)[:300]},
                    )

            summary_res = await summary_gen.generate_project_summary_for_session(session, pre.service_id)
            if isinstance(summary_res, dict):
                summary = summary_res
            else:
                if isinstance(summary_res, Exception):
                    await log_event(
                        "QUEST_SUMMARY_ERROR",
                        session_id=session.session_id,
                        data={"phase": "project_summary", "error": str(summary_res)[:300]},
                    )
                summary = await summary_gen.generate_project_summary_for_session(session, pre.service_id)

            params_for_fb = _get_quest_params(session)
            flat_fb = summary_gen.flatten_params_for_summary(params_for_fb)
            mood_raw = session.extracted_fields.get(QUEST_META)
            mood_meta_fb: dict[str, Any] = mood_raw if isinstance(mood_raw, dict) else {}
            mood_line = summary_gen.get_mood_analysis_summary(mood_meta_fb)
            six_point = summary_gen.generate_fallback_six_point_summary(
                session, pre.service_id, flat_fb, mood_line
            )
            asyncio.create_task(_deferred_voice_six_point())
        else:
            summary_res, six_res = await asyncio.gather(
                summary_gen.generate_project_summary_for_session(session, pre.service_id),
                summary_gen.generate_six_point_summary_for_session(session, pre.service_id),
                return_exceptions=True,
            )
            if isinstance(summary_res, dict):
                summary = summary_res
            else:
                if isinstance(summary_res, Exception):
                    await log_event(
                        "QUEST_SUMMARY_ERROR",
                        session_id=session.session_id,
                        data={"phase": "project_summary", "error": str(summary_res)[:300]},
                    )
                summary = await summary_gen.generate_project_summary_for_session(session, pre.service_id)
            if isinstance(six_res, dict):
                six_point = six_res
            else:
                if isinstance(six_res, Exception):
                    await log_event(
                        "QUEST_SUMMARY_ERROR",
                        session_id=session.session_id,
                        data={"phase": "six_point_summary", "error": str(six_res)[:300]},
                    )
                six_point = await summary_gen.generate_six_point_summary_for_session(session, pre.service_id)
        summary_ms = (time.perf_counter() - t_sum) * 1000.0
        session.extracted_fields[QUEST_SUMMARY] = summary
        session.summary = summary
        session.six_point_summary = six_point
        session.summary_generated = True
        session.conversation_stage = ConversationStage.SUMMARY_GENERATED
        session.add_message(MessageRole.ASSISTANT, reply)
        out = QuestTurnResult(assistant_text=reply, completed=True, summary_generated=True)
    else:
        session.add_message(MessageRole.ASSISTANT, reply)
        out = QuestTurnResult(assistant_text=reply, completed=False, summary_generated=False)

    # Store the assistant "ask" for the next user turn to pair into conversationFlow.
    # We do this after the assistant message is added so the question text matches what the user heard.
    if not is_complete:
        params_now = _get_quest_params(session)
        pending_now = collect_pending_datapoints(pre.service_id, params_now)
        asked_param = ""
        if pending_now:
            asked_param = str(pending_now[0].get("id") or "")
        if pre.needs_confirmation and isinstance(pre.needs_confirmation, dict):
            asked_param = str(pre.needs_confirmation.get("field") or asked_param)
        meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}

        # Fix #7: ask-count guard. Track how many turns in a row we have asked
        # the SAME field. If we exceed ASK_COUNT_SKIP_THRESHOLD, inject a
        # low-confidence placeholder so collect_pending_datapoints stops
        # returning it and the flow moves forward. Prevents infinite re-ask
        # loops when ASR/extraction can't lock a value for that field.
        prev_lastask_raw = meta.get(QUEST_LAST_ASK) if isinstance(meta, dict) else None
        prev_asked = ""
        if isinstance(prev_lastask_raw, dict):
            prev_asked = str(prev_lastask_raw.get("askedParam") or "")
        ask_counts_raw = meta.get(QUEST_ASK_COUNTS) if isinstance(meta, dict) else None
        ask_counts: dict[str, int] = ask_counts_raw if isinstance(ask_counts_raw, dict) else {}
        filled_this_turn = pre.applied_param_ids
        if asked_param:
            # Help/Recommendation turns should not count as a "miss" for the ask-count guard.
            # Example: user replies "recommend" to a budget question → we give guidance and re-ask,
            # but must not auto-skip budget as "not specified" just because we helped.
            help_turn = bool(_looks_like_suggestion_request(user_message or ""))
            if asked_param in filled_this_turn and not help_turn:
                # User supplied a high-confidence value for this slot on this turn — never treat as a miss.
                ask_counts[asked_param] = 0
            elif asked_param == prev_asked:
                if not help_turn:
                    ask_counts[asked_param] = int(ask_counts.get(asked_param) or 0) + 1
            else:
                ask_counts[asked_param] = 1
            # Keep counters for all OTHER fields so we don't lose history, but
            # reset the just-answered one (not the current asked_param).
        meta[QUEST_ASK_COUNTS] = ask_counts

        if (
            asked_param
            and ASK_COUNT_SKIP_THRESHOLD > 0
            and not bool(_looks_like_suggestion_request(user_message or ""))
            and asked_param not in filled_this_turn
            and ask_counts.get(asked_param, 0) >= ASK_COUNT_SKIP_THRESHOLD
        ):
            params_skip = _get_quest_params(session)
            if asked_param not in params_skip:
                params_skip[asked_param] = {
                    "value": "not specified",
                    "confidence": 0.3,
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "_auto_skipped": True,
                }
                _set_quest_params(session, params_skip)
                await log_event(
                    "QUEST_FIELD_AUTO_SKIPPED",
                    session_id=session.session_id,
                    data={"field": asked_param, "asks": ask_counts[asked_param]},
                )
            # Clear the counter so the same slot isn't kept at the cap forever.
            ask_counts[asked_param] = 0
            meta[QUEST_ASK_COUNTS] = ask_counts

        meta[QUEST_LAST_ASK] = {
            "askedParam": asked_param,
            "parameterLabel": _get_param_label(pre.service_id, asked_param) if asked_param else "",
            "question": str(reply or "").strip(),
            "answered": False,
        }
        session.extracted_fields = meta

    # Clear one-turn markers after the assistant reply is produced.
    meta_clear = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    if isinstance(meta_clear, dict):
        qm = meta_clear.get(QUEST_META)
        if isinstance(qm, dict) and "lastConfirmed" in qm:
            qm.pop("lastConfirmed", None)
            meta_clear[QUEST_META] = qm
            session.extracted_fields = meta_clear

    if get_settings().log_quest_turn_timing:
        total_ms = (time.perf_counter() - t_turn0) * 1000.0
        timing_data: dict[str, Any] = {
            "channel": channel,
            "opening_ms": round(pre.opening_ms, 2),
            "extraction_ms": round(pre.extraction_ms, 2),
            "reply_ms": round(reply_ms, 2),
            "summary_ms": round(summary_ms, 2),
            "total_ms": round(total_ms, 2),
            "completed": is_complete,
            "merged_extract_reply": pre.merged_turn,
            "voice_streamed_main_llm": voice_streamed_main,
        }
        await log_event(
            "QUEST_TURN_TIMING",
            session_id=session.session_id,
            data=timing_data,
        )
    return out


async def prepare_voice_quest_stream_or_sync(
    session: Session,
    user_message: str,
) -> QuestTurnResult | tuple[Callable[[], AsyncIterator[str]], Callable[[str, float], Awaitable[QuestTurnResult]]]:
    """
    Voice-only: either returns a completed QuestTurnResult (sync path) or
    (stream_factory, finalize) where finalize must be called with concatenated raw model text and reply-phase ms.
    """
    t_turn0 = time.perf_counter()
    # Per-turn reset: prevents a stale end-call flag from the prior turn (or from a
    # crashed/incomplete turn) from spuriously hanging up the next turn. Branches
    # below that actually want to end the call will re-set this to True.
    session.voice_turn_requested_end_call = False
    service_id = ensure_quest_service(session)
    params = _get_quest_params(session)
    if session.summary_generated and is_coverage_satisfied(params, service_id):
        if not post_completion_user_requests_data_change(user_message):
            msg_norm = (user_message or "").strip()
            # Warm close patterns — caller signals they are done. End the call gracefully.
            #
            # Why the regex is structured this way: real callers chain acks+farewells
            # ("Okay. Bye bye.", "Ok thanks bye", "Alright, thanks!"). The previous
            # regex anchored with `[\s\W]*$` only allowed ONE token before end-of-string,
            # so it silently missed "Okay. Bye bye." — and the call never hung up.
            # The new form allows ANY sequence of close-tokens separated by whitespace
            # or punctuation, which covers all observed compound farewells.
            _close_token = (
                r"(?:ok(?:ay)?|k|yes|yeah|yep|sure|right|correct|exactly|"
                r"thanks?(?:\s+(?:a\s+lot|so\s+much|buddy|priya|you))?|thank\s+you|"
                r"that(?:'s|s|\s+is)\s+(?:all|it|fine)|all\s+(?:good|set|done)|"
                r"sounds?\s+good|perfect|wonderful|cool|got\s+it|alright|"
                r"no\s+(?:thanks|questions|nothing)|nothing\s+else|"
                r"bye(?:[-\s]+bye)?|good\s*bye|goodbye|see\s+(?:you|ya)|"
                r"talk\s+(?:later|soon)|have\s+a\s+(?:good|great|nice)\s+(?:day|one|time|evening))"
            )
            graceful_close = bool(
                re.match(
                    rf"^\W*{_close_token}(?:\W+{_close_token})*\W*$",
                    msg_norm,
                    re.I,
                )
            )
            if graceful_close:
                # Warm one-line goodbye, then signal Vapi to hang up.
                reply = "Perfect — have a great day!"
                session.voice_turn_requested_end_call = True
                session.add_message(MessageRole.ASSISTANT, reply)
                return QuestTurnResult(assistant_text=reply, completed=True, summary_generated=False)

            # Caller said something else after the closing line — likely a quick follow-up
            # question. Give a brief polite line and keep the window open one more turn
            # so they can say "ok" / "bye" naturally.
            reply = (
                "Sure — our team will share all those details when they call you. "
                "Anything else I can answer right now? Otherwise have a great day!"
            )
            session.add_message(MessageRole.ASSISTANT, reply)
            return QuestTurnResult(assistant_text=reply, completed=True, summary_generated=False)
    pre = await _quest_pre_reply_phases(session, user_message, "voice")
    settings = get_settings()
    if pre.opening_text:
        # First voice user turn: return opening as the sole assistant message.
        # This guarantees the caller hears an intro instead of jumping straight into questions.
        t_reply = time.perf_counter()
        gen = {"reply": pre.opening_text, "isComplete": False, "mood": "neutral"}
        reply_ms = (time.perf_counter() - t_reply) * 1000.0
        return await _quest_turn_finalize(session, user_message, "voice", pre, gen, t_turn0, reply_ms)
    if not settings.voice_stream_main_llm:
        t_reply = time.perf_counter()
        gen = await _quest_compute_gen_dict(session, user_message, "voice", pre)
        reply_ms = (time.perf_counter() - t_reply) * 1000.0
        return await _quest_turn_finalize(session, user_message, "voice", pre, gen, t_turn0, reply_ms)

    can_stream_main = (
        pre.merged_out is None
        and not pre.needs_confirmation
        and _assistant_main_prompt_only_sync(session, pre.character, pre.service_id, user_message.strip(), "voice")
        is not None
    )
    if not can_stream_main:
        t_reply = time.perf_counter()
        gen = await _quest_compute_gen_dict(session, user_message, "voice", pre)
        reply_ms = (time.perf_counter() - t_reply) * 1000.0
        return await _quest_turn_finalize(session, user_message, "voice", pre, gen, t_turn0, reply_ms)

    prompt = _assistant_main_prompt_only_sync(
        session, pre.character, pre.service_id, user_message.strip(), "voice"
    )
    if not prompt:
        t_reply = time.perf_counter()
        gen = await _quest_compute_gen_dict(session, user_message, "voice", pre)
        reply_ms = (time.perf_counter() - t_reply) * 1000.0
        return await _quest_turn_finalize(session, user_message, "voice", pre, gen, t_turn0, reply_ms)

    max_out = QUEST_GEMINI_MAX_OUTPUT_VOICE

    def stream_factory() -> AsyncIterator[str]:
        return _llm_system_only_stream(session, prompt, max_tokens=max_out)

    async def finalize(raw_reply_full: str, reply_ms: float) -> QuestTurnResult:
        # If the streaming provider yields no usable text, do NOT advance the quest state off an empty
        # assistant message (that causes repeated questions next turn). Fall back to the normal
        # non-stream reply path for this same turn.
        if not (raw_reply_full or "").strip():
            gen = await _quest_compute_gen_dict(session, user_message, "voice", pre)
            return await _quest_turn_finalize(
                session, user_message, "voice", pre, gen, t_turn0, reply_ms, voice_streamed_main=False
            )
        gen = await _finalize_main_stream_raw_to_gen(session, user_message.strip(), "voice", raw_reply_full)
        return await _quest_turn_finalize(
            session, user_message, "voice", pre, gen, t_turn0, reply_ms, voice_streamed_main=True
        )

    return (stream_factory, finalize)


async def process_quest_turn(session: Session, user_message: str, channel: str) -> QuestTurnResult:
    """
    quest-characters `routes.ts` POST /questionnaires/:id/messages semantics
    (confirmation gate, extraction filter, agreed-to-call), plus web-style opening
    injection when the channel has no assistant yet (matches POST /questionnaires opener).
    """
    t_turn0 = time.perf_counter()
    service_id = ensure_quest_service(session)
    params = _get_quest_params(session)
    if session.summary_generated and is_coverage_satisfied(params, service_id):
        if not post_completion_user_requests_data_change(user_message):
            user_short_ack = bool(
                re.match(
                    r"^(ok|okay|k|yes|yeah|yep|sure|right|correct|that's right|that is right|exactly|thanks|thank you)\W*$",
                    (user_message or "").strip(),
                    re.I,
                )
            )
            reply = "Thanks — goodbye." if (channel == "voice" and user_short_ack) else _closing_append_signoff_warm_day(
                "Perfect — we already have everything. You're all set; "
                "the right PropFlow vendor will contact you shortly. 🙏"
            )
            if channel == "voice" and user_short_ack:
                session.voice_turn_requested_end_call = True
            session.add_message(MessageRole.ASSISTANT, reply)
            return QuestTurnResult(assistant_text=reply, completed=True, summary_generated=False)
    pre = await _quest_pre_reply_phases(session, user_message, channel)
    t_reply = time.perf_counter()
    gen = await _quest_compute_gen_dict(session, user_message, channel, pre)
    reply_ms = (time.perf_counter() - t_reply) * 1000.0
    return await _quest_turn_finalize(session, user_message, channel, pre, gen, t_turn0, reply_ms)
