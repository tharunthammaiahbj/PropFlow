"""
Aadhya – Conversation Controller (quest-parity questionnaire)

WhatsApp and Voice both route through the same quest-style engine:
- service-specific parameters (generated from quest-characters)
- extraction JSON + assistant/closing prompts (templates copied from quest-characters)

Lightweight guardrails remain here (off-topic, pricing, structural, commitment, callback).
"""
from __future__ import annotations

import re
import json
import time
from typing import Any

from backend.schemas.session import Session, MessageRole
from backend.config import get_settings
from backend.intelligence.llm_engine import get_llm_engine
from backend.questionnaire.conversation_engine import (
    QuestTurnResult,
    collect_pending_datapoints,
    apply_extracted_ts,
    prepare_voice_quest_stream_or_sync,
    process_quest_turn,
)
from backend.utils.logger import log_event
from backend.intelligence.persona import GUARDRAIL_REDIRECT, get_base_identity_by_persona_key
from backend.intelligence.router_engine import RouterEngine
from backend.intelligence.service_registry import QUEST_SERVICE_REGISTRY, ROUTER_TO_QUEST_ID

# ─── Guardrail detection keywords ────────────────────────────────────────────
# Fix #5: voice callers paraphrase identity questions in many ways. Substring
# matching means each entry is a phrase that must appear in the lowercased
# caller utterance. Keep entries tight (≥2 words) so that harmless user words
# like "bot" or "human" alone don't trigger the guardrail.
IDENTITY_KEYWORDS = [
    "who are you",
    "who is this",
    "who's this",
    "who am i talking",
    "who am i speaking",
    "are you a bot",
    "are you a human",
    "are you human",
    "are you real",
    "are you an ai",
    "is this a robot",
    "is this an ai",
    "is this a bot",
    "is this automated",
    "is this a real",
    "am i talking to",
    "am i talking with",
    "am i speaking to",
    "am i speaking with",
    "am i with a human",
    "what's your name",
    "whats your name",
    "what is your name",
    "tell me your name",
    "say your name",
    "your name again",
    "what company",
    "which company",
    "who do you work for",
    "what is propflow",
    "what's propflow",
    "what is tatva ops",
    "what is propflow",
    "what's propflow",
]

PRICING_KEYWORDS_SIMPLE = [
    "how much",
    "what is the cost",
    "cost of",
    "price",
    "rate",
    "quote",
    "charges",
    "fees",
    "kitna",
    # Fix #6 additions
    "total cost",
    "exact price",
    "cheapest",
    "lowest price",
    "budget option",
    "premium option",
    "ballpark",
    "ballpark figure",
]


# Opening turns in the quest engine store the ENTIRE assistant reply
# ("Hi! I'm <Name>, your <Role>. <Question>") into
# `session.extracted_fields["__quest:lastAsk"]["question"]`. When we later
# echo that value back as the transition tail of a domain answer or an
# off-topic redirect, the persona self-intro leaks out of its original turn
# and re-plays as:
#   "... Anyway, back to your project — Hi. I'm Claire Foster, your solar
#    services consultant. What type of solar installation ..."
# which is the exact production bug at 12:26:32 in the 2026-04-24 transcript.
# This helper trims any leading greeting / self-intro sentences so only the
# actual question survives. We loop because openings often stack two sentences
# back-to-back ("Hi. I'm Claire Foster, your solar services consultant. <Q>").
_LEADING_PERSONA_INTRO_RE = re.compile(
    r"^(?:Hi[!.,\s]|Hello[!.,\s]|Hey[!.,\s]|I['\u2019]m\s|I am\s|"
    r"This is\s|My name\s)[^.!?]*[.!?]\s+",
    re.IGNORECASE,
)


def _strip_persona_intro_from_question(last_q: str) -> str:
    """Drop any leading greeting / self-intro sentences from a stored last-ask."""
    s = (last_q or "").strip()
    if not s:
        return ""
    # Bounded loop: openings never stack more than 2–3 intro sentences.
    for _ in range(4):
        m = _LEADING_PERSONA_INTRO_RE.match(s)
        if not m:
            break
        s = s[m.end():].lstrip()
    return s.strip()


def _last_question_text(session: Session) -> str:
    meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    last_ask = meta.get("__quest:lastAsk")
    if not isinstance(last_ask, dict):
        return ""
    raw = str(last_ask.get("question") or "")
    # Defense-in-depth for the "Got it. the roof type?" leak in prod:
    # if any acknowledgement snuck into storage (e.g. from an older session
    # created before ack-dedup shipped), strip it before we re-attach the
    # last question to a domain-answer / off-topic redirect / summary reply.
    # Otherwise the caller hears "Anyway, back to your project — Got it.
    # the roof type?" with broken grammar.
    try:
        from backend.agents.voice.voice_response_optimizer import strip_leading_ack
        raw = strip_leading_ack(raw)
    except Exception:  # noqa: BLE001
        pass
    return _strip_persona_intro_from_question(raw)


def _current_service_id(session: Session) -> str:
    meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    sid = meta.get("__quest:service_id")
    return str(sid).strip() if isinstance(sid, str) else ""


def _service_display_name(service_id: str) -> str:
    manifest = QUEST_SERVICE_REGISTRY.get(service_id) or {}
    return str(manifest.get("webhook_service_name") or service_id.replace("_", " ")).strip() or "PropFlow service"


def _is_likely_quest_answer(msg: str) -> bool:
    """
    Skip classifier when the message is a short, non-question-like answer.
    True when: <= 4 words AND contains none of the question indicators.
    """
    s = " ".join((msg or "").strip().lower().split())
    if not s:
        return False
    if len(s.split()) > 4:
        return False

    padded = f" {s} "
    indicators = (
        "?",
        " who ",
        " what ",
        " why ",
        " how ",
        " when ",
        " which ",
        " can you",
        " do you",
        " is it",
        " tell me",
        " explain",
        " meaning",
        " difference",
        " better",
        " recommend",
        " suggest",
    )
    return not any(ind in padded for ind in indicators)


# Unambiguous "I want an explanation" phrases. When any of these appear we skip the
# LLM classifier and route straight to PATH 2 (DOMAIN_QUESTION). Saves ~150ms and
# never misclassifies these as a quest answer.
_DOMAIN_QUESTION_TRIGGERS = (
    "what do you mean",
    "what does that mean",
    "what does it mean",
    "what does ",
    "what is ",
    "what's ",
    "whats ",
    "what are ",
    "tell me what",
    "explain ",
    "explain it",
    "can you explain",
    "could you explain",
    "never heard",
    "don't understand",
    "dont understand",
    "do not understand",
    "i don't know what",
    "i dont know what",
    "what's the difference",
    "whats the difference",
    "difference between",
    "which is better",
    "what would you recommend",
    "what do you recommend",
    "any suggestion",
    "any suggestions",
    "give me an example",
    "for example?",
    "like what",
    "like?",
    "such as?",
    "meaning of",
    "by ground mount",
    "by on grid",
    "by off grid",
    "by hybrid",
    # Explicit "ask the agent for advice" phrases. These are clearly a request
    # for the consultant's opinion, not a quest answer. Bare "suggest" /
    # "recommendation" are intentionally NOT in this list — callers volunteer
    # "I suggest on-grid" as a QUEST_ANSWER and substring match would steal
    # those turns. The tighter variants below only fire when the caller is
    # clearly deferring the decision to us.
    "you tell me",
    "give me a suggestion",
    "give me a recommendation",
    "what would you suggest",
    "help me decide",
    "help me choose",
    "any idea",
    "any recommendation",
    "your suggestion",
    "your recommendation",
)


def _looks_like_domain_question(msg: str) -> bool:
    """Cheap, deterministic detector for explicit clarification questions."""
    s = " ".join((msg or "").strip().lower().split())
    if not s:
        return False
    # Single-word "huh?" / "what?" / "explain?" -> domain question.
    if s.rstrip("?.! ") in ("what", "huh", "sorry", "explain", "meaning", "pardon", "come again"):
        return True
    return any(trig in s for trig in _DOMAIN_QUESTION_TRIGGERS)


_ORDINAL_PATTERNS = [
    re.compile(r"\b(first|one|1st|it one|ek|first one)\b", re.I),
    re.compile(r"\b(second|two|2nd|second one|do)\b", re.I),
    re.compile(r"\b(third|three|3rd|third one|teen)\b", re.I),
]
_ORDINAL_EXPLAIN_RE = re.compile(
    r"\b(what (is|does|do you mean by)|tell me (about|what)|explain|means?)\b.*"
    r"\b(first|second|third|one|two|three|1st|2nd|3rd|it one)\b",
    re.I,
)


def _looks_like_ordinal_option_request(msg: str) -> bool:
    return bool(_ORDINAL_EXPLAIN_RE.search(msg or ""))


def _resolve_ordinal_to_option(msg: str, options: list[str]) -> str | None:
    m = (msg or "").lower()
    if any(p in m for p in ["first", "1st", "one", "it one", "ek"]):
        return options[0] if options else None
    if any(p in m for p in ["second", "2nd", "two", "do"]):
        return options[1] if len(options) > 1 else None
    if any(p in m for p in ["third", "3rd", "three", "teen"]):
        return options[2] if len(options) > 2 else None
    return None


def _extract_offered_options(last_question: str) -> list[str]:
    q = (last_question or "").lower()
    q = re.sub(r"[^a-z0-9\\s]", " ", q)
    q = re.sub(r"\\s+", " ", q).strip()
    known_multi = [
        "ground mount",
        "residential rooftop",
        "metal sheet",
        "flat rcc",
        "on grid",
        "off grid",
        "hybrid with battery",
    ]
    found: list[str] = []

    def add(opt: str) -> None:
        if opt and opt not in found:
            found.append(opt)

    for opt in known_multi:
        if opt in q:
            add(opt)
    return found


# Warm, slightly self-deprecating off-topic redirects keyed by service id. We pick the
# matching one so a solar consultant deflects differently from an interiors one. This
# replaces the old robotic "That is a bit outside what I can help with right now…" line.
_WARM_OFFTOPIC_BY_SERVICE: dict[str, str] = {
    "solar_services":
        "Ha, I wish I could help with that — I'm only really good at solar!",
    "residential_interiors":
        "Ha, that one's outside my world — I'm strictly an interiors person!",
    "commercial_interiors":
        "Ha, can't help you there — I only know commercial interiors!",
    "modular_kitchen":
        "Ha, that's not my thing — I just live and breathe kitchens!",
    "wardrobes":
        "Ha, that's outside my lane — I only know wardrobes!",
    "false_ceiling":
        "Ha, that's not my area — I only do ceilings!",
    "painting_services":
        "Ha, I wish I knew — I only do paint!",
    "flooring":
        "Ha, that's beyond me — I only know flooring!",
    "electrical":
        "Ha, can't help with that — I'm an electrical guy through and through!",
    "plumbing":
        "Ha, not my expertise — I only know plumbing!",
    "carpentry":
        "Ha, that's outside my workshop — I only do carpentry!",
    "civil_construction":
        "Ha, that's a different world — I only do civil work!",
    "renovation":
        "Ha, way outside my zone — I only handle renovations!",
}
_DEFAULT_WARM_OFFTOPIC_PREFIX = "Ha, I wish I knew — I'm only really good at this right now!"

# ─── Fix #4: transition phrase rotation ──────────────────────────────────────
_TRANSITION_PHRASES = [
    "Anyway, back to your project.",
    "Alright, on your project —",
    "Coming back to your home —",
    "Right, where we left off —",
    "Okay — where we were:",
    "So, on your project:",
    "Back to where we were —",
]
_VOICE_LAST_TRANSITION_KEY = "__voice:lastTransition"
_VOICE_LAST_TRANSITION_INDEX_KEY = "__voice:lastTransitionIndex"
_VOICE_PREV_TRANSITION_INDEX_KEY = "__voice:prevTransitionIndex"


