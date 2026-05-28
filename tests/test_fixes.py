"""
Aadhya – Unit Tests for Issue Fixes
Covers the 6 issues resolved in the repo analysis.
"""
import pytest
import os


# ─── 1. Config — BASE_URL and CORS_ORIGINS settings ───────────────────────────

def test_base_url_default():
    """BASE_URL defaults to localhost when env var not set."""
    os.environ.pop("BASE_URL", None)
    # Re-import with fresh cache
    from importlib import reload
    import backend.config as cfg_module
    cfg_module.get_settings.cache_clear()
    settings = cfg_module.Settings()
    assert settings.base_url == "http://localhost:8000"


def test_cors_origins_list_wildcard():
    """When CORS_ORIGINS=*, cors_origins_list returns ['*']."""
    from importlib import reload
    import backend.config as cfg_module
    s = cfg_module.Settings(cors_origins="*")
    assert s.cors_origins_list == ["*"]


def test_cors_origins_list_custom():
    """Comma-separated CORS_ORIGINS are split into a proper list."""
    import backend.config as cfg_module
    s = cfg_module.Settings(
        cors_origins="https://admin.propflow.com, https://propflow.com"
    )
    result = s.cors_origins_list
    assert "https://admin.propflow.com" in result
    assert "https://propflow.com" in result
    assert len(result) == 2


# ─── 2. Vapi handler — base_url used for model URL ────────────────────────────

def test_vapi_model_url_uses_base_url(monkeypatch):
    """Vapi assistant config URL should use settings.base_url, not a hardcoded placeholder."""
    import backend.config as cfg_module
    cfg_module.get_settings.cache_clear()
    monkeypatch.setenv("BASE_URL", "https://aadhya.propflow.com")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    # Re-read settings now that env is patched
    cfg_module.get_settings.cache_clear()

    from backend.agents.voice.vapi_handler import _assistant_config_response
    config = _assistant_config_response("Hello!")
    url = config["assistant"]["model"]["url"]

    assert "your-deployed-url" not in url, "Hardcoded placeholder URL still present!"
    assert "propflow.com" in url or "localhost" in url
    assert url.endswith("/webhook/vapi/chat/completions")


# ─── 3. Vapi handler — CALL_ENDED event on call end ──────────────────────────

@pytest.mark.asyncio
async def test_call_ended_event_logged(monkeypatch):
    """end-of-call-report must emit CALL_ENDED, not SESSION_START."""
    logged_events = []

    async def mock_log_event(event, session_id="system", data=None):
        logged_events.append(event)

    monkeypatch.setattr("backend.agents.voice.vapi_handler.log_event", mock_log_event)

    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)

    payload = {
        "message": {
            "type": "end-of-call-report",
        },
        "call": {
            "id": "test_call_001",
        }
    }
    response = client.post("/webhook/vapi", json=payload)
    assert response.status_code == 200
    assert "CALL_ENDED" in logged_events, (
        f"Expected CALL_ENDED, got: {logged_events}"
    )
    assert "SESSION_START" not in logged_events, (
        "SESSION_START incorrectly logged for call-end event!"
    )


# ─── 4. Guardrail — off-topic detection ───────────────────────────────────────

def test_off_topic_guardrail():
    """Off-topic keywords trigger the guardrail check."""
    from backend.intelligence.conversation_controller import _is_off_topic
    assert _is_off_topic("what is the current stock price?") is True
    assert _is_off_topic("I need a 3BHK design in Bengaluru") is False
    assert _is_off_topic("bitcoin investment advice") is True
    assert _is_off_topic("I want modular kitchen") is False


# ─── 5. Budget anxiety detection ──────────────────────────────────────────────

def test_budget_anxiety_detection():
    """Budget anxiety phrases are correctly detected."""
    from backend.intelligence.conversation_controller import _has_budget_anxiety
    assert _has_budget_anxiety("it feels too expensive for me") is True
    assert _has_budget_anxiety("I am worried about cost") is True
    assert _has_budget_anxiety("I have a 15 lakh budget") is False
    assert _has_budget_anxiety("can't afford much right now") is True


# ─── 6. Redis SCAN — no KEYS in list_session_ids ─────────────────────────────

def test_redis_scan_not_keys():
    """list_session_ids() must not use the KEYS command."""
    import inspect
    import backend.storage.redis_store as redis_module
    source = inspect.getsource(redis_module.RedisStore.list_session_ids)
    assert "\"KEYS\"" not in source and "'KEYS'" not in source, (
        "Blocking KEYS command still used in list_session_ids!"
    )
    assert "SCAN" in source, "SCAN not found in list_session_ids implementation!"
