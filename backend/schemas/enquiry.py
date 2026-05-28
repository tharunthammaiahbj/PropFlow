"""
Aadhya – Structured Enquiry Payload Schema
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


class ClientInfo(BaseModel):
    client_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    contact_pref: Optional[str] = None
    callback_time: Optional[str] = None


class PropertyInfo(BaseModel):
    property_type: Optional[str] = None      # apartment / villa / independent house / plot
    project_name: Optional[str] = None
    location: Optional[str] = None
    area_sqft: Optional[str] = None
    configuration: Optional[str] = None      # 1BHK / 2BHK / 3BHK / 4BHK / etc.
    floor_number: Optional[str] = None
    possession_status: Optional[str] = None  # ready / under-construction / renovation


class InteriorScope(BaseModel):
    service_type: Optional[str] = None       # full-home / partial / single-room / renovation
    rooms_to_design: Optional[List[str]] = None
    kitchen_type: Optional[str] = None       # modular / semi-modular / open
    wardrobe_count: Optional[int] = None
    false_ceiling_required: Optional[bool] = None
    lighting_plan: Optional[bool] = None


class DesignVision(BaseModel):
    design_style: Optional[str] = None       # modern / contemporary / traditional / bohemian / japandi
    color_preferences: Optional[List[str]] = None
    reference_images: Optional[List[str]] = None
    design_inspiration_words: Optional[List[str]] = None


class Constraints(BaseModel):
    budget_range: Optional[str] = None       # e.g. "10-15 lakh"
    timeline: Optional[str] = None           # e.g. "3 months"
    preferred_start: Optional[str] = None
    must_have_features: Optional[List[str]] = None
    avoid_items: Optional[List[str]] = None


class SpecialConsiderations(BaseModel):
    kids: Optional[bool] = None
    pets: Optional[bool] = None
    elderly: Optional[bool] = None
    vastu_importance: Optional[str] = None   # strict / flexible / not-important
    storage_priority: Optional[str] = None   # high / medium / low
    pooja_room: Optional[bool] = None


class EnquiryPayload(BaseModel):
    """Complete structured enquiry collected from conversation."""
    client: ClientInfo = ClientInfo()
    property: PropertyInfo = PropertyInfo()
    scope: InteriorScope = InteriorScope()
    vision: DesignVision = DesignVision()
    constraints: Constraints = Constraints()
    special: SpecialConsiderations = SpecialConsiderations()

    def flat_dict(self) -> dict:
        """Returns a flat dict of all fields for easy display."""
        result = {}
        for section in [self.client, self.property, self.scope,
                        self.vision, self.constraints, self.special]:
            result.update({k: v for k, v in section.model_dump().items() if v is not None})
        return result