def _next_transition_phrase(session: Session) -> str:
    meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
        session.extracted_fields = meta
    n = len(_TRANSITION_PHRASES)
    try:
        last_i = int(meta.get(_VOICE_LAST_TRANSITION_INDEX_KEY))
    except Exception:
        last_i = -1
    try:
        prev_i = int(meta.get(_VOICE_PREV_TRANSITION_INDEX_KEY))
    except Exception:
        prev_i = -1
    next_i = (last_i + 1) % n
    # Never repeat the same transition within 2 turns: avoid prev_i if it would repeat.
    if n >= 3 and next_i == prev_i:
        next_i = (next_i + 1) % n
    phrase = _TRANSITION_PHRASES[next_i]
    meta[_VOICE_PREV_TRANSITION_INDEX_KEY] = last_i
    meta[_VOICE_LAST_TRANSITION_INDEX_KEY] = next_i
    meta[_VOICE_LAST_TRANSITION_KEY] = phrase
    session.extracted_fields = meta
    return phrase


def _warm_offtopic_redirect(session: Session, service_id: str, last_question: str) -> str:
    """Build a warm, in-character off-topic deflection ending with the last question."""
    prefix = _WARM_OFFTOPIC_BY_SERVICE.get((service_id or "").strip(), _DEFAULT_WARM_OFFTOPIC_PREFIX)
    tail = (last_question or "where were we?").strip()
    transition = _next_transition_phrase(session)
    # Ensure clean spacing no matter how the transition ends ('.', '—', ':').
    return f"{prefix} {transition} {tail}".strip()


# ─── Fix #8: summary-request handler ────────────────────────────────────────
# Callers often pause mid-brief to ask "what did you capture so far?" /
# "summarize what we have". Before Fix #8 this went to the classifier which
# either (a) routed as DOMAIN_QUESTION (generic hallucinated answer) or (b)
# routed as QUEST_ANSWER (extraction failed, question re-asked). Either was
# wrong. We add a deterministic shortcut: read the captured params out loud,
# then re-anchor to the last question so the flow stays unbroken.
_SUMMARY_REQUEST_TRIGGERS = (
    "what did you capture",
    "what have you captured",
    "what do we have",
    "what do you have so far",
    "what have i told you",
    "what have i said",
    "summarize",
    "summary so far",
    "recap",
    "quick recap",
    "tell me what you have",
    "tell me what we have",
    "what have you got",
    "what have we covered",
    "read it back",
    "read that back",
    "repeat what i said",
)

# Labels used for the spoken read-back. Same ids as the quest datapoints,
# keyed here so the controller doesn't need to import the quest engine's
# service-params dict. Unknown ids fall back to `id.replace("_"," ")`.
_SUMMARY_FIELD_LABELS: dict[str, str] = {
    "project_type": "home type",
    "rooms": "BHK",
    "size_sqft": "carpet area",
    "plot_size_sqft": "plot size",
    "style": "style",
    "preferred_start": "start",
    "budget": "budget",
    "timeline": "timeline",
    "contact_pref": "contact preference",
    "callback_time": "callback time",
    "capacity_kw": "capacity",
    "roof_type": "roof type",
    "monthly_units": "monthly usage",
    "grid_type": "grid type",
    "orientation": "orientation",
    "city": "city",
    "painting_scope": "painting scope",
    "paint_finish": "finish",
}


def _looks_like_summary_request(msg: str) -> bool:
    """True when the caller is asking us to read back what was captured."""
    s = " ".join((msg or "").strip().lower().split())
    if not s:
        return False
    return any(trig in s for trig in _SUMMARY_REQUEST_TRIGGERS)


