"""
Aadhya – Structured Data Extractor
Parses Gemini conversations into structured JSON field values.
Uses Gemini's JSON mode for reliable extraction.
"""
from __future__ import annotations
import json
from typing import Any, Dict, List

from backend.utils.logger import log_event

# All extractable fields with their descriptions
EXTRACTABLE_FIELDS = {
    "client_name": "The client's full name or first name",
    "phone": "Phone number (Indian or international format)",
    "city": "City or location where the property is",
    "property_type": "One of: apartment, villa, independent_house, plot, penthouse",
    "project_name": "Name of the housing project or society (if mentioned)",
    "area_sqft": "Area in square feet as a number string",
    "configuration": "BHK configuration e.g. 1BHK, 2BHK, 3BHK, 4BHK, 5BHK, studio",
    "floor_number": "Floor number of the apartment (if mentioned)",
    "possession_status": "One of: ready_to_move, under_construction, renovation",
    "service_type": "One of: full_home, partial, single_room, renovation, consultation",
    "rooms_to_design": "List of rooms mentioned e.g. [living room, master bedroom, kitchen]",
    "kitchen_type": "One of: modular, semi_modular, open, straight, L_shaped, U_shaped",
    "wardrobe_count": "Number of wardrobes needed (integer)",
    "false_ceiling_required": "true or false",
    "design_style": "One of: modern, contemporary, traditional, bohemian, japandi, scandinavian, industrial, luxury",
    "color_preferences": "List of color preferences mentioned",
    "budget_range": "Budget as a range string e.g. '10-15 lakh', '50 lakh', '1 crore'",
    "timeline": "Timeline string e.g. '3 months', 'by June 2026', 'ASAP'",
    "preferred_start": "When they want to start e.g. 'next month', 'April 2026'",
    "must_have_features": "List of must-have features the client explicitly requested",
    "avoid_items": "List of things client wants to avoid",
    "kids": "true if client has children, false otherwise",
    "pets": "true if client has pets, false otherwise",
    "elderly": "true if elderly family members will live there, false otherwise",
    "vastu_importance": "One of: strict, flexible, not_important",
    "storage_priority": "One of: high, medium, low",
    "pooja_room": "true if client wants a pooja room, false otherwise",
    "design_inspiration_words": "List of adjectives/words client used to describe their dream space",
    "contact_pref": "Preferred contact method: whatsapp, call, email",
    "callback_time": "Preferred callback time if mentioned",
}


def build_extraction_prompt(conversation_excerpt: str) -> str:
    fields_desc = "\n".join(
        f'  "{k}": "{v}"' for k, v in EXTRACTABLE_FIELDS.items()
    )
    return f"""You are a data extraction assistant. Analyze the following conversation between a user and an interior design consultant.

Extract ONLY the fields that are clearly mentioned or confirmed in the conversation.
Do NOT guess or infer — only extract what the user explicitly stated.
Return ONLY valid JSON with the fields that were found. Omit fields that are not mentioned.
For boolean fields, use true/false (not strings).
For list fields, return JSON arrays.

FIELDS TO EXTRACT:
{{
{fields_desc}
}}

CONVERSATION:
{conversation_excerpt}

Return ONLY a JSON object with the extracted fields. No explanation, no markdown, just JSON.
Example: {{"client_name": "Priya", "property_type": "apartment", "area_sqft": "1200"}}
"""


class StructuredExtractor:
    """
    Extracts structured field values from conversation turns.
    Merges newly found fields into session state.
    """

    async def extract(
        self,
        session_id: str,
        conversation_history: list,
        gemini_engine,
    ) -> Dict[str, Any]:
        """
        Run JSON-mode extraction on recent conversation turns.
        Returns dict of newly extracted fields (may be empty).
        """
        # Last N turns: must include early turns where name / property are often given
        _RECENT_FOR_EXTRACT = 14
        recent = (
            conversation_history[-_RECENT_FOR_EXTRACT:]
            if len(conversation_history) > _RECENT_FOR_EXTRACT
            else conversation_history
        )
        excerpt = self._format_excerpt(recent)

        if not excerpt.strip():
            return {}

        prompt = build_extraction_prompt(excerpt)
        raw = await gemini_engine.extract_json(session_id=session_id, extraction_prompt=prompt)

        if not isinstance(raw, dict):
            return {}

        # Normalize types
        cleaned = self._normalize(raw)

        if cleaned:
            await log_event("EXTRACTED_FIELDS", session_id=session_id,
                            data={"fields": cleaned})

        return cleaned

    def _format_excerpt(self, messages: list) -> str:
        lines = []
        for msg in messages:
            if hasattr(msg, "role") and hasattr(msg, "content"):
                role_label = "User" if msg.role == "user" else "Sophia"
                lines.append(f"{role_label}: {msg.content}")
        return "\n".join(lines)

    def _normalize(self, raw: dict) -> dict:
        """Clean and normalize extracted field values."""
        result = {}
        bool_fields = {"false_ceiling_required", "kids", "pets", "elderly", "pooja_room"}
        list_fields = {"rooms_to_design", "color_preferences", "must_have_features",
                       "avoid_items", "design_inspiration_words"}

        for k, v in raw.items():
            if k not in EXTRACTABLE_FIELDS:
                continue  # ignore unknown fields
            if v is None or v == "" or v == [] or v == {}:
                continue

            if k in bool_fields:
                if isinstance(v, bool):
                    result[k] = v
                elif isinstance(v, str):
                    result[k] = v.lower() in ("true", "yes", "1")
            elif k in list_fields:
                if isinstance(v, list):
                    result[k] = [str(i) for i in v if i]
                elif isinstance(v, str):
                    result[k] = [v]
            elif k == "wardrobe_count":
                try:
                    result[k] = int(v)
                except (ValueError, TypeError):
                    pass
            else:
                result[k] = str(v).strip()

        return result

    def merge_into_session(self, session, new_fields: Dict[str, Any]) -> List[str]:
        """
        Merge extracted fields into session state.
        Returns list of newly completed field names.
        """
        newly_completed = []
        for field, value in new_fields.items():
            if field not in session.completed_fields:
                session.mark_field_complete(field, value)
                newly_completed.append(field)
            else:
                # Update value but don't re-add to completed list
                session.extracted_fields[field] = value
        return newly_completed


# Singleton
_extractor: StructuredExtractor | None = None


def get_extractor() -> StructuredExtractor:
    global _extractor
    if _extractor is None:
        _extractor = StructuredExtractor()
    return _extractor
