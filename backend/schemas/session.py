"""
Aadhya – Session Object Model
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any, Set
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime


class ConversationStage(str, Enum):
    DISCOVERY = "DISCOVERY"
    DETAIL_COLLECTION = "DETAIL_COLLECTION"
    CONFIRMATION = "CONFIRMATION"
    SUMMARY_GENERATED = "SUMMARY_GENERATED"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)  # fields extracted on this turn


class AIThinkingTrace(BaseModel):
    """Captures the AI's decision reasoning for the admin panel."""
    turn: int
    user_message: str
    detected_fields: Dict[str, Any] = Field(default_factory=dict)
    next_field_target: Optional[str] = None
    stage_before: ConversationStage = ConversationStage.DISCOVERY
    stage_after: ConversationStage = ConversationStage.DISCOVERY
    guardrail_triggered: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    session_id: str
    phone_number: str
    channel: str = "whatsapp"              # "whatsapp" | "voice"
    # Website/service routing (business service selection; NOT the same as extracted_fields["service_type"])
    service_code: Optional[str] = None     # e.g. "IRPW02"
    persona_key: Optional[str] = None      # e.g. "marcus"
    conversation_history: List[ConversationMessage] = Field(default_factory=list)
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)  # merged flat dict of all extracted values
    completed_fields: List[str] = Field(default_factory=list)       # field names confirmed as collected
    conversation_stage: ConversationStage = ConversationStage.DISCOVERY
    thinking_traces: List[AIThinkingTrace] = Field(default_factory=list)
    summary_generated: bool = False
    # Voice only: set true on the single turn where the quest engine first returns summary_generated
    # (so Vapi can emit endCall without re-hanging-up on post-completion small-talk turns).
    voice_turn_requested_end_call: bool = False
    summary: Optional[Dict[str, Any]] = None
    # Quest-style 6-point exec brief (quest-characters `generateSixPointSummary`)
    six_point_summary: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    turn_count: int = 0

    @property
    def field_completion_pct(self) -> int:
        required = [
            "client_name", "property_type", "city", "service_type",
            "area_sqft", "configuration", "rooms_to_design",
            "budget_range", "timeline",
        ]
        done = sum(1 for f in required if f in self.completed_fields)
        return int((done / len(required)) * 100)

    def add_message(self, role: MessageRole, content: str,
                    extracted: Dict[str, Any] | None = None) -> None:
        self.conversation_history.append(
            ConversationMessage(role=role, content=content,
                                extracted_fields=extracted or {})
        )
        self.last_active = datetime.utcnow()
        if role == MessageRole.USER:
            self.turn_count += 1

    def mark_field_complete(self, field_name: str, value: Any) -> None:
        self.extracted_fields[field_name] = value
        if field_name not in self.completed_fields:
            self.completed_fields.append(field_name)