# Suggestion requests ("you tell me", "suggest", "help me decide") should NOT
# be treated as domain questions when we are mid-questionnaire and there is an
# active askedParam. In that case the user is asking for a recommendation for
# the *current field* (e.g. capacity_kw), and the quest engine should handle it.
_SUGGESTION_REQUEST_TRIGGERS = (
    "you tell me",
    "you decide",
    "you choose",
    "your call",
    "up to you",
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


def _looks_like_suggestion_request(msg: str) -> bool:
    s = " ".join((msg or "").strip().lower().split())
    if not s:
        return False
    return any(trig in s for trig in _SUGGESTION_REQUEST_TRIGGERS)


def _summarize_captured_params(session: Session) -> str:
    """Return a short spoken digest of captured parameters (max 5 fields)."""
    meta = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
    params_raw = meta.get("__quest:parameters") if isinstance(meta, dict) else None
    params: dict[str, Any] = params_raw if isinstance(params_raw, dict) else {}
    bits: list[str] = []
    for fid, entry in params.items():
        if not isinstance(entry, dict):
            continue
        val = entry.get("value")
        if val is None:
            continue
        sv = str(val).strip()
        if not sv or sv.lower() in ("none", "null", "not specified"):
            continue
        label = _SUMMARY_FIELD_LABELS.get(fid) or fid.replace("_", " ")
        bits.append(f"{label} {sv}")
        if len(bits) >= 5:
            break
    if not bits:
        return "We haven't locked anything in yet — let's keep going."
    return "Here's what I have so far — " + "; ".join(bits) + "."


def _build_summary_reply(session: Session, last_question: str) -> str:
    """Spoken digest + deterministic transition back to the last question."""
    digest = _summarize_captured_params(session)
    last_q = (last_question or "").strip()
    if not last_q:
        return digest
    transition = _next_transition_phrase(session)
    return f"{digest} {transition} {last_q}".strip()


def _build_domain_history(session: Session, *, max_messages: int = 4) -> list[dict]:
    """
    Build OpenAI-style history for the LLM router: [{'role': 'user'|'assistant', 'content': '...'}]
    """
    hist = session.conversation_history[-max_messages:] if session.conversation_history else []
    out: list[dict] = []
    for m in hist:
        role = getattr(m, "role", None)
        role_val = getattr(role, "value", str(role))
        if role_val not in ("user", "assistant"):
            continue
        out.append({"role": role_val, "content": str(getattr(m, "content", "") or "")})
    return out


async def _classify_voice_path(
    *,
    session: Session,
    service_name: str,
    last_question: str,
    user_message: str,
) -> str:
    """
    Return exactly one of: QUEST_ANSWER | DOMAIN_QUESTION | OFF_TOPIC
    Falls back to QUEST_ANSWER on failure/empty/unexpected.
    """
    # Anchored output: model must end with `LABEL=<one of three>`. This survives leading
    # whitespace/newlines and partial truncation under tight token caps far better than
    # asking for "one word" and hoping.
    system_prompt = (
        f"You are a classifier for a voice agent handling {service_name} consultations.\n"
        f"The agent just asked: {last_question}\n\n"
        "Classify the user message into exactly one category:\n"
        "- QUEST_ANSWER: user is answering the questionnaire question or providing project information\n"
        f"- DOMAIN_QUESTION: user is asking about {service_name}, materials, processes, timelines, "
        "recommendations, what was captured, who they are speaking to, or anything related to PropFlow\n"
        "- OFF_TOPIC: user is asking about something completely unrelated like cricket, politics, weather, food, "
        "other industries\n\n"
        "Reply with EXACTLY one line in this format and nothing else:\n"
        "LABEL=QUEST_ANSWER\n"
        "or\n"
        "LABEL=DOMAIN_QUESTION\n"
        "or\n"
        "LABEL=OFF_TOPIC"
    )
    try:
        raw = await get_llm_engine().chat(
            session_id=f"{session.session_id}:path_classifier",
            user_message=user_message,
            system_prompt=system_prompt,
            history=[],
            temperature=0.0,
            # Why 64 (not 24): gpt-oss-20b on Groq is a reasoning model. Even with
            # `reasoning_effort=low`, the hidden chain-of-thought token count varies
            # per turn — production logs showed ~40% of turns still burning the entire
            # 24-token budget on internal thinking and returning `content=""` (visible
            # as CLASSIFIER_UNEXPECTED raw=''). 64 absorbs the worst-case thinking
            # variance so the model always has enough headroom to emit the full
            # `LABEL=DOMAIN_QUESTION` (~10 sub-tokens) after it finishes reasoning.
            # Extra latency vs 24: negligible — streaming stops at the label anyway.
            max_tokens=64,
        )
    except Exception as e:  # noqa: BLE001
        await log_event(
            "CLASSIFIER_ERROR",
            session_id=session.session_id,
            data={"error": str(e)[:200]},
        )
        return "QUEST_ANSWER"

    raw_str = str(raw or "")
    # Always log the raw response (preserving whitespace/newlines via repr) so we can
    # diagnose any future classifier flakiness without guessing.
    await log_event(
        "CLASSIFIER_RAW",
        session_id=session.session_id,
        data={"raw_repr": repr(raw_str)[:200], "len": len(raw_str)},
    )

    # Primary parse: look for `LABEL=<word>` anywhere in the response (handles leading
    # whitespace, code fences, stray quotes).
    label: str | None = None
    m = re.search(r"LABEL\s*=\s*([A-Z_]+)", raw_str.upper())
    if m:
        candidate = m.group(1)
        if candidate in ("QUEST_ANSWER", "DOMAIN_QUESTION", "OFF_TOPIC"):
            label = candidate

    # Secondary parse: bare token (legacy behaviour, still useful when the model
    # ignores the LABEL= contract but emits the right word).
    if label is None:
        token = raw_str.strip().upper().replace("LABEL=", "").strip()
        # First whitespace-separated chunk only.
        token = token.split()[0] if token else ""
        token = token.rstrip(".,;:!?")
        if token in ("QUEST_ANSWER", "DOMAIN_QUESTION", "OFF_TOPIC"):
            label = token

    # Tertiary fuzzy parse: the model produced something verbose like
    # "This looks like a domain question." — recover the intent rather than
    # silently defaulting to QUEST_ANSWER (which loses the routing decision).
    if label is None:
        upper = raw_str.upper()
        if "DOMAIN" in upper:
            label = "DOMAIN_QUESTION"
        elif "OFF_TOPIC" in upper or "OFF TOPIC" in upper or "OFFTOPIC" in upper:
            label = "OFF_TOPIC"
        elif "QUEST" in upper or "ANSWER" in upper:
            label = "QUEST_ANSWER"

    if label is None:
        await log_event(
            "CLASSIFIER_UNEXPECTED",
            session_id=session.session_id,
            data={"raw": raw_str[:80], "raw_repr": repr(raw_str)[:120]},
        )
        return "QUEST_ANSWER"
    return label


_DOMAIN_TRAILING_TRANSITION_RE = re.compile(
    r"\s*(?:Anyway[,\s]+|So[,\s]+|Now[,\s]+)?back\s+to\s+your\s+(?:project|question|brief|quote)[\s\S]*$",
    re.IGNORECASE,
)

_DOMAIN_TRAILING_INTRO_RE = re.compile(
    # Fires only when a NEW sentence (post period/!/?) begins with a greeting/
    # self-intro token — that's the exact failure mode from production logs
    # ("... the best tilt and orientation. Hi. I'm Kavyanir. Your?"). We trim
    # from the sentence break onwards so the legitimate explanation is kept.
    r"[.!?]\s+(?:Hi[!.,\s]|Hello[!.,\s]|Hey[!.,\s]|I['\u2019]m\s|I am\s|"
    r"This is\s|My name\s|Your\??\s*$)[\s\S]*$",
    re.IGNORECASE,
)

_DOMAIN_MARKDOWN_RE = re.compile(r"(\*\*|`{1,3}|_{2,}|#{1,6}\s|^-|\n-|\n\d+\.)")
_DOMAIN_BAD_TAIL_RE = re.compile(r"(?:\b(?:an|on)\b\s*)\*\*$", re.I)
_DOMAIN_BAD_SHORT_RE = re.compile(r"^(certainly\.?|sure\.?|okay\.?)\s*$", re.I)


def _clean_domain_answer_text(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    t = t.replace("**", "")
    t = t.replace("`", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _domain_answer_is_unusable(body: str) -> bool:
    b = (body or "").strip()
    if not b:
        return True
    if len(b) < 12 or _DOMAIN_BAD_SHORT_RE.match(b):
        return True
    if _DOMAIN_MARKDOWN_RE.search(b):
        return True
    if _DOMAIN_BAD_TAIL_RE.search(b):
        return True
    return False


async def _answer_domain_question(
    *,
    session: Session,
    service_name: str,
    last_question: str,
    user_message: str,
) -> str | None:
    """
    Answer a domain question with an expert explanation, then deterministically
    append the transition back to the last questionnaire question.

    Why the transition is now Python-appended instead of LLM-generated
    (was Problem #9 in voice logs):
    Under a tight `max_tokens` cap gpt-oss-20b would exhaust its budget on the
    35-word explanation plus hidden chain-of-thought tokens and fabricate a
    garbled persona intro at the tail ("Hi. I'm Kavyanir. Your?") instead of
    echoing the literal transition string. By writing the transition in Python
    we guarantee the caller hears exactly "Anyway, back to your project — ..."
    every single time, even when the LLM truncates or misbehaves.

    Returns None on LLM failure so the caller falls back to the quest engine.
    """
    persona = get_base_identity_by_persona_key(getattr(session, "persona_key", None))
    system_prompt = (
        f"{persona}\n\n"
        f"You are answering a caller's question during a {service_name} consultation.\n"
        "Answer the question naturally and expertly in UNDER 35 words.\n"
        "Output MUST be plain text only.\n"
        "DO NOT use markdown (no **bold**, no bullets, no headings, no backticks).\n"
        "Do NOT greet. Do NOT introduce yourself. Do NOT add transitions.\n"
        "Output ONLY the explanation sentence(s).\n"
    )

    async def _call_domain_llm(max_tokens: int) -> str:
        return await get_llm_engine().chat(
            session_id=f"{session.session_id}:domain_answer",
            user_message=user_message,
            system_prompt=system_prompt,
            history=_build_domain_history(session, max_messages=4),
            temperature=0.2,
            max_tokens=max_tokens,
        )

    try:
        txt = await _call_domain_llm(max_tokens=220)
    except Exception as e:  # noqa: BLE001
        await log_event(
            "DOMAIN_RESPONSE_ERROR",
            session_id=session.session_id,
            data={"error": str(e)[:200]},
        )
        return None

    body = _clean_domain_answer_text(str(txt or ""))

    # Defensive cleanup — if the model ignored the "no transition" instruction
    # and tacked one on anyway, strip it so we don't emit a double transition.
    body = _DOMAIN_TRAILING_TRANSITION_RE.sub("", body).strip()

    # Strip any hallucinated trailing persona intro (the exact production bug).
    m = _DOMAIN_TRAILING_INTRO_RE.search(body)
    if m:
        # Keep the sentence terminator (`.`, `!`, `?`) that immediately precedes
        # the hallucinated intro, drop everything from the whitespace after it.
        body = body[: m.start() + 1].strip()

    if _domain_answer_is_unusable(body):
        try:
            txt2 = await _call_domain_llm(max_tokens=320)
        except Exception:
            return None
        body2 = _clean_domain_answer_text(str(txt2 or ""))
        body2 = _DOMAIN_TRAILING_TRANSITION_RE.sub("", body2).strip()
        m2 = _DOMAIN_TRAILING_INTRO_RE.search(body2)
        if m2:
            body2 = body2[: m2.start() + 1].strip()
        if _domain_answer_is_unusable(body2):
            return None
        body = body2

    # Guarantee terminal punctuation so the deterministic suffix reads cleanly.
    if body[-1] not in ".!?":
        body += "."

    last_q = (last_question or "").strip()
    if not last_q:
        return body
    transition = _next_transition_phrase(session)
    return f"{body} {transition} {last_q}".strip()

def _looks_like_identity_question(msg: str) -> bool:
    lower = (msg or "").lower()
    return any(k in lower for k in IDENTITY_KEYWORDS)


def _looks_like_pricing_question(msg: str) -> bool:
    lower = (msg or "").lower()
    return any(k in lower for k in PRICING_KEYWORDS_SIMPLE)


# ─── Guardrail keyword lists ─────────────────────────────────────────────────
# Fix #6: broaden the routing lists so the LLM classifier is bypassed more
# often for obvious cases (cheaper + faster + more deterministic). These are
# substring-matched against lowercased user text, so entries with ≥2 words are
# preferred to avoid collateral damage (e.g. "news" alone would be too broad).
_FRICTION_PATTERNS = [
    re.compile(r"\b(are you (there|listening)|can you hear me|hello\??)\b", re.I),
    re.compile(r"\b(not listening|you are not listening|not hearing|did you hear)\b", re.I),
    re.compile(r"\b(why (are you )?(repeating|asking again)|stop (asking|repeating))\b", re.I),
    re.compile(r"\b(robot|are you a bot)\b", re.I),
    re.compile(r"\b(repeat what i said|say that again)\b", re.I),
    re.compile(r"\bhow about you\b", re.I),
]


def _is_friction_complaint(msg: str) -> bool:
    s = (msg or "").strip()
    if not s:
        return False
    return any(p.search(s) for p in _FRICTION_PATTERNS)

OFF_TOPIC_KEYWORDS = [
    "stock", "crypto", "bitcoin", "recipe", "weather", "cricket", "movie",
    "exam", "job", "salary", "politics", "news", "visa", "marriage",
    "football", "election", "neet", "jee", "upsc", "dating", "tinder",
    # Fix #6 additions — common voice off-topic patterns we saw or anticipate
    "ipl", "t20", "world cup", "match today", "who won",
    "stocks", "share price", "gold price", "silver price",
    "rupee to dollar", "dollar rate", "currency rate",
    "vacation", "holiday plan", "travel plan",
    "song", "music",
    "recipe for", "cooking",
    "weather today", "rain today",
    "horoscope", "astrology",
]

PRICING_KEYWORDS = [
    "how much", "kitna", "price", "cost", "rate", "charges", "per sqft",
    "per square foot", "quote", "estimate", "quotation", "rupee", "rupees",
    "lakh", "lakhs", "budget breakdown", "total cost", "exact price",
    "final price", "billing", "invoice",
    # Fix #6 additions
    "cheapest", "lowest price", "ballpark", "ballpark figure",
    "roughly how much", "around how much", "approximate cost",
]

STRUCTURAL_KEYWORDS = [
    "break wall", "remove wall", "load bearing", "structural change",
    "add floor", "extra floor", "demolish", "knock down wall",
    "plumbing riser", "move bathroom", "extend balcony", "build room",
]

COMMITMENT_KEYWORDS = [
    "guarantee", "promise", "how many days", "when will it be done",
    "delivery date", "completion date", "timeline", "deadline", "discount",
    "offer", "free", "complimentary", "how long will it take",
]

CALLBACK_SIGNALS = [
    "i'll discuss with", "let me talk to my", "will get back",
    "need to check with", "call me later", "i'll think about it",
    "not right now", "maybe later", "let me consult",
    # Fix #6 additions — common voice "I need to go" signals
    "i have to go", "gotta go", "gotta run", "need to go",
    "in a meeting", "driving right now", "driving now",
    "busy right now", "busy now", "catch you later",
    "call me back", "call back later",
]


def _is_off_topic(msg: str) -> bool:
    return any(kw in msg.lower() for kw in OFF_TOPIC_KEYWORDS)


def _is_asking_price(msg: str) -> bool:
    return any(kw in msg.lower() for kw in PRICING_KEYWORDS)


def _is_asking_structural(msg: str) -> bool:
    return any(kw in msg.lower() for kw in STRUCTURAL_KEYWORDS)


def _is_asking_commitment(msg: str) -> bool:
    return any(kw in msg.lower() for kw in COMMITMENT_KEYWORDS)


def _wants_callback(msg: str) -> bool:
    return any(kw in msg.lower() for kw in CALLBACK_SIGNALS)


def _has_budget_anxiety(msg: str) -> bool:
    words = [
        "expensive", "too much", "can't afford", "tight budget",
        "very low", "no money", "costly", "cheap", "worried about cost",
    ]
    return any(w in msg.lower() for w in words)


def _build_guardrail_hints(user_message: str) -> list[str]:
    hints: list[str] = []
    if _wants_callback(user_message):
        hints.append(
            "The client wants to end the conversation. Do NOT ask more questions. "
            "Warmly acknowledge, summarize what you've collected, and let them know "
            "the PropFlow team will follow up."
        )
    if _is_asking_price(user_message):
        hints.append(
            "The client is asking about pricing. Do NOT quote exact prices. "
            "Give very broad ranges if pressed and defer to the project manager."
        )
    if _is_asking_structural(user_message):
        hints.append(
            "The client is asking about structural changes. Stay within interior scope. "
            "Say the design team would need to assess feasibility."
        )
    if _is_asking_commitment(user_message):
        hints.append(
            "The client is asking for timelines or guarantees. "
            "Do NOT make commitments. Defer to the project manager."
        )
    if _has_budget_anxiety(user_message):
        hints.append(
            "The client is expressing budget anxiety. Be reassuring: "
            "elegance doesn't require extravagance. Mention smart material choices."
        )
    return hints


class AgentResponse:
    def __init__(
        self,
        text: str,
        session: Session,
        summary_generated: bool = False,
        completed: bool = False,
    ):
        self.text = text
        self.session = session
        self.summary_generated = summary_generated
        self.completed = completed


class ConversationController:
    def __init__(self):
        # Phase 1: voice-only routing via quest service IDs.
        self.router_engine = RouterEngine()

    async def process_message(
        self,
        session: Session,
        user_message: str,
        channel: str = "whatsapp",
    ) -> AgentResponse:
        await log_event(
            "USER_MESSAGE",
            session_id=session.session_id,
            data={"message": user_message, "stage": session.conversation_stage},
        )

        session.add_message(MessageRole.USER, user_message)

        # ── ROUTING HOOK ─────────────────────────────────────────────────────
        # Voice: always route on first turn.
        # WhatsApp: if the service isn't already fixed (service_code or __quest:service_id),
        # behave like Priya and ask for the service bucket first (do not default-lock).
        ch = (channel or "").strip().lower()
        extracted = session.extracted_fields if isinstance(session.extracted_fields, dict) else {}
        session.extracted_fields = extracted
        has_service_id = bool(extracted.get("__quest:service_id")) or bool(getattr(session, "service_code", None))

        if ch == "voice":
            await self.router_engine.route(user_message, channel="voice", session=session)
        elif ch == "whatsapp":
            # WhatsApp should behave like Retell: deterministic stages (like nodes),
            # with ALL wording generated by the LLM (no static sentences).
            #
            # Stages:
            # - PRIYA_SERVICE_PICK -> identify service (or ask 1 clarify question)
            # - PRIYA_OTHER_VENDORS -> ask "reached out to other vendors?"
            # - PRIYA_HEAR_ABOUT -> ask "how did you hear about PropFlow?"
            # - PRIYA_CONNECT_CONFIRM -> ask yes/no to connect
            # - SPECIALIST_WELCOME -> specialist intro + 1 first question
            # - SPECIALIST_ACTIVE -> quest engine takes over

            JESSICA_GP = str(extracted.get("__wa:jessica_gp") or "").strip() or (
                "You are Jessica, the front-desk voice receptionist for PropFlow (home services: interiors, construction, "
                "painting, solar, plumbing, electrical, home automation).\n"
                "Prime directive: respond like a real human receptionist, acknowledge, then steer toward (1) service line "
                "and (2) connect to the right specialist. Never sound scripted.\n"
                "Language: match English/Hindi/Kannada, code-mix ok. No sir/ma'am/bhai/didi.\n"
                "Never ask for phone number, callback time, or schedule a visit.\n"
                "Ask ONE question per message.\n"
            )

            # Reused on every Priya turn after the opener: no repeated “Hi there” mid-flow.
            JESSICA_ONGOING_TONE = (
                "The conversation is already in progress. Do not open with a greeting "
                "(no Hi, Hello, Hey there, Good morning). Be concise and professional; go straight to the point.\n"
            )

            stage = str(extracted.get("__wa:stage") or "PRIYA_SERVICE_PICK").strip()
            svc_bucket = str(extracted.get("__wa:service_bucket") or "").strip().lower()

            allowed_services = [
                "interiors",
                "construction",
                "painting",
                "solar",
                "plumbing",
                "electrical",
                "home automation",
            ]
            service_to_router_code = {
                "interiors": "interior_design",
                "construction": "construction",
                "painting": "painting",
                "solar": "solar_rooftop",
                "plumbing": "plumbing",
                "electrical": "electrical",
                "home automation": "home_automation",
            }

            def _expert_first_name_for_persona() -> str:
                base = get_base_identity_by_persona_key(getattr(session, "persona_key", None))
                # Persona base identities typically start with "You are <First> <Last>...".
                # We also support "I'm <First>" / "this is <First>" patterns.
                m = re.search(r"\byou are\s+([A-Za-z]+)\b", (base or ""), re.I) or re.search(
                    r"\b(?:this is|i['\u2019]?m)\s+([A-Za-z]+)\b",
                    (base or ""),
                    re.I,
                )
                return m.group(1).strip() if m else ""

            def _coerce_bool(v: Any) -> bool | None:
                """
                Normalize JSON-ish booleans the model may emit (string "true", punctuation, etc.).
                Output sanitation only — not user-intent routing.
                """
                if v is True:
                    return True
                if v is False:
                    return False
                if isinstance(v, (int, float)) and v in (0, 1):
                    return bool(v)
                if isinstance(v, str):
                    s = v.strip().lower()
                    if re.search(r"\b(true|yes|y|yeah|yep|sure|ok|okay|do it|go ahead|connect)\b", s):
                        return True
                    if re.search(r"\b(false|no|n|nope|not now|wait)\b", s):
                        return False
                    compact = re.sub(r"[^a-z]", "", s)
                    if compact in ("true", "yes", "y", "yeah", "yep", "sure", "ok", "okay"):
                        return True
                    if compact in ("false", "no", "n", "nope"):
                        return False
                return None

            def _looks_like_affirmative(text: str) -> bool:
                s = " ".join((text or "").strip().lower().split())
                if not s:
                    return False
                # Deterministic loop-breaker only: if user clearly agrees, transfer without re-asking.
                return bool(
                    re.search(
                        r"\b("
                        r"yes|yep|yeah|ya|sure|ok|okay|pls|please|do it|go ahead|connect|proceed|put me through|"
                        r"haan|haanji|han|ha|ji|theek|thik|chalo|karo|"
                        r"howdu|sari|seri|aaytu|aytu|maadi|madri|"
                        r")\b",
                        s,
                    )
                )

            def _looks_like_negative(text: str) -> bool:
                s = " ".join((text or "").strip().lower().split())
                if not s:
                    return False
                return bool(
                    re.search(
                        r"\b("
                        r"no|nope|nah|not now|dont|don't|do not|wait|later|hold on|stop|cancel|"
                        r"nahi|na|mat|ruk|abhi nahi|"
                        r"illa|beda|bekilla|ill|"
                        r")\b",
                        s,
                    )
                )

            def _tag_service(bucket: str) -> None:
                rc = service_to_router_code.get(bucket)
                qid = ROUTER_TO_QUEST_ID.get(rc or "", "")
                if qid:
                    extracted["__quest:service_id"] = qid
                    extracted["__router:service_id"] = qid
                    manifest = QUEST_SERVICE_REGISTRY.get(qid) or {}
                    pk = str(manifest.get("persona_key") or "").strip()
                    if pk:
                        session.persona_key = pk

            async def _llm_json(prompt: str) -> dict[str, Any]:
                # Primary: provider JSON-mode extraction.
                try:
                    out = await get_llm_engine().extract_json(session_id=session.session_id, extraction_prompt=prompt)
                    if isinstance(out, dict) and out:
                        return out
                except Exception:
                    pass

                # Fallback: plain chat returning JSON text, then parse locally.
                try:
                    raw = await get_llm_engine().chat(
                        session_id=session.session_id,
                        user_message="Return the JSON object now.",
                        system_prompt=prompt + "\n\nReturn ONLY valid JSON.",
                        history=[],
                        temperature=0.2,
                        max_tokens=256,
                    )
                    parsed = json.loads((raw or "").strip())
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}

            def _quest_parameters_dict() -> dict[str, Any]:
                params_raw = extracted.get("__quest:parameters") if isinstance(extracted, dict) else None
                return params_raw if isinstance(params_raw, dict) else {}

            async def _capture_prefill_from_user_message(service_id: str) -> None:
                """
                Lightweight Priya-phase capture: store any volunteered project facts early
                so the specialist doesn't re-ask them after transfer.
                """
                try:
                    if not (user_message or "").strip():
                        return
                    params = _quest_parameters_dict()
                    pending = collect_pending_datapoints(service_id, params)
                    if not pending:
                        return
                    allowed_ids = [p.get("id") for p in pending if isinstance(p, dict) and p.get("id")]
                    if not allowed_ids:
                        return
                    # Include label/hint so the model maps values correctly (avoids guesses like
                    # project_type="painting", location="residential" from generic messages).
                    allowed_block = "\n".join(
                        f"- {p.get('id')}: {p.get('label') or ''}{(' — ' + p.get('hint')) if p.get('hint') else ''}"
                        for p in pending
                        if isinstance(p, dict) and p.get("id")
                    )
                    prompt = (
                        "Extract structured project facts from the user's message. Return STRICT JSON only.\n"
                        "Extract ANY of the allowed fields the user provided (even if not asked yet).\n"
                        f"Allowed fields:\n{allowed_block}\n\n"
                        f"User message:\n{user_message!r}\n"
                    )
                    out = await get_llm_engine().extract_json(
                        session_id=f"{session.session_id}:wa_priya_prefill_capture",
                        extraction_prompt=prompt,
                    )
                    if not isinstance(out, dict) or not out:
                        return
                    normalized: dict[str, dict[str, Any]] = {}
                    for k, v in out.items():
                        if k not in allowed_ids:
                            continue
                        if isinstance(v, dict) and "value" in v:
                            normalized[k] = v
                        else:
                            normalized[k] = {"value": v, "confidence": 0.85}
                    if not normalized:
                        return
                    notes_raw = extracted.get("__wa:prefill_notes")
                    notes: dict[str, Any] = notes_raw if isinstance(notes_raw, dict) else {}
                    # Merge (latest wins).
                    for k, v in normalized.items():
                        notes[k] = v
                    extracted["__wa:prefill_notes"] = notes
                except Exception:
                    return

            async def _prefill_params_from_history(service_id: str) -> None:
                """
                One-time handoff extraction: capture any project facts the user already said during
                Priya's flow before the specialist asks the first schema question.
                """
                try:
                    params = _quest_parameters_dict()
                    pending = collect_pending_datapoints(service_id, params)
                    if not pending:
                        return
                    # First: apply any lightweight per-message prefill notes captured during Priya.
                    notes_raw = extracted.get("__wa:prefill_notes")
                    if isinstance(notes_raw, dict) and notes_raw:
                        allowed_ids = {p.get("id") for p in pending if isinstance(p, dict) and p.get("id")}
                        normalized_notes: dict[str, dict[str, Any]] = {}
                        for k, v in notes_raw.items():
                            if k not in allowed_ids:
                                continue
                            if isinstance(v, dict) and "value" in v:
                                normalized_notes[k] = v
                            else:
                                normalized_notes[k] = {"value": v, "confidence": 0.85}
                        if normalized_notes:
                            apply_extracted_ts(session, service_id, params, normalized_notes)
                            extracted["__quest:parameters"] = session.extracted_fields.get("__quest:parameters", params)
                    allowed_lines = "\n".join(
                        f"- {p.get('id')}: {p.get('label') or ''}{(' — ' + p.get('hint')) if p.get('hint') else ''}"
                        for p in pending
                        if isinstance(p, dict) and p.get("id")
                    )
                    # Full transcript so far (Priya + user).
                    turns = [
                        m
                        for m in (session.conversation_history or [])
                        if getattr(m, "role", None) in (MessageRole.USER, MessageRole.ASSISTANT)
                    ]
                    transcript = "\n".join(
                        f"{'User' if t.role == MessageRole.USER else 'Assistant'}: {t.content}"
                        for t in turns
                        if (t.content or "").strip()
                    )[-4000:]
                    prompt = (
                        "Extract structured data from the conversation so far. Return STRICT JSON only.\n"
                        "Extract ANY of the allowed fields that the user has already provided.\n"
                        f"Allowed fields:\n{allowed_lines}\n\n"
                        f"Conversation so far:\n{transcript}\n"
                    )
                    out = await get_llm_engine().extract_json(
                        session_id=f"{session.session_id}:handoff_prefill",
                        extraction_prompt=prompt,
                    )
                    # Normalize: accept {"field": "value"} or {"field": {"value":..,"confidence":..}}
                    if isinstance(out, dict) and out:
                        allowed_ids = {p.get("id") for p in pending if isinstance(p, dict) and p.get("id")}
                        normalized: dict[str, dict[str, Any]] = {}
                        for k, v in out.items():
                            if k not in allowed_ids:
                                continue
                            if isinstance(v, dict) and "value" in v:
                                normalized[k] = v
                            else:
                                normalized[k] = {"value": v, "confidence": 0.85}
                        apply_extracted_ts(session, service_id, params, normalized)
                        # Ensure extracted_fields stays in sync.
                        extracted["__quest:parameters"] = session.extracted_fields.get("__quest:parameters", params)
                except Exception:
                    return

            def _next_pending_datapoint(service_id: str) -> dict[str, Any] | None:
                """
                Pick the next schema datapoint deterministically (same ordering as quest engine),
                so the specialist welcome asks a concrete, answerable question immediately.
                """
                try:
                    params = _quest_parameters_dict()
                    pending = collect_pending_datapoints(service_id, params)
                    return pending[0] if pending else None
                except Exception:
                    return None

            async def _specialist_welcome_reply(*, service_id: str, service_label: str, expert_first: str) -> str:
                def _service_emoji(sid: str) -> str:
                    s = (sid or "").strip().lower()
                    if s in ("residential_interiors", "commercial_interiors"):
                        return "🛋️"
                    if "construction" in s or "property" in s:
                        return "🏗️"
                    if s == "painting":
                        return "🎨"
                    if "solar" in s:
                        return "☀️"
                    if "plumbing" in s:
                        return "🚰"
                    if "electrical" in s:
                        return "⚡"
                    if "automation" in s:
                        return "🏠"
                    return ""

                emoji = _service_emoji(service_id)
                emoji_suffix = f" {emoji}" if emoji else ""
                # Known facts captured by Priya in the WhatsApp stage machine.
                known_bits: list[str] = []
                if svc_bucket:
                    known_bits.append(f"service={svc_bucket}")
                ov = str(extracted.get("__wa:other_vendors_answer") or "").strip()
                if ov:
                    known_bits.append(f"other_vendors_answer={ov}")
                ha = str(extracted.get("__wa:hear_about_answer") or "").strip()
                if ha:
                    known_bits.append(f"heard_about_answer={ha}")
                known_facts = "; ".join(known_bits) if known_bits else "none"

                # Project facts captured so far (quest parameters). This is what we WANT to recap aloud.
                # Exclude referral/vendor-history and any contact scheduling fields.
                params = _quest_parameters_dict()
                recap_allow = (
                    "project_type",
                    "scope_type",
                    "painting_scope",
                    "size_sqft",
                    "plot_size_sqft",
                    "capacity_kw",
                    "grid_type",
                    "roof_type",
                    "monthly_units",
                    "load_requirement",
                    "style",
                    "rooms",
                    "budget",
                    "timeline",
                    "location",
                )
                recap_bits: list[str] = []
                for k in recap_allow:
                    if k not in params:
                        continue
                    raw = params.get(k)
                    v = raw.get("value") if isinstance(raw, dict) else raw
                    if v is None:
                        continue
                    sv = str(v).strip()
                    if not sv or sv.lower() in ("none", "null", "not provided"):
                        continue
                    label = k.replace("_", " ")
                    recap_bits.append(f"{label}: {sv}")
                    if len(recap_bits) >= 3:
                        break
                recap_facts = "; ".join(recap_bits) if recap_bits else "none yet"

                # If we still have no structured project facts, pull a minimal, safe recap
                # from conversation history so the welcome feels continuous (Retell-style),
                # without relying on extraction succeeding.
                if recap_facts == "none yet":
                    try:
                        turns = [
                            m
                            for m in (session.conversation_history or [])
                            if getattr(m, "role", None) == MessageRole.USER and (m.content or "").strip()
                        ]
                        # Prefer a service-related user utterance; avoid vendor/referral answers.
                        svc = (svc_bucket or "").strip().lower()
                        ignore_re = re.compile(
                            r"\b(instagram|google|referral|friend|ad|ads|heard about|how did you hear|vendor|vendors)\b",
                            re.I,
                        )
                        picked = ""
                        for t in turns:
                            s = (t.content or "").strip()
                            if not s or ignore_re.search(s):
                                continue
                            if svc and svc in s.lower():
                                picked = s
                                break
                        if not picked and turns:
                            # Fall back to first non-ignored user message.
                            for t in turns:
                                s = (t.content or "").strip()
                                if s and not ignore_re.search(s):
                                    picked = s
                                    break
                        picked = re.sub(r"\s+", " ", picked).strip()
                        if picked:
                            recap_facts = picked[:140]
                    except Exception:
                        pass

                # Determine the next concrete field to ask.
                dp = _next_pending_datapoint(service_id)
                if isinstance(dp, dict) and dp.get("id"):
                    dp_id = str(dp.get("id") or "").strip()
                    dp_label = str(dp.get("label") or dp_id).strip()
                    dp_hint = str(dp.get("hint") or "").strip()
                    dp_opts = dp.get("options")
                    opts_str = ""
                    if isinstance(dp_opts, list) and dp_opts:
                        opts_str = ", ".join(str(o) for o in dp_opts[:10])
                    next_field = (
                        f"id={dp_id}; label={dp_label}"
                        + (f"; hint={dp_hint}" if dp_hint else "")
                        + (f"; options={opts_str}" if opts_str else "")
                    )
                else:
                    next_field = "none (ask the next required datapoint from the service schema)"

                # Provide the next-field goal (id/label/hint), but let the LLM phrase it naturally.
                # This avoids robotic "Label — hint" fragments in the welcome question.
                next_field_goal = (
                    f"id={dp_id}; label={dp_label}"
                    + (f"; hint={dp_hint}" if dp_hint else "")
                    + (f"; options={opts_str}" if opts_str else "")
                )

                system_prompt = (
                    "You are a specialist consultant at PropFlow on WhatsApp.\n"
                    "This is the handoff from Jessica. The user already agreed to connect.\n"
                    "Write 2–3 short sentences.\n"
                    "1) Introduce yourself by FIRST name and say Jessica transferred them.\n"
                    "2) Briefly recap the project facts below.\n"
                    "3) Ask EXACTLY ONE clear question to collect the next field.\n"
                    "Hard rules:\n"
                    "- Do NOT mention Instagram or other vendors.\n"
                    "- Do NOT say site visit / site assessment / site inspection / on-site.\n"
                    "- Ask only ONE question (end with a single '?').\n"
                    "- The question must be a full natural sentence (never a label like 'Paintable area (sqft)?').\n"
                    "- Phrase it like an expert who just picked up a warm transfer.\n"
                    "- Include the service emoji once in sentence 1, right after the service name.\n"
                    "- Your ONE question must be about this field goal (you may rephrase naturally):\n"
                    f"{next_field_goal}\n"
                    "If the field hint contains options, include 2–4 options naturally.\n"
                    f"Service: {service_label}{emoji_suffix}\n"
                    f"Specialist first name: {expert_first}\n"
                    f"Project facts to recap: {recap_facts}\n"
                )
                text = (
                    await get_llm_engine().chat(
                        session_id=f"{session.session_id}:specialist_welcome_text",
                        user_message="Write the welcome message now.",
                        system_prompt=system_prompt,
                        history=[],
                        temperature=0.2,
                        max_tokens=280,
                    )
                ).strip()
                # Treat ultra-short completions as provider truncation; retry once.
                if "?" in text and len(text) >= 60:
                    return text
                # One retry: stricter.
                retry_prompt = system_prompt + "\nReturn 2–3 sentences. Ask only one question ending with '?'."
                text2 = (
                    await get_llm_engine().chat(
                        session_id=f"{session.session_id}:specialist_welcome_text_retry",
                        user_message="Write the welcome message now.",
                        system_prompt=retry_prompt,
                        history=[],
                        temperature=0.0,
                        max_tokens=320,
                    )
                ).strip()
                if "?" in text2 and len(text2) >= 60:
                    return text2
                # Deterministic fallback (still natural + option-based).
                # Avoid label/hint fragments; phrase as a real consultant question.
                qid = (dp_id or "").strip().lower()
                hint = (dp_hint or "").strip()
                # If hint lists options, use them so the question is specific (e.g. roof_type).
                if hint and ("," in hint or " or " in hint.lower()):
                    q = f"To start, which option fits best — {hint}?"
                if qid.endswith("_sqft") or "sqft" in qid:
                    q = "To start, roughly what paintable area are we talking in square feet?"
                elif qid.endswith("_kw") or "capacity" in qid:
                    q = "To start, what solar capacity are you aiming for in kW?"
                elif "budget" in qid:
                    q = "To start, what budget are you comfortable with for this project?"
                elif "timeline" in qid or "preferred_start" in qid or "start" in qid:
                    q = "To start, when would you like to begin?"
                elif not hint:
                    q = "To start, could you share that detail?"
                return f"Hi, I’m {expert_first} from PropFlow {service_label}{emoji_suffix} — Jessica just transferred you. {q}"

            # If specialist is active, skip Priya stages and let the quest engine take over.
            if stage == "SPECIALIST_ACTIVE":
                pass
            elif stage == "PRIYA_SERVICE_PICK":
                is_first = bool(extracted.get("__wa:first_message"))
                first_msg_instruction = (
                    "This is the FIRST message of the conversation.\n"
                    "Greet the caller warmly as Jessica from PropFlow, then naturally mention ALL seven services: interiors, construction, painting, solar, plumbing, electrical, and home automation.\n"
                    "Ask which one they need. Keep it warm and conversational, not robotic.\n"
                    "Never abbreviate or drop any of the seven.\n"
                    "Include the 👋 emoji exactly once in this first message.\n"
                ) if is_first else ""
                if is_first:
                    extracted.pop("__wa:first_message", None)
                ongoing = "" if is_first else JESSICA_ONGOING_TONE
                prompt = (
                    f"{JESSICA_GP}\n"
                    "You are replying on WhatsApp.\n"
                    f"{first_msg_instruction}"
                    f"{ongoing}"
                    "Task: pick exactly ONE service from the allowed list, or ask ONE clarifying question if unclear.\n"
                    f"Allowed services: {', '.join(allowed_services)}.\n"
                    "Return ONLY valid JSON with keys:\n"
                    '- "service": one of the allowed services or "unclear"\n'
                    '- "reply": If service is unclear, ask EXACTLY ONE clarifying question. If service is identified, write ONE short acknowledgement sentence with no question.\n'
                    "Hard rule: do NOT mention connecting to a specialist yet.\n"
                    "Do not ask about callback time.\n"
                    "If the user asks what services are available, list ALL seven exactly: interiors, construction, painting, solar, plumbing, electrical, and home automation — never abbreviate or summarise.\n"
                    f"User message: {user_message!r}\n"
                )
                out = await _llm_json(prompt)
                service = str(out.get("service") or "unclear").strip().lower()
                reply = str(out.get("reply") or "").strip()
                if service in service_to_router_code:
                    extracted["__wa:service_bucket"] = service
                    _tag_service(service)
                    # Capture any early project facts in the same user message now that service is known.
                    qid = str(extracted.get("__quest:service_id") or "")
                    if qid:
                        await _capture_prefill_from_user_message(qid)
                    # Collapse the service acknowledgement + other-vendors question into ONE message.
                    # Prevents "Ok got it" dead-ends where the user replies "yes" before we ever asked.
                    extracted["__wa:stage"] = "PRIYA_OTHER_VENDORS"
                    extracted["__wa:lastAsk"] = "other_vendors"
                    extracted["__wa:ask_count:other_vendors"] = 0
                    combined_prompt = (
                        f"{JESSICA_GP}\n"
                        f"{JESSICA_ONGOING_TONE}"
                        f"Service chosen: {service!r}.\n"
                        "Write ONE natural WhatsApp message that:\n"
                        "1. Briefly acknowledges the chosen service\n"
                        "2. Immediately asks: Have you reached out to any other vendors for this?\n"
                        "Hard rules:\n"
                        "- Must end with '?'\n"
                        "- EXACTLY ONE question total\n"
                        "- Do NOT mention connecting/transferring to a specialist yet\n"
                        "Return ONLY JSON: {\"reply\": \"...\"}\n"
                    )
                    out2 = await _llm_json(combined_prompt)
                    reply = str(out2.get("reply") or "").strip()
                    if not reply or "?" not in reply:
                        reply = f"Got it — {service}. Have you reached out to any other vendors for this project?"
                else:
                    extracted["__wa:stage"] = "PRIYA_SERVICE_PICK"
                if not reply:
                    reply = (
                        "Hi, I’m Jessica from PropFlow 👋 What are you looking for today—interiors, construction, painting, solar, plumbing, electrical, or home automation?"
                        if is_first
                        else "Which service is this for—interiors, construction, painting, solar, plumbing, electrical, or home automation?"
                    )
                session.add_message(MessageRole.ASSISTANT, reply)
                return AgentResponse(text=reply, session=session)
            elif stage == "PRIYA_OTHER_VENDORS":
                qid = str(extracted.get("__quest:service_id") or "")
                if qid:
                    await _capture_prefill_from_user_message(qid)
                prompt = (
                    f"{JESSICA_GP}\n"
                    f"{JESSICA_ONGOING_TONE}"
                    f"Service chosen: {svc_bucket!r}.\n"
                    "Write EXACTLY ONE short question asking: Have you reached out to any other vendors for this?\n"
                    "Hard rules:\n"
                    "- Do NOT mention connecting to a specialist.\n"
                    "- Do NOT mention next steps.\n"
                    "- Do NOT use filler phrases like 'Quick one'.\n"
                    "If the user already answered, acknowledge briefly and set answered=true.\n"
                    "If the user already answered, do NOT ask the same vendors question again.\n"
                    "Return ONLY JSON: {\"answered\": true/false, \"reply\": \"...\"}\n"
                    f"User message: {user_message!r}\n"
                )
                out = await _llm_json(prompt)
                answered = _coerce_bool(out.get("answered")) is True
                _last_ask_key = "__wa:lastAsk"
                _last_ask = str(extracted.get(_last_ask_key) or "").strip()
                _ask_key = "__wa:ask_count:other_vendors"
                _ask_count = int(extracted.get(_ask_key) or 0)
                # Field-lock (specialist-style): only accept "answered=true" if Priya actually
                # asked this specific question last. Prevents generic "yes/ok" from skipping.
                if answered and _last_ask != "other_vendors":
                    answered = False
                # History gate (bulletproof): only allow "answered=true" if the LAST assistant
                # message actually asked the other-vendors question. Prevents skipping when
                # the user says generic "yes/ok" and the model misflags answered=true.
                if answered:
                    last_asst = ""
                    try:
                        for m in reversed(session.conversation_history or []):
                            if getattr(m, "role", None) == MessageRole.ASSISTANT and (m.content or "").strip():
                                last_asst = (m.content or "").strip()
                                break
                    except Exception:
                        last_asst = ""
                    if not re.search(r"\b(other vendors?|reached out to any other vendors?)\b", last_asst, re.I):
                        answered = False
                if not answered:
                    if _ask_count >= 1:
                        # Asked once already — accept and move on
                        answered = True
                        extracted[_ask_key] = 0
                    else:
                        extracted[_ask_key] = _ask_count + 1
                else:
                    extracted[_ask_key] = 0
                # If the model fails to mark answered=true, run a tiny LLM intent check so we don't re-ask.
                if not answered:
                    intent_prompt = (
                        "The user was asked: 'Have you reached out to any other vendors for this project?'\n"
                        f"User replied: {user_message!r}\n"
                        "Did the user answer that question?\n"
                        "- YES = they clearly answered (yes/no + brief context)\n"
                        "- NO = they did not answer\n"
                        "- UNCLEAR = genuinely cannot tell\n"
                        "Return ONLY one word: YES or NO or UNCLEAR\n"
                    )
                    try:
                        intent_raw = await get_llm_engine().chat(
                            session_id=f"{session.session_id}:other_vendors_answered",
                            user_message=intent_prompt,
                            system_prompt="Return ONLY one word: YES or NO or UNCLEAR.",
                            history=[],
                            temperature=0.0,
                            max_tokens=8,
                        )
                        ir = (intent_raw or "").strip().upper()
                        m = re.search(r"\b(YES|NO|UNCLEAR|Y|N)\b", ir)
                        if m:
                            tok = m.group(1)
                            answered = True if tok in ("YES", "Y") else answered
                    except Exception:
                        pass
                if answered:
                    # Persist the raw answer for handoff context, but also try to interpret YES/NO.
                    extracted["__wa:other_vendors_answer"] = (user_message or "").strip()

                    yn = ""
                    try:
                        yn_prompt = (
                            "The user was asked: 'Have you reached out to any other vendors for this project?'\n"
                            f"User replied: {user_message!r}\n"
                            "Decide if they meant YES or NO.\n"
                            "- YES if they say yes or mention any vendor/company.\n"
                            "- NO if they clearly say no.\n"
                            "- UNCLEAR otherwise.\n"
                            "Return ONLY one word: YES or NO or UNCLEAR\n"
                        )
                        yn_raw = await get_llm_engine().chat(
                            session_id=f"{session.session_id}:other_vendors_yesno",
                            user_message=yn_prompt,
                            system_prompt="Return ONLY one word: YES or NO or UNCLEAR.",
                            history=[],
                            temperature=0.0,
                            max_tokens=6,
                        )
                        ir = (yn_raw or "").strip().upper()
                        m = re.search(r"\b(YES|NO|UNCLEAR|Y|N)\b", ir)
                        if m:
                            tok = m.group(1)
                            yn = "YES" if tok in ("YES", "Y") else "NO" if tok in ("NO", "N") else "UNCLEAR"
                    except Exception:
                        yn = ""

                    # If they reached out, capture vendor/company name like "hear about" (info-capture),
                    # otherwise move on to hear-about.
                    if yn == "YES":
                        extracted["__wa:stage"] = "PRIYA_OTHER_VENDORS_NAME"
                        extracted["__wa:lastAsk"] = "other_vendors_name"
                        extracted["__wa:ask_count:other_vendors_name"] = 0
                        name_prompt = (
                            f"{JESSICA_GP}\n"
                            f"{JESSICA_ONGOING_TONE}"
                            f"Service chosen: {svc_bucket!r}.\n"
                            "Write EXACTLY ONE short question asking which vendor/company they reached out to.\n"
                            "Hard rules:\n"
                            "- Ask only ONE question, end with '?'\n"
                            "- Include 2 examples in parentheses, like (e.g., Brick & Bolt, Livspace)\n"
                            "- Do NOT mention connecting to a specialist yet\n"
                            "Return ONLY JSON: {\"reply\": \"...\"}\n"
                        )
                        outn = await _llm_json(name_prompt)
                        reply = str(outn.get("reply") or "").strip()
                        if not reply or "?" not in reply:
                            reply = "Which vendor/company did you reach out to (e.g., Brick & Bolt, Livspace)?"
                    else:
                        extracted["__wa:stage"] = "PRIYA_HEAR_ABOUT"
                        combined_prompt = (
                            f"{JESSICA_GP}\n"
                            f"{JESSICA_ONGOING_TONE}"
                            f"Service chosen: {svc_bucket!r}.\n"
                            f"The caller just answered the other-vendors question. Their answer: {user_message!r}\n"
                            "Write ONE natural message that:\n"
                            "1. Acknowledges their answer briefly\n"
                            "2. Immediately asks: how did you hear about PropFlow?\n"
                            "Both in one sentence or two short sentences max.\n"
                            "Return ONLY JSON: {\"reply\": \"...\"}\n"
                        )
                        combined_out = await _llm_json(combined_prompt)
                        reply = (
                            str(combined_out.get("reply") or "").strip()
                            or "Got it. And how did you hear about PropFlow?"
                        )
                        # We are asking the next pre-question now.
                        extracted[_last_ask_key] = "hear_about"
                else:
                    reply = str(out.get("reply") or "").strip()
                    # Invariant: when we are still waiting for an answer, we must actually ask the vendors question.
                    if not reply or "?" not in reply or not re.search(r"\b(other vendors?|reached out to any other vendors?)\b", reply, re.I):
                        reply = "Have you reached out to any other vendors for this project?"
                    # We are asking the vendors question now.
                    extracted[_last_ask_key] = "other_vendors"
                session.add_message(MessageRole.ASSISTANT, reply)
                return AgentResponse(text=reply, session=session)
            elif stage == "PRIYA_OTHER_VENDORS_NAME":
                # Capture vendor/company name (info-capture). "yes" is not a valid answer here.
                _last_ask_key = "__wa:lastAsk"
                _ask_key = "__wa:ask_count:other_vendors_name"
                _ask_count = int(extracted.get(_ask_key) or 0)
                extracted[_ask_key] = _ask_count

                name = (user_message or "").strip()
                looks_like_non_answer = bool(re.match(r"^(yes|yeah|yep|ok|okay|sure|done|cool|thanks|thank you)\b", name, re.I))

                if name and not looks_like_non_answer and len(name) >= 2:
                    extracted["__wa:other_vendors_name"] = name
                    extracted["__wa:stage"] = "PRIYA_HEAR_ABOUT"
                    combined_prompt = (
                        f"{JESSICA_GP}\n"
                        f"{JESSICA_ONGOING_TONE}"
                        f"Service chosen: {svc_bucket!r}.\n"
                        f"The caller shared the vendor/company they reached out to: {name!r}\n"
                        "Write ONE natural message that:\n"
                        "1. Acknowledges briefly\n"
                        "2. Immediately asks: how did you hear about PropFlow?\n"
                        "Return ONLY JSON: {\"reply\": \"...\"}\n"
                    )
                    out2 = await _llm_json(combined_prompt)
                    reply = str(out2.get("reply") or "").strip() or "Got it. And how did you hear about PropFlow?"
                    extracted[_last_ask_key] = "hear_about"
                    session.add_message(MessageRole.ASSISTANT, reply)
                    return AgentResponse(text=reply, session=session)

                # Re-ask once with examples; then move on to avoid loops.
                if _ask_count >= 1:
                    extracted[_ask_key] = 0
                    extracted["__wa:stage"] = "PRIYA_HEAR_ABOUT"
                    reply = "No worries. And how did you hear about PropFlow?"
                    extracted[_last_ask_key] = "hear_about"
                    session.add_message(MessageRole.ASSISTANT, reply)
                    return AgentResponse(text=reply, session=session)

                extracted[_ask_key] = _ask_count + 1
                reply = "Which vendor/company did you reach out to (e.g., Brick & Bolt, Livspace)?"
                extracted[_last_ask_key] = "other_vendors_name"
                session.add_message(MessageRole.ASSISTANT, reply)
                return AgentResponse(text=reply, session=session)
            elif stage == "PRIYA_HEAR_ABOUT":
                qid = str(extracted.get("__quest:service_id") or "")
                if qid:
                    await _capture_prefill_from_user_message(qid)
                prompt = (
                    f"{JESSICA_GP}\n"
                    f"{JESSICA_ONGOING_TONE}"
                    f"Service chosen: {svc_bucket!r}.\n"
                    "Write EXACTLY ONE short question asking: How did you hear about PropFlow?\n"
                    "Hard rules:\n"
                    "- Do NOT mention connecting to a specialist.\n"
                    "- Do NOT mention next steps.\n"
                    "If the user already answered, acknowledge briefly and set answered=true.\n"
                    "Return ONLY JSON: {\"answered\": true/false, \"reply\": \"...\"}\n"
                    f"User message: {user_message!r}\n"
                )
                out = await _llm_json(prompt)
                answered = _coerce_bool(out.get("answered")) is True
                _last_ask_key = "__wa:lastAsk"
                _last_ask = str(extracted.get(_last_ask_key) or "").strip()
                _ask_key = "__wa:ask_count:hear_about"
                _ask_count = int(extracted.get(_ask_key) or 0)
                # Field-lock (specialist-style): only accept "answered=true" if Priya actually
                # asked this specific question last.
                if answered and _last_ask != "hear_about":
                    answered = False
                if not answered:
                    if _ask_count >= 1:
                        answered = True
                        extracted[_ask_key] = 0
                    else:
                        extracted[_ask_key] = _ask_count + 1
                else:
                    extracted[_ask_key] = 0
                # If the model fails to mark answered=true, run a tiny LLM intent check so we don't re-ask.
                if not answered:
                    intent_prompt = (
                        "The user was asked: 'How did you hear about PropFlow?'\n"
                        f"User replied: {user_message!r}\n"
                        "Did the user answer that question?\n"
                        "- YES = they clearly answered (source like Instagram, Google, referral)\n"
                        "- NO = they did not answer\n"
                        "- UNCLEAR = genuinely cannot tell\n"
                        "Return ONLY one word: YES or NO or UNCLEAR\n"
                    )
                    try:
                        intent_raw = await get_llm_engine().chat(
                            session_id=f"{session.session_id}:hear_about_answered",
                            user_message=intent_prompt,
                            system_prompt="Return ONLY one word: YES or NO or UNCLEAR.",
                            history=[],
                            temperature=0.0,
                            max_tokens=8,
                        )
                        ir = (intent_raw or "").strip().upper()
                        m = re.search(r"\b(YES|NO|UNCLEAR|Y|N)\b", ir)
                        if m:
                            tok = m.group(1)
                            answered = True if tok in ("YES", "Y") else answered
                    except Exception:
                        pass
                if answered:
                    # Persist Priya pre-connect answer so the specialist can recap it on handoff.
                    extracted["__wa:hear_about_answer"] = (user_message or "").strip()
                    extracted["__wa:stage"] = "PRIYA_CONNECT_CONFIRM"
                    expert = _expert_first_name_for_persona()
                    qid = str(extracted.get("__quest:service_id") or "")
                    manifest = QUEST_SERVICE_REGISTRY.get(qid) or {}
                    service_label = str(manifest.get("webhook_service_name") or svc_bucket).strip()
                    combined_prompt = (
                        f"{JESSICA_GP}\n"
                        f"{JESSICA_ONGOING_TONE}"
                        f"Service chosen: {svc_bucket!r} ({service_label}). Expert: {expert!r}.\n"
                        f"The caller just answered how they heard about PropFlow. Their answer: {user_message!r}\n"
                        "Write ONE natural message that:\n"
                        "1. Acknowledges their answer briefly\n"
                        "2. Immediately recommends the specialist and asks yes/no to connect\n"
                        "Both in one or two short sentences max.\n"
                        "Return ONLY JSON: {\"reply\": \"...\"}\n"
                    )
                    combined_out = await _llm_json(combined_prompt)
                    fallback_expert = expert or "our specialist"
                    reply = (
                        str(combined_out.get("reply") or "").strip()
                        or f"Got it. I can connect you with our {service_label} expert {fallback_expert}. Want me to connect you now?"
                    )
                    # We are now asking the connect confirmation.
                    extracted[_last_ask_key] = "connect_confirm"
                else:
                    reply = str(out.get("reply") or "").strip() or "And how did you hear about PropFlow?"
                    # We are asking the hear-about question now.
                    extracted[_last_ask_key] = "hear_about"
                session.add_message(MessageRole.ASSISTANT, reply)
                return AgentResponse(text=reply, session=session)
            elif stage == "PRIYA_CONNECT_CONFIRM":
                if svc_bucket in service_to_router_code and not extracted.get("__quest:service_id"):
                    _tag_service(svc_bucket)
                qid = str(extracted.get("__quest:service_id") or "")
                if qid:
                    await _capture_prefill_from_user_message(qid)
                expert = _expert_first_name_for_persona()
                manifest = QUEST_SERVICE_REGISTRY.get(qid) or {}
                service_label = str(manifest.get("webhook_service_name") or "").strip()
                _ask_key = "__wa:ask_count:connect_confirm"
                _ask_count = int(extracted.get(_ask_key) or 0)

                # Hard no-loop rule: any clear "yes" transfers immediately (including first time).
                if _looks_like_affirmative(user_message):
                    extracted[_ask_key] = 0
                    extracted["__wa:stage"] = "SPECIALIST_WELCOME"
                    service_label2 = service_label or svc_bucket
                    expert2 = expert or "Team"
                    qid2 = str(extracted.get("__quest:service_id") or "")
                    if qid2:
                        await _prefill_params_from_history(qid2)
                    reply = await _specialist_welcome_reply(
                        service_id=qid2,
                        service_label=service_label2,
                        expert_first=expert2,
                    )
                    extracted["__wa:stage"] = "SPECIALIST_ACTIVE"
                    session.add_message(MessageRole.ASSISTANT, reply)
                    return AgentResponse(text=reply, session=session)

                # Clear "no" without looping.
                if _looks_like_negative(user_message):
                    extracted[_ask_key] = 0
                    extracted["__wa:stage"] = "PRIYA_SERVICE_PICK"
                    extracted.pop("__wa:service_bucket", None)
                    extracted.pop("__quest:service_id", None)
                    decline_prompt = (
                        f"{JESSICA_GP}\n"
                        f"{JESSICA_ONGOING_TONE}"
                        "The user does not want to connect to the specialist right now.\n"
                        "Write ONE short, professional sentence; offer to help another way or try later.\n"
                        "Return ONLY JSON: {\"reply\": \"...\"}\n"
                        f"User message: {user_message!r}\n"
                    )
                    decl = await _llm_json(decline_prompt)
                    reply = str(decl.get("reply") or "").strip() or (
                        "No problem — tell me if you’d like a different service or we can pick this up later."
                    )
                    session.add_message(MessageRole.ASSISTANT, reply)
                    return AgentResponse(text=reply, session=session)

                # Binary intent classification (YES/NO only). Strong bias toward YES to avoid re-asking.
                intent_prompt = (
                    f"The user was asked if they want to connect to our {svc_bucket} specialist.\n"
                    f"User said: {user_message!r}\n"
                    "Decide if they want to connect.\n"
                    "- Reply YES for any positive signal (even informal/frustrated).\n"
                    "- Reply NO only for explicit refusal (not now / wait / no).\n"
                    "Languages: English, Hindi, Kannada.\n"
                    "Return ONLY: YES or NO\n"
                )
                intent = ""
                try:
                    intent_raw = await get_llm_engine().chat(
                        session_id=f"{session.session_id}:connect_intent",
                        user_message=intent_prompt,
                        system_prompt="Return ONLY: YES or NO",
                        history=[],
                        temperature=0.0,
                        max_tokens=5,
                    )
                    ir = (intent_raw or "").strip().upper()
                    m = re.search(r"\b(YES|NO|Y|N)\b", ir)
                    if m:
                        tok = m.group(1)
                        intent = "YES" if tok == "Y" else "NO" if tok == "N" else tok
                except Exception:
                    intent = ""

                # Parse safety net: anything malformed defaults to YES (connect > re-ask).
                if intent not in ("YES", "NO"):
                    if _ask_count < 1:
                        # Ask once more (only once) if truly unparseable.
                        extracted[_ask_key] = _ask_count + 1
                        confirm_prompt = (
                            f"{JESSICA_GP}\n"
                            f"{JESSICA_ONGOING_TONE}"
                            f"Service: {svc_bucket!r} ({service_label}). Expert: {expert!r}.\n"
                            "Write 1–2 sentences: acknowledge what they said and ask ONE clear yes/no question to connect.\n"
                            "Return ONLY JSON: {\"reply\": \"...\"}\n"
                            f"User message: {user_message!r}\n"
                        )
                        out = await _llm_json(confirm_prompt)
                        reply = str(out.get("reply") or "").strip() or (
                            f"Shall I connect you with our {svc_bucket} expert{(' ' + expert) if expert else ''} now?"
                        )
                        extracted["__wa:stage"] = "PRIYA_CONNECT_CONFIRM"
                        session.add_message(MessageRole.ASSISTANT, reply)
                        return AgentResponse(text=reply, session=session)
                    intent = "YES"

                if intent == "NO":
                    extracted[_ask_key] = 0
                    extracted["__wa:stage"] = "PRIYA_SERVICE_PICK"
                    extracted.pop("__wa:service_bucket", None)
                    extracted.pop("__quest:service_id", None)
                    decline_prompt = (
                        f"{JESSICA_GP}\n"
                        f"{JESSICA_ONGOING_TONE}"
                        "The user does not want to connect to the specialist right now.\n"
                        "Write ONE short, professional sentence; offer to help another way or try later.\n"
                        "Return ONLY JSON: {\"reply\": \"...\"}\n"
                        f"User message: {user_message!r}\n"
                    )
                    decl = await _llm_json(decline_prompt)
                    reply = str(decl.get("reply") or "").strip() or (
                        "No problem — tell me if you’d like a different service or we can pick this up later."
                    )
                    session.add_message(MessageRole.ASSISTANT, reply)
                    return AgentResponse(text=reply, session=session)

                # YES: transfer immediately.
                extracted[_ask_key] = 0
                extracted["__wa:stage"] = "SPECIALIST_WELCOME"
                service_label2 = service_label or svc_bucket
                expert2 = expert or "Team"
                qid2 = str(extracted.get("__quest:service_id") or "")
                if qid2:
                    await _prefill_params_from_history(qid2)
                reply = await _specialist_welcome_reply(
                    service_id=qid2,
                    service_label=service_label2,
                    expert_first=expert2,
                )
                extracted["__wa:stage"] = "SPECIALIST_ACTIVE"
                session.add_message(MessageRole.ASSISTANT, reply)
                return AgentResponse(text=reply, session=session)

            elif stage == "SPECIALIST_WELCOME":
                # If we've already entered specialist mode and the user replies (e.g. "what?"),
                # don't re-send the welcome; let the quest engine handle the turn.
                if (user_message or "").strip():
                    extracted["__wa:stage"] = "SPECIALIST_ACTIVE"
                    stage = "SPECIALIST_ACTIVE"
                else:
                    qid = str(extracted.get("__quest:service_id") or "")
                    manifest = QUEST_SERVICE_REGISTRY.get(qid) or {}
                    service_label = str(manifest.get("webhook_service_name") or qid.replace("_", " ")).strip()
                    expert = _expert_first_name_for_persona() or "Team"
                    if qid:
                        await _prefill_params_from_history(qid)
                    reply = await _specialist_welcome_reply(
                        service_id=qid,
                        service_label=service_label,
                        expert_first=expert,
                    )
                    extracted["__wa:stage"] = "SPECIALIST_ACTIVE"
                    session.add_message(MessageRole.ASSISTANT, reply)
                    return AgentResponse(text=reply, session=session)

        # ── GUARDRAILS (pre off-topic) ──────────────────────────────────────
        last_q = _last_question_text(session)
        # WhatsApp: handle domain questions during specialist intake too (not voice-only).
        if (channel or "").strip().lower() == "whatsapp" and stage == "SPECIALIST_ACTIVE" and last_q:
            last_ask_raw = (
                session.extracted_fields.get("__quest:lastAsk") if isinstance(session.extracted_fields, dict) else None
            )
            asked_param = str(last_ask_raw.get("askedParam") or "") if isinstance(last_ask_raw, dict) else ""
            if not (asked_param and _looks_like_suggestion_request(user_message)) and _looks_like_domain_question(user_message):
                sid = _current_service_id(session)
                svc_name = _service_display_name(sid) if sid else "PropFlow service"
                answer = await _answer_domain_question(
                    session=session,
                    service_name=svc_name,
                    last_question=last_q,
                    user_message=user_message,
                )
                if answer:
                    await log_event(
                        "DOMAIN_QUESTION_HANDLED",
                        session_id=session.session_id,
                        data={"service_id": sid, "via": "whatsapp_active", "message_preview": (user_message or "")[:80]},
                    )
                    session.add_message(MessageRole.ASSISTANT, answer)
                    return AgentResponse(text=answer, session=session)
        if _looks_like_identity_question(user_message):
            base = get_base_identity_by_persona_key(getattr(session, "persona_key", None))
            first_line = (base or "").strip().splitlines()[0].strip()
            text = first_line
            if last_q:
                text = f"{text} {last_q}"
            session.add_message(MessageRole.ASSISTANT, text)
            return AgentResponse(text=text, session=session)

        if _looks_like_pricing_question(user_message):
            # WhatsApp: when we are mid-questionnaire, budget/estimate requests should be handled
            # by the quest engine (FIELD-LOCK), not by the generic pricing guardrail.
            last_ask_raw = (
                session.extracted_fields.get("__quest:lastAsk") if isinstance(session.extracted_fields, dict) else None
            )
            asked_param = str(last_ask_raw.get("askedParam") or "") if isinstance(last_ask_raw, dict) else ""
            if (channel or "").strip().lower() == "whatsapp" and asked_param:
                # Fall through to quest engine
                pass
            else:
                text = (
                    "Our team will give you an accurate quote once I have your complete requirements, "
                    "that way the number is specific to your project."
                )
                if last_q:
                    text = f"{text} {last_q}"
                session.add_message(MessageRole.ASSISTANT, text)
                return AgentResponse(text=text, session=session)

        # Fix #8: deterministic summary-request shortcut. Callers asking
        # "what did you capture?" / "summarize" get a brief digest of captured
        # fields + the last question re-anchored — no LLM roundtrip, no risk
        # of the classifier misrouting this turn.
        if _looks_like_summary_request(user_message):
            text = _build_summary_reply(session, last_q)
            await log_event(
                "SUMMARY_REQUEST_HANDLED",
                session_id=session.session_id,
                data={"message_preview": (user_message or "")[:80]},
            )
            session.add_message(MessageRole.ASSISTANT, text)
            return AgentResponse(text=text, session=session)

        # ── THREE-PATH CLASSIFIER (voice only) ──────────────────────────────
        # Skip classifier when there is no last question yet (first turn).
        if (channel or "").strip().lower() == "voice" and last_q:
            sid = _current_service_id(session)
            svc_name = _service_display_name(sid) if sid else "PropFlow service"

            # Deterministic PATH 2 shortcut: explicit "what is X?" / "explain" / "never
            # heard" phrases bypass the classifier entirely. Saves ~150ms and is
            # 100% reliable — these are unambiguous clarification asks.
            # Suggestion requests should be handled by the quest engine (for the
            # currently asked field), NOT by domain-answer + revert.
            last_ask_raw = (
                session.extracted_fields.get("__quest:lastAsk") if isinstance(session.extracted_fields, dict) else None
            )
            asked_param = str(last_ask_raw.get("askedParam") or "") if isinstance(last_ask_raw, dict) else ""
            if asked_param and _looks_like_suggestion_request(user_message):
                await log_event(
                    "SUGGESTION_REQUEST_BYPASS_DOMAIN",
                    session_id=session.session_id,
                    data={"asked_param": asked_param},
                )
                # Fall through: quest engine will see the utterance and respond.
            # Ordinal option handler: "tell me what it one means" / "what is the first one"
            # Maps ordinal references to actual offered options and explains that option.
            elif _looks_like_ordinal_option_request(user_message):
                offered_opts = _extract_offered_options(last_q)
                resolved = _resolve_ordinal_to_option(user_message, offered_opts)
                if resolved:
                    synthetic_msg = f"What do you mean by {resolved}?"
                    answer = await _answer_domain_question(
                        session=session,
                        service_name=svc_name,
                        last_question=last_q,
                        user_message=synthetic_msg,
                    )
                    if answer:
                        await log_event(
                            "ORDINAL_OPTION_EXPLAINED",
                            session_id=session.session_id,
                            data={"resolved": resolved, "original": user_message[:80]},
                        )
                        session.add_message(MessageRole.ASSISTANT, answer)
                        return AgentResponse(text=answer, session=session)

                # Unresolved ordinal request → fall through to the normal domain handler
                # by directly calling the same domain-answer path with the ORIGINAL user message.
                answer = await _answer_domain_question(
                    session=session,
                    service_name=svc_name,
                    last_question=last_q,
                    user_message=user_message,
                )
                if answer:
                    await log_event(
                        "DOMAIN_QUESTION_HANDLED",
                        session_id=session.session_id,
                        data={"service_id": sid, "via": "heuristic", "message_preview": (user_message or "")[:80]},
                    )
                    session.add_message(MessageRole.ASSISTANT, answer)
                    return AgentResponse(text=answer, session=session)
                # If the domain LLM call failed, fall through to the quest engine.
            elif _looks_like_domain_question(user_message):
                await log_event("CLASSIFIER_SKIPPED_DOMAIN", session_id=session.session_id, data={})
                answer = await _answer_domain_question(
                    session=session,
                    service_name=svc_name,
                    last_question=last_q,
                    user_message=user_message,
                )
                if answer:
                    await log_event(
                        "DOMAIN_QUESTION_HANDLED",
                        session_id=session.session_id,
                        data={"service_id": sid, "via": "heuristic", "message_preview": (user_message or "")[:80]},
                    )
                    session.add_message(MessageRole.ASSISTANT, answer)
                    return AgentResponse(text=answer, session=session)
                # If the domain LLM call failed, fall through to the quest engine.
            elif _is_likely_quest_answer(user_message):
                await log_event("CLASSIFIER_SKIPPED", session_id=session.session_id, data={})
            else:
                label = await _classify_voice_path(
                    session=session,
                    service_name=svc_name,
                    last_question=last_q,
                    user_message=user_message,
                )
                if label == "DOMAIN_QUESTION":
                    answer = await _answer_domain_question(
                        session=session,
                        service_name=svc_name,
                        last_question=last_q,
                        user_message=user_message,
                    )
                    if answer:
                        await log_event(
                            "DOMAIN_QUESTION_HANDLED",
                            session_id=session.session_id,
                            data={"service_id": sid, "via": "classifier", "message_preview": (user_message or "")[:80]},
                        )
                        session.add_message(MessageRole.ASSISTANT, answer)
                        return AgentResponse(text=answer, session=session)
                    # Domain response failed → PATH 1 fallback (quest engine)
                elif label == "OFF_TOPIC":
                    text = _warm_offtopic_redirect(session, sid, last_q)
                    await log_event(
                        "OFF_TOPIC_REDIRECTED",
                        session_id=session.session_id,
                        data={"service_id": sid, "message_preview": (user_message or "")[:80]},
                    )
                    session.add_message(MessageRole.ASSISTANT, text)
                    return AgentResponse(text=text, session=session)
                else:
                    await log_event("CLASSIFIER_QUEST_ANSWER", session_id=session.session_id, data={})

        # Friction handler (must run BEFORE off-topic redirect).
        # These utterances are usually the caller reacting to ASR/latency ("Are you listening?")
        # and should NOT trigger the off-topic guardrail.
        if _is_friction_complaint(user_message):
            text = "I’m here — yes, I can hear you."
            if last_q:
                text = f"{text} {last_q}"
            session.add_message(MessageRole.ASSISTANT, text)
            return AgentResponse(text=text, session=session)

        if _is_off_topic(user_message):
            session.add_message(MessageRole.ASSISTANT, GUARDRAIL_REDIRECT)
            return AgentResponse(text=GUARDRAIL_REDIRECT, session=session)

        # Optional hints for future prompt injection (quest engine does not consume these yet).
        hints = _build_guardrail_hints(user_message)
        if hints:
            gh = session.extracted_fields.setdefault("__guardrail_hints", [])
            if isinstance(gh, list):
                gh.extend(hints)

        # process_quest_turn appends assistant message(s) to history (opening + reply / closing).
        result = await process_quest_turn(session, user_message=user_message, channel=channel)

        await log_event(
            "QUEST_TURN",
            session_id=session.session_id,
            data={
                "channel": channel,
                "completed": result.completed,
                "summary_generated": result.summary_generated,
            },
        )

        return AgentResponse(
            text=result.assistant_text,
            session=session,
            summary_generated=result.summary_generated,
            completed=result.completed,
        )

    async def process_message_stream(
        self,
        session: Session,
        user_message: str,
        channel: str = "voice",
    ):
        """
        Voice streaming entrypoint.

        When VOICE_STREAM_MAIN_LLM is enabled (default), streams main assistant tokens after
        extraction so Vapi can start TTS earlier. Falls back to a single yield when disabled
        or when merged-extract or confirmation paths require the classic reply pipeline.
        """
        if channel == "voice" and get_settings().voice_stream_main_llm:
            await log_event(
                "USER_MESSAGE",
                session_id=session.session_id,
                data={"message": user_message, "stage": session.conversation_stage},
            )
            session.add_message(MessageRole.USER, user_message)
            session.voice_turn_requested_end_call = False

            # ── ROUTING HOOK (Phase 1: voice-only) ───────────────────────────
            # Tag quest service id + persona key once per session.
            await self.router_engine.route(user_message, channel="voice", session=session)

            # ── GUARDRAILS (pre off-topic) ──────────────────────────────────
            last_q = _last_question_text(session)
            if _looks_like_identity_question(user_message):
                base = get_base_identity_by_persona_key(getattr(session, "persona_key", None))
                first_line = (base or "").strip().splitlines()[0].strip()
                text = first_line
                if last_q:
                    text = f"{text} {last_q}"
                session.add_message(MessageRole.ASSISTANT, text)

                async def _guard_iter():
                    yield text

                return _guard_iter(), session, False

            if _looks_like_pricing_question(user_message):
                last_ask_raw = (
                    session.extracted_fields.get("__quest:lastAsk") if isinstance(session.extracted_fields, dict) else None
                )
                asked_param = str(last_ask_raw.get("askedParam") or "") if isinstance(last_ask_raw, dict) else ""
                if (channel or "").strip().lower() == "whatsapp" and asked_param:
                    pass
                else:
                    text = (
                        "Our team will give you an accurate quote once I have your complete requirements, "
                        "that way the number is specific to your project."
                    )
                    if last_q:
                        text = f"{text} {last_q}"
                    session.add_message(MessageRole.ASSISTANT, text)

                    async def _guard_iter():
                        yield text

                    return _guard_iter(), session, False

            # Fix #8: summary-request shortcut (voice streaming).
            if _looks_like_summary_request(user_message):
                text = _build_summary_reply(session, last_q)
                await log_event(
                    "SUMMARY_REQUEST_HANDLED",
                    session_id=session.session_id,
                    data={"message_preview": (user_message or "")[:80]},
                )
                session.add_message(MessageRole.ASSISTANT, text)

                async def _summary_iter():
                    yield text

                return _summary_iter(), session, False

            # ── THREE-PATH CLASSIFIER (voice streaming) ─────────────────────
            if last_q:
                sid = _current_service_id(session)
                svc_name = _service_display_name(sid) if sid else "PropFlow service"

                # Deterministic PATH 2 shortcut: explicit "what is X?" / "explain" /
                # "never heard" phrases bypass the classifier entirely.
                if _looks_like_domain_question(user_message):
                    await log_event("CLASSIFIER_SKIPPED_DOMAIN", session_id=session.session_id, data={})
                    answer = await _answer_domain_question(
                        session=session,
                        service_name=svc_name,
                        last_question=last_q,
                        user_message=user_message,
                    )
                    if answer:
                        await log_event(
                            "DOMAIN_QUESTION_HANDLED",
                            session_id=session.session_id,
                            data={"service_id": sid, "via": "heuristic", "message_preview": (user_message or "")[:80]},
                        )
                        session.add_message(MessageRole.ASSISTANT, answer)

                        async def _domain_iter():
                            yield answer

                        return _domain_iter(), session, False
                    # Domain response failed → fall through to quest engine.
                elif _is_likely_quest_answer(user_message):
                    await log_event("CLASSIFIER_SKIPPED", session_id=session.session_id, data={})
                else:
                    label = await _classify_voice_path(
                        session=session,
                        service_name=svc_name,
                        last_question=last_q,
                        user_message=user_message,
                    )
                    if label == "DOMAIN_QUESTION":
                        answer = await _answer_domain_question(
                            session=session,
                            service_name=svc_name,
                            last_question=last_q,
                            user_message=user_message,
                        )
                        if answer:
                            await log_event(
                                "DOMAIN_QUESTION_HANDLED",
                                session_id=session.session_id,
                                data={"service_id": sid, "via": "classifier", "message_preview": (user_message or "")[:80]},
                            )
                            session.add_message(MessageRole.ASSISTANT, answer)

                            async def _domain_iter():
                                yield answer

                            return _domain_iter(), session, False
                        # Domain response failed → PATH 1 fallback (quest engine)
                    elif label == "OFF_TOPIC":
                        text = _warm_offtopic_redirect(session, sid, last_q)
                        await log_event(
                            "OFF_TOPIC_REDIRECTED",
                            session_id=session.session_id,
                            data={"service_id": sid, "message_preview": (user_message or "")[:80]},
                        )
                        session.add_message(MessageRole.ASSISTANT, text)

                        async def _off_iter():
                            yield text

                        return _off_iter(), session, False
                    else:
                        await log_event("CLASSIFIER_QUEST_ANSWER", session_id=session.session_id, data={})

            # Friction handler (must run BEFORE off-topic redirect).
            if _is_friction_complaint(user_message):
                text = "I’m here — yes, I can hear you."
                if last_q:
                    text = f"{text} {last_q}"
                session.add_message(MessageRole.ASSISTANT, text)

                async def _friction_iter():
                    yield text

                return _friction_iter(), session, False

            if _is_off_topic(user_message):
                session.add_message(MessageRole.ASSISTANT, GUARDRAIL_REDIRECT)

                async def _guard_iter():
                    yield GUARDRAIL_REDIRECT

                return _guard_iter(), session, False

            hints = _build_guardrail_hints(user_message)
            if hints:
                gh = session.extracted_fields.setdefault("__guardrail_hints", [])
                if isinstance(gh, list):
                    gh.extend(hints)

            prep = await prepare_voice_quest_stream_or_sync(session, user_message)
            if isinstance(prep, QuestTurnResult):
                await log_event(
                    "QUEST_TURN",
                    session_id=session.session_id,
                    data={
                        "channel": channel,
                        "completed": prep.completed,
                        "summary_generated": prep.summary_generated,
                    },
                )

                # CRITICAL: do NOT overwrite — the graceful-close branch inside
                # `prepare_voice_quest_stream_or_sync` explicitly sets this flag to
                # True for caller farewells ("bye bye", "ok thanks bye") even though
                # `summary_generated` is False on that turn. The prior unconditional
                # assignment (`= prep.summary_generated`) silently cleared the flag,
                # which is why the agent kept talking after "bye bye" in production.
                # `voice_turn_requested_end_call` is reset to False at the top of
                # every voice turn, so OR-merge is stale-safe.
                session.voice_turn_requested_end_call = bool(
                    prep.summary_generated
                    or getattr(session, "voice_turn_requested_end_call", False)
                )

                async def _sync_iter():
                    yield prep.assistant_text

                return _sync_iter(), session, prep.summary_generated

            stream_factory, finalize = prep

            async def _stream_iter():
                parts: list[str] = []
                t_reply = time.perf_counter()
                async for piece in stream_factory():
                    parts.append(piece)
                    yield piece
                reply_ms = (time.perf_counter() - t_reply) * 1000.0
                result = await finalize("".join(parts), reply_ms)
                # Same OR-merge as the sync branch — preserve any flag set inside
                # the finalize path (stream-based completions can also hit graceful
                # close via post-completion heuristics).
                session.voice_turn_requested_end_call = bool(
                    result.summary_generated
                    or getattr(session, "voice_turn_requested_end_call", False)
                )
                await log_event(
                    "QUEST_TURN",
                    session_id=session.session_id,
                    data={
                        "channel": channel,
                        "completed": result.completed,
                        "summary_generated": result.summary_generated,
                    },
                )

            return _stream_iter(), session, False

        res = await self.process_message(session, user_message, channel=channel)
        # Non-voice path: OR-merge for safety though flag is rarely set here.
        res.session.voice_turn_requested_end_call = bool(
            res.summary_generated
            or getattr(res.session, "voice_turn_requested_end_call", False)
        )

        async def _iter():
            yield res.text

        return _iter(), res.session, res.summary_generated


_controller: ConversationController | None = None


def get_controller() -> ConversationController:
    global _controller
    if _controller is None:
        _controller = ConversationController()
    return _controller
