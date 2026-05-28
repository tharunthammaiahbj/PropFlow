from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ServiceRouting:
    service_code: str
    persona_key: str


# Canonical mapping for website-listed services.
# Frontend should send `service_code` (e.g. IRPW02) and backend resolves `persona_key`.
SERVICE_CODE_TO_PERSONA_KEY: dict[str, str] = {
    # Construction & Infrastructure
    "CIRC01": "ryan",
    "CIEL03": "ethan",
    "CIPL02": "james",
    "CICC04": "tyler",
    # Interiors & Renovation
    "IRRI01": "sophia",
    "IRPW02": "marcus",
    "IRCI03": "natalie",
    # Solar & Energy
    "SESR01": "claire",
    # Professional & Service Industries
    "PSEM01": "emma",
    # Real Estate & Property
    "RPPD01": "daniel",
    # Home Automation
    "HASH01": "lily",
    "HSEM03": "lily",
    "HASS02": "lily",
    # Agriculture & Agritech
    "AAFI01": "noah",
    "AAIA02": "liam",
}


def normalize_service_code(service_code: str | None) -> str | None:
    if not service_code:
        return None
    s = str(service_code).strip().upper()
    return s or None


def resolve_persona_key(service_code: str | None) -> Optional[str]:
    """
    Resolve a persona key from a service code.
    Returns None when service code is missing or not mapped.
    """
    code = normalize_service_code(service_code)
    if not code:
        return None
    return SERVICE_CODE_TO_PERSONA_KEY.get(code)


# ──────────────────────────────────────────────────────────────────────────────
# Quest-services-only registry for RouterEngine (Phase 1 voice-only)
#
# We route ONLY to existing quest service IDs already supported by the quest engine.
# Session routing tags are stored in Session.extracted_fields:
# - "__quest:service_id": quest service id (used by quest engine)
# - "__router:service_id": same quest service id (auditing / admin)
# - Session.persona_key is set to a persona key that maps to persona.py identities.
# ──────────────────────────────────────────────────────────────────────────────

# Canonical set of quest service IDs present in this repo (questionnaire supports these end-to-end).
QUEST_SERVICE_IDS: tuple[str, ...] = (
    "residential_interiors",
    "residential_construction",
    "painting",
    "solar_services",
    "plumbing_services",
    "electrical_services",
    "home_automation",
    "commercial_interiors",
    "commercial_construction",
    "property_development",
    "event_management",
    "farm_infrastructure",
    "irrigation_automation",
)

# Router will always fall back to an existing quest service.
DEFAULT_QUEST_SERVICE_ID = "residential_interiors"

# If RouterEngine produces "router ids" for logs or testing, translate them here.
ROUTER_TO_QUEST_ID: dict[str, str] = {
    # Home services (map to existing quest services)
    "interior_design": "residential_interiors",
    "construction": "residential_construction",
    "painting": "painting",
    "solar_rooftop": "solar_services",
    "plumbing": "plumbing_services",
    "electrical": "electrical_services",
    "home_automation": "home_automation",
    # Commercial / professional services (already exist in quest)
    "commercial_interiors": "commercial_interiors",
    "commercial_construction": "commercial_construction",
    "property_development": "property_development",
    "event_management": "event_management",
    # Agriculture (already exist in quest)
    "farm_infrastructure": "farm_infrastructure",
    "irrigation_automation": "irrigation_automation",
}

