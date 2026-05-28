"""
Per-service coverage (required fields) — port of quest-characters
apps/questionnaire/src/engine/coverage-policy.ts
"""
from __future__ import annotations

from typing import Any

from backend.questionnaire.generated.service_parameters_generated import SERVICE_PARAMS


DEFAULT_REQUIRED = [
    "project_type",
    "rooms",
    "size_sqft",
    "style",
    "budget",
    "timeline",
    "contact_pref",
    "preferred_start",
]

DEFAULT_OPTIONAL = [
    "must_haves",
    "avoid",
    "site_ready",
    "storage_needs",
    "lighting_pref",
    "notes",
    "moodboard_refs",
    "special_zones",
    "material_preference",
]


def has_service_params(service: str) -> bool:
    return service in SERVICE_PARAMS


def get_required_fields_for_service(service: str) -> list[str]:
    if has_service_params(service):
        ids = [p["id"] for p in SERVICE_PARAMS[service]["required"]]
        if ids:
            # Policy: callback_time is not collected (voice/WA). Never require it.
            return [i for i in ids if i != "callback_time"]
    return list(DEFAULT_REQUIRED)


def get_optional_fields_for_service(service: str) -> list[str]:
    if has_service_params(service):
        ids = [p["id"] for p in SERVICE_PARAMS[service]["optional"]]
        if ids:
            return [i for i in ids if i != "callback_time"]
    return list(DEFAULT_OPTIONAL)


def get_coverage_policy_for_service(service: str) -> dict[str, Any]:
    return {
        "required": get_required_fields_for_service(service),
        "optional": get_optional_fields_for_service(service),
    }


def is_coverage_satisfied(parameters: dict[str, Any], service: str) -> bool:
    required = get_required_fields_for_service(service)
    for fid in required:
        val = parameters.get(fid)
        if val is None:
            return False
        if isinstance(val, dict) and "value" in val:
            if val.get("value") is None:
                return False
    return True
