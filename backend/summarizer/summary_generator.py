"""
Aadhya – Project Summary Generator
Generates the full 10-section "Project Summary – Ready to Initiate" document.
Uses Gemini to write the narrative sections, then assembles the final schema.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from backend.schemas.session import Session
from backend.schemas.summary import ProjectSummary
from backend.intelligence.gemini_engine import get_gemini_engine
from backend.utils.logger import log_event


SUMMARY_GENERATION_PROMPT = """
You are Sophia Carter, Senior Interior Design Consultant at PropFlow.
Based on the enquiry data below, generate a professional Project Summary.

ENQUIRY DATA:
{enquiry_data}

Generate the following sections. Be specific, warm, and professional.
Return ONLY valid JSON with these exact keys:

{{
  "next_step": "One clear action line (e.g., 'Call client on Monday at 7 PM to confirm site visit date')",
  "project_overview": "1-2 sentences summarizing property type, area, style, budget, and timeline",
  "scope_of_work": ["list", "of", "areas", "and", "services"],
  "client_requirements": "Style preferences, must-haves, and items to avoid in one paragraph",
  "technical_specs": "Format: PropertyType · Area sqft · Configuration · DesignStyle (e.g., 'Apartment · 1400 sqft · 3BHK · Contemporary')",
  "timeline": "e.g., '3 months from April 2026' or 'Design to begin after possession in June 2026'",
  "special_considerations": "Combine notes on kids/pets/vastu/storage/elderly into one paragraph",
  "estimated_scope": "Format: 'Budget: ₹15 Lakh | Area: 1400 sqft'",
  "design_direction": "1-2 sentence evocative design vision statement (e.g., 'A Japandi-inspired sanctuary with warm natural woods, clean lines, and soft ambient lighting that breathes calm into every corner.')",
  "execution_readiness": "1-2 sentence assessment of readiness to begin (e.g., 'Client possession is confirmed for next month; design planning can begin immediately. Budget is allocated and scope is well-defined.')"
}}
"""


class SummaryGenerator:

    def __init__(self):
        self.engine = get_gemini_engine()

    async def generate(self, session: Session) -> ProjectSummary:
        """
        Generate a complete project summary from session data.
        """
        enquiry_data = self._format_enquiry_data(session)
        prompt = SUMMARY_GENERATION_PROMPT.format(enquiry_data=enquiry_data)

        raw = await self.engine.extract_json(
            session_id=session.session_id,
            extraction_prompt=prompt,
        )

        # Build summary with fallbacks for any missing keys
        summary = ProjectSummary(
            session_id=session.session_id,
            generated_at=datetime.utcnow(),
            next_step=raw.get("next_step", "Our team will reach out within 24 hours to schedule a consultation."),
            project_overview=raw.get("project_overview", self._build_fallback_overview(session)),
            scope_of_work=raw.get("scope_of_work", self._build_fallback_scope(session)),
            client_requirements=raw.get("client_requirements", "To be confirmed during consultation."),
            technical_specs=raw.get("technical_specs", self._build_technical_specs(session)),
            timeline=raw.get("timeline", session.extracted_fields.get("timeline", "To be confirmed.")),
            special_considerations=raw.get("special_considerations", self._build_special_notes(session)),
            estimated_scope=raw.get("estimated_scope", self._build_estimated_scope(session)),
            design_direction=raw.get("design_direction", "A thoughtfully curated home that reflects the client's unique personality and lifestyle."),
            execution_readiness=raw.get("execution_readiness", "Design planning can begin following team confirmation."),
            enquiry_snapshot=session.extracted_fields,
        )

        await log_event("SUMMARY_GENERATED", session_id=session.session_id,
                        data={"project_overview": summary.project_overview[:100]})

        return summary

    def _format_enquiry_data(self, session: Session) -> str:
        ef = session.extracted_fields
        lines = []
        for k, v in ef.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines) if lines else "  (minimal data collected)"

    def _build_fallback_overview(self, session: Session) -> str:
        ef = session.extracted_fields
        parts = []
        if ef.get("property_type"):
            parts.append(ef["property_type"].title())
        if ef.get("configuration"):
            parts.append(ef["configuration"])
        if ef.get("city"):
            parts.append(f"in {ef['city']}")
        if ef.get("area_sqft"):
            parts.append(f"({ef['area_sqft']} sqft)")
        if ef.get("budget_range"):
            parts.append(f"with a budget of {ef['budget_range']}")
        return " ".join(parts) if parts else "Residential interior design project."

    def _build_fallback_scope(self, session: Session) -> list[str]:
        ef = session.extracted_fields
        scope = []
        rooms = ef.get("rooms_to_design", [])
        if rooms:
            scope.extend(rooms if isinstance(rooms, list) else [rooms])
        if ef.get("kitchen_type"):
            scope.append(f"Modular Kitchen ({ef['kitchen_type']})")
        if ef.get("false_ceiling_required"):
            scope.append("False Ceiling Design")
        if ef.get("wardrobe_count"):
            scope.append(f"Wardrobes (x{ef['wardrobe_count']})")
        return scope or ["Full Home Interior Design"]

    def _build_technical_specs(self, session: Session) -> str:
        ef = session.extracted_fields
        parts = [
            ef.get("property_type", "Property").title(),
            f"{ef['area_sqft']} sqft" if ef.get("area_sqft") else "",
            ef.get("configuration", ""),
            ef.get("design_style", "").title() if ef.get("design_style") else "",
        ]
        return " · ".join(p for p in parts if p)

    def _build_special_notes(self, session: Session) -> str:
        ef = session.extracted_fields
        notes = []
        if ef.get("kids"):
            notes.append("Child-safe design required")
        if ef.get("pets"):
            notes.append("Pet-friendly materials preferred")
        if ef.get("elderly"):
            notes.append("Senior-friendly accessibility needed")
        if ef.get("vastu_importance"):
            notes.append(f"Vastu: {ef['vastu_importance']}")
        if ef.get("storage_priority"):
            notes.append(f"Storage priority: {ef['storage_priority']}")
        if ef.get("pooja_room"):
            notes.append("Pooja room to be designed")
        return "; ".join(notes) if notes else "No special considerations noted."

    def _build_estimated_scope(self, session: Session) -> str:
        ef = session.extracted_fields
        budget = ef.get("budget_range", "TBD")
        area = ef.get("area_sqft", "TBD")
        return f"Budget: {budget} | Area: {area} sqft"


_generator: Optional[SummaryGenerator] = None


def get_summary_generator() -> SummaryGenerator:
    global _generator
    if _generator is None:
        _generator = SummaryGenerator()
    return _generator
