from __future__ import annotations

# Mirrors quest-characters/apps/questionnaire/src/service-codes.ts
SERVICE_CODE_TO_ID: dict[str, str] = {
    "CIRC01": "residential_construction",
    "IRRI01": "residential_interiors",
    "IRPW02": "painting",
    "CIEL03": "electrical_services",
    "CIPL02": "plumbing_services",
    "SESR01": "solar_services",
    "PSEM01": "event_management",
    "RPPD01": "property_development",
    "HASH01": "home_automation",
    "AAFI01": "farm_infrastructure",
    "AAIA02": "irrigation_automation",
    # Commercial mapping used by service-agents routing
    "CICC04": "commercial_construction",
    "IRCI03": "commercial_interiors",
}

SERVICE_CODE_TO_CHARACTER_NAME: dict[str, str] = {
    "CIRC01": "Ryan Carter",
    "IRRI01": "Sophia Carter",
    "IRPW02": "Marcus Webb",
    "CIEL03": "Ethan Brooks",
    "CIPL02": "James Mitchell",
    "SESR01": "Claire Foster",
    "PSEM01": "Emma Collins",
    "RPPD01": "Daniel Hayes",
    "HASH01": "Lily Grant",
    "AAFI01": "Noah Bennett",
    "AAIA02": "Liam Parker",
    "CICC04": "Tyler Stone",
    "IRCI03": "Natalie Rhodes",
}

SERVICE_ID_TO_CODE: dict[str, str] = {
    v: k for k, v in SERVICE_CODE_TO_ID.items()
}


def normalize_service_input(service: str) -> tuple[str | None, str]:
    raw = str(service or "").strip()
    upper = raw.upper()
    service_id = SERVICE_CODE_TO_ID.get(upper, raw)
    code = upper if upper in SERVICE_CODE_TO_ID else None
    return code, service_id


def resolve_service_id(service: str) -> str:
    _, service_id = normalize_service_input(service)
    return service_id


def get_display_name_by_service_code(service: str, default_name: str) -> str:
    code, service_id = normalize_service_input(service)
    code_for_lookup = code or SERVICE_ID_TO_CODE.get(service_id)
    if code_for_lookup and code_for_lookup in SERVICE_CODE_TO_CHARACTER_NAME:
        return SERVICE_CODE_TO_CHARACTER_NAME[code_for_lookup]
    return default_name
