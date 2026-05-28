from __future__ import annotations

import json
import re


def safe_parse_json(text: str) -> dict:
    """
    Robust JSON parser with multiple fallback strategies.
    Works across providers that sometimes return wrapped or slightly malformed JSON.
    """
    if not isinstance(text, str):
        return {}

    text = text.strip()
    if not text:
        return {}

    # Strategy 1: Direct parse
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    # Strategy 2: Extract from markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

    # Strategy 3: Find first balanced {...}
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start : i + 1]
                try:
                    parsed = json.loads(candidate)
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    pass

    # Strategy 4: last resort key-value regex
    result: dict[str, str] = {}
    kv_pattern = re.compile(r"\"(\w+)\"\s*:\s*\"([^\"]*)\"")
    for match in kv_pattern.finditer(text):
        result[match.group(1)] = match.group(2)
    return result