# Quest-service registry used by RouterEngine for keyword routing + persona assignment.
# - service_id: quest service id (used by quest engine via "__quest:service_id")
# - persona_key: must match persona.py keys (falls back to "sophia" when unknown)
# - keywords: used only by tier-1 trie routing (lowercase; avoid duplicates across services)
QUEST_SERVICE_REGISTRY: dict[str, dict] = {
    "residential_interiors": {
        "service_id": "residential_interiors",
        "webhook_service_name": "Residential Interiors",
        "persona_key": "sophia",
        "closing_voice": "Perfect — I've created your interiors project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "interior",
            "interiors",
            "interior design",
            "design my home",
            "home design",
            "home interiors",
            "house interior",
            "flat interior",
            "apartment interior",
            "villa interior",
            "2bhk",
            "3bhk",
            "living room",
            "bedroom",
            "wardrobe",
            "tv unit",
            "storage",
            "space planning",
            "vastu",
            "pooja room",
        ],
    },
    "residential_construction": {
        "service_id": "residential_construction",
        "webhook_service_name": "Residential Construction",
        "persona_key": "ryan",
        "closing_voice": "Perfect — I've created your construction project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "construction",
            "construct",
            "build house",
            "build home",
            "new house",
            "new home",
            "site",
            "plot",
            "foundation",
            "rcc",
            "structure",
            "g+1",
            "g+2",
            "floors",
            "soil test",
            "bbmp",
            "plan approval",
        ],
    },
    "painting": {
        "service_id": "painting",
        "webhook_service_name": "Painting & Finishes",
        "persona_key": "marcus",
        "closing_voice": "Perfect — I've created your painting project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "painting",
            "paint",
            "repaint",
            "wall paint",
            "house painting",
            "interior painting",
            "exterior painting",
            "texture",
            "putty",
            "primer",
            "damp paint",
            "peeling",
            "cracks",
            "rang",
            "color",
            "colour",
        ],
    },
    "solar_services": {
        "service_id": "solar_services",
        "webhook_service_name": "Solar Services",
        "persona_key": "claire",
        "closing_voice": "Perfect — I've created your solar project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "solar",
            "solar rooftop",
            "rooftop solar",
            "solar panel",
            # Common Deepgram/Vapi mishears for "solar" in fast speech
            "so a lot",
            "so alot",
            "so large",
            "solor",
            "sollar",
            "pv",
            "net metering",
            "on grid",
            "off grid",
            "hybrid solar",
            "inverter solar",
            "units",
            "bill",
            "electricity bill",
            "subsidy",
            "mnre",
        ],
    },
    "plumbing_services": {
        "service_id": "plumbing_services",
        "webhook_service_name": "Plumbing Services",
        "persona_key": "james",
        "closing_voice": "Perfect — I've created your plumbing project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "plumbing",
            "plumber",
            "pipeline",
            "pipe",
            "leak",
            "leakage",
            "tap",
            "faucet",
            "flush",
            "commode",
            "bathroom leak",
            "blocked",
            "clog",
            "drain",
            "paani",
            "water leak",
        ],
    },
    "electrical_services": {
        "service_id": "electrical_services",
        "webhook_service_name": "Electrical Services",
        "persona_key": "ethan",
        "closing_voice": "Perfect — I've created your electrical project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "electrical",
            "electrician",
            "wiring",
            "rewiring",
            "short circuit",
            "mcb",
            "elcb",
            "switch",
            "socket",
            "points",
            "load",
            "inverter",
            "earthing",
            "power trip",
            "bijli",
            "current",
        ],
    },
    "home_automation": {
        "service_id": "home_automation",
        "webhook_service_name": "Home Automation",
        "persona_key": "lily",
        "closing_voice": "Perfect — I've created your home automation project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "automation",
            "smart home",
            "smart switch",
            "smart lights",
            "smart lighting",
            "alexa",
            "google home",
            "voice control",
            "iot",
            "zigbee",
            "z-wave",
            "knx",
            "smart lock",
            "cctv",
            "camera",
            "scene",
        ],
    },
    "commercial_interiors": {
        "service_id": "commercial_interiors",
        "webhook_service_name": "Commercial Interiors & Fit-Out",
        "persona_key": "natalie",
        "closing_voice": "Perfect — I've created your commercial interiors project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "commercial interiors",
            "fitout",
            "fit-out",
            "office interior",
            "office interiors",
            "workspace",
            "reception",
            "workstations",
            "partition",
            "acoustic",
            "restaurant interior",
            "clinic interior",
            "retail fitout",
            "brand theme",
        ],
    },
    "commercial_construction": {
        "service_id": "commercial_construction",
        "webhook_service_name": "Commercial Construction",
        "persona_key": "tyler",
        "closing_voice": "Perfect — I've created your commercial construction project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "commercial construction",
            "warehouse",
            "shed",
            "industrial shed",
            "factory",
            "commercial building",
            "site execution",
            "contractor",
            "civil work",
            "retail outlet",
            "office build",
            "hand over",
            "turnkey",
        ],
    },
    "property_development": {
        "service_id": "property_development",
        "webhook_service_name": "Property Development",
        "persona_key": "daniel",
        "closing_voice": "Perfect — I've created your property development project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "property development",
            "builder",
            "developer",
            "project coordination",
            "vendor",
            "milestone",
            "boq",
            "delivery",
            "multi vendor",
            "apartment building",
            "tenant improvement",
            "shell and core",
        ],
    },
    "event_management": {
        "service_id": "event_management",
        "webhook_service_name": "Event Management",
        "persona_key": "emma",
        "closing_voice": "Perfect — I've created your event project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "event",
            "event management",
            "wedding",
            "engagement",
            "birthday",
            "corporate event",
            "conference",
            "decor",
            "decoration",
            "stage",
            "sound",
            "dj",
            "catering",
            "venue",
        ],
    },
    "farm_infrastructure": {
        "service_id": "farm_infrastructure",
        "webhook_service_name": "Farm Infrastructure",
        "persona_key": "noah",
        "closing_voice": "Perfect — I've created your farm infrastructure project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "farm",
            "farmland",
            "fencing",
            "farm shed",
            "pump house",
            "borewell",
            "pipeline farm",
            "drip",
            "sprinkler",
            "greenhouse",
            "polyhouse",
            "shade net",
            "irrigation",
            "tank",
            "reservoir",
        ],
    },
    "irrigation_automation": {
        "service_id": "irrigation_automation",
        "webhook_service_name": "Irrigation Automation",
        "persona_key": "liam",
        "closing_voice": "Perfect — I've created your irrigation automation project in our system. The right PropFlow vendor will contact you shortly.",
        "keywords": [
            "irrigation automation",
            "automation irrigation",
            "smart irrigation",
            "soil moisture",
            "controller",
            "valve",
            "solenoid",
            "sensor",
            "timer irrigation",
            "fertigation",
            "iot irrigation",
            "drip automation",
            "zone",
            "schedule",
        ],
    },
}
