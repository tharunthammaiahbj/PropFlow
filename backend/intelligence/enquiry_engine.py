"""
Aadhya – Priority-Based Dynamic Enquiry Engine
Decides which field to ask about next based on priority and context.
"""
from __future__ import annotations
from typing import Optional
from backend.schemas.session import Session, ConversationStage

# ─── Required fields in priority order ───────────────────────────────────────
REQUIRED_FIELDS_PRIORITY = [
    "client_name",
    "property_type",
    "city",
    "service_type",
    "area_sqft",
    "configuration",
    "rooms_to_design",
    "budget_range",
    "timeline",
]

# ─── Field-to-natural-question hints for the prompt ──────────────────────────
FIELD_QUESTION_HINTS = {
    "client_name":      "Ask for their name warmly.",
    "property_type":    "Ask if this is an apartment, villa, or independent house.",
    "city":             "Ask which city or area the property is in.",
    "service_type":     "Ask if they want full-home design, partial rooms, or are renovating.",
    "area_sqft":        "Ask the approximate area of the home in square feet.",
    "configuration":    "Ask the BHK configuration (1BHK, 2BHK, 3BHK, etc.).",
    "rooms_to_design":  "Ask which specific rooms they want to design.",
    "budget_range":     "Ask for a rough budget range they have in mind.",
    "timeline":         "Ask when they're hoping to get the design completed.",
}

# ─── Contextual branches injected when conditions are met ────────────────────
def get_contextual_injections(session: Session) -> list[str]:
    """Returns additional context hints based on what we know about the client."""
    hints = []
    ef = session.extracted_fields

    if ef.get("property_type") == "villa":
        hints.append("This is a VILLA — naturally ask about number of floors and outdoor/garden areas.")
    elif ef.get("property_type") == "apartment":
        hints.append("This is an APARTMENT — if relevant, consider asking about builder restrictions.")

    if ef.get("service_type") == "renovation":
        hints.append("This is a RENOVATION — show interest in their existing furniture and electrical layout.")

    if ef.get("kids") is True:
        hints.append("CLIENT HAS KIDS — weave in child-safe design awareness naturally.")

    if ef.get("elderly") is True:
        hints.append("ELDERLY FAMILY MEMBERS present — consider accessibility and senior-friendly design.")

    if ef.get("pets") is True:
        hints.append("CLIENT HAS PETS — pet-friendly materials and layout are relevant.")

    if ef.get("pooja_room") is True:
        hints.append("CLIENT WANTS POOJA ROOM — consider mentioning Vastu orientation options.")

    # Detect budget anxiety from conversation patterns
    # (rough heuristic — more sophisticated in controller)
    if ef.get("budget_range") and any(
        word in str(ef.get("budget_range", "")).lower()
        for word in ["tight", "low", "limited", "small", "less"]
    ):
        hints.append("Client may have BUDGET ANXIETY — reassure that value design is possible.")

    return hints


def get_next_field(session: Session) -> Optional[str]:
    """Returns the next highest-priority field that hasn't been collected yet."""
    missing = [f for f in REQUIRED_FIELDS_PRIORITY if f not in session.completed_fields]
    return missing[0] if missing else None


def has_minimum_required_fields(session: Session) -> bool:
    """Returns True when all 9 required fields are collected."""
    return all(f in session.completed_fields for f in REQUIRED_FIELDS_PRIORITY)


def build_task_instruction(session: Session) -> str:
    """
    Builds the task instruction injected into the system prompt for this turn.
    Tells Gemini exactly what to focus on without being robotic.
    """
    if session.conversation_stage == ConversationStage.SUMMARY_GENERATED:
        return (
            "The project summary has been generated. "
            "Thank the client warmly, confirm the next step (our team will be in touch), "
            "and invite any final questions."
        )

    if session.conversation_stage == ConversationStage.CONFIRMATION:
        collected = session.extracted_fields
        fields_str = ", ".join(f"{k}: {v}" for k, v in collected.items())
        return (
            f"You now have enough information. Warmly summarize what you've learned: [{fields_str}]. "
            "Ask if everything sounds correct and if they'd like to add anything before we prepare their design brief."
        )

    next_field = get_next_field(session)
    injections = get_contextual_injections(session)

    if not next_field:
        return (
            "All required fields are collected. "
            "Transition naturally into confirmation: re-state the key details and ask if they sound right."
        )

    hint = FIELD_QUESTION_HINTS.get(next_field, f"Ask about {next_field}.")
    instruction = f"Your PRIMARY goal this turn: {hint}\n"

    if injections:
        instruction += "CONTEXTUAL AWARENESS (use naturally, don't list robotically):\n"
        for inj in injections:
            instruction += f"  - {inj}\n"

    instruction += (
        f"\nRemember: Ask only ONE question about {next_field}. "
        "Acknowledge what the client just said first.\n"
        "If the client already gave this information earlier in the chat, do not ask again. "
        "Acknowledge it briefly and move on to what you still need."
    )

    return instruction


class EnquiryEngine:
    """Decides next conversational move based on field completion state."""

    def get_next_field(self, session: Session) -> Optional[str]:
        return get_next_field(session)

    def is_complete(self, session: Session) -> bool:
        return has_minimum_required_fields(session)

    def build_task_instruction(self, session: Session) -> str:
        return build_task_instruction(session)


_engine: EnquiryEngine | None = None


def get_enquiry_engine() -> EnquiryEngine:
    global _engine
    if _engine is None:
        _engine = EnquiryEngine()
    return _engine
