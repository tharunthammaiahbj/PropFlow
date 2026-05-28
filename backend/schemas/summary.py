"""
Aadhya – Project Summary Schema
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class ProjectSummary(BaseModel):
    """Project Summary – Ready to Initiate"""
    session_id: str
    generated_at: datetime

    # Action
    next_step: str                           # "Call client tomorrow at 8 PM"

    # Overview
    project_overview: str                    # 1-2 sentence summary

    # Scope
    scope_of_work: List[str]                 # list of areas/services

    # Client needs
    client_requirements: str                 # style, must-haves, avoid items

    # Specs
    technical_specs: str                     # "Apartment · 1200 sqft · 3BHK · Japandi"

    # Time
    timeline: str                            # "3 months from April 2026"

    # Notes
    special_considerations: str             # kids/pets/vastu/storage combined

    # Budget + area
    estimated_scope: str                     # "Budget: ₹15L | Area: 1200 sqft"

    # NEW — AI vision statement
    design_direction: str                    # Japandi-inspired minimal home...

    # NEW — AI readiness assessment
    execution_readiness: str                 # Possession expected next month...

    # Raw enquiry snapshot
    enquiry_snapshot: dict = {}

    def formatted_text(self) -> str:
        """Returns the summary as a formatted consultant document."""
        lines = [
            "═══════════════════════════════════════════════",
            "  PROJECT SUMMARY — READY TO INITIATE",
            "  PropFlow AI • Interior Consulting",
            "═══════════════════════════════════════════════",
            "",
            f"📌 NEXT STEP",
            f"   {self.next_step}",
            "",
            f"📋 PROJECT OVERVIEW",
            f"   {self.project_overview}",
            "",
            f"🏗️  SCOPE OF WORK",
        ]
        for item in self.scope_of_work:
            lines.append(f"   • {item}")
        lines += [
            "",
            f"🎯 CLIENT REQUIREMENTS",
            f"   {self.client_requirements}",
            "",
            f"⚙️  TECHNICAL SPECS",
            f"   {self.technical_specs}",
            "",
            f"📅 TIMELINE",
            f"   {self.timeline}",
            "",
            f"⭐ SPECIAL CONSIDERATIONS",
            f"   {self.special_considerations}",
            "",
            f"💰 ESTIMATED SCOPE",
            f"   {self.estimated_scope}",
            "",
            f"🎨 DESIGN DIRECTION",
            f"   {self.design_direction}",
            "",
            f"✅ EXECUTION READINESS",
            f"   {self.execution_readiness}",
            "",
            "═══════════════════════════════════════════════",
        ]
        return "\n".join(lines)
