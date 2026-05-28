"""
Aadhya – AI Interior Design Consultant
Configuration via environment variables (Pydantic Settings)
"""
from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    _BACKEND_DIR = Path(__file__).resolve().parent
    model_config = SettingsConfigDict(
        # Use absolute paths so configuration works regardless of current working directory.
        # Prefer backend/.env, but allow a repo-root .env as a fallback.
        env_file=(
            str(_BACKEND_DIR / ".env"),
            str(_BACKEND_DIR.parent / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Universal LLM routing
    # - LLM_PROVIDER can be: "gemini", "openai_compat"
    # - LLM_FALLBACKS is a comma-separated list, e.g. "gemini,openai_compat"
    llm_provider: str = "gemini"
    llm_fallbacks: str = "gemini,openai_compat"

    # OpenAI-compatible provider (OpenAI / OpenRouter / Groq / etc.)
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    # Reasoning effort for reasoning-capable models (Groq's gpt-oss-*, OpenAI o-series, etc.).
    # Allowed values: "none", "low", "medium", "high".
    # CRITICAL for gpt-oss-20b on Groq: without "low" (or "none"), the model spends every
    # max_tokens on hidden chain-of-thought tokens that the API strips before returning,
    # leaving `content=""`. That single bug causes empty classifier replies, empty
    # extraction JSON, and empty assistant turns ("One moment, I didn't catch that").
    # Set to "" / "auto" to omit the parameter (use for non-reasoning models).
    openai_reasoning_effort: str = "low"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # Vapi
    vapi_api_key: str = ""
    vapi_assistant_id: str = ""

    # TTS (used by Vapi assistant config)
    # Supported: "cartesia", "11labs"
    tts_provider: str = "cartesia"

    # Cartesia
    # Note: API key is typically configured in the Vapi dashboard integration,
    # but we keep these settings so the assistant config can be controlled by env.
    cartesia_voice_id: str = ""
    cartesia_model: str = "sonic-3"

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    # ElevenLabs TTS model to use via Vapi (recommended: eleven_multilingual_v2 or eleven_flash_v2_5)
    elevenlabs_voice_model: str = "eleven_multilingual_v2"

    # Deepgram (Vapi transcriber)
    # Use "multi" for automatic language detection in realtime calls.
    deepgram_language: str = "multi"

    # Vapi Custom LLM streaming
    # When enabled, /webhook/vapi/chat/completions will stream incremental tokens
    # (OpenAI-compatible SSE) instead of waiting for the full response.
    vapi_true_streaming: bool = True
    # Flush buffered text after this many characters if no punctuation boundary appears.
    # Lower values reach TTS sooner (better perceived latency).
    vapi_stream_flush_chars: int = 28
    # Minimum buffered length before flushing on punctuation (.?! newline).
    vapi_stream_boundary_min_chars: int = 12
    # After extraction, stream main assistant tokens to Vapi (provider must support chat_stream; else one chunk).
    voice_stream_main_llm: bool = True
    # Voice-only: max_tokens for project + six-point summary LLMs (JSON; 2048 is usually wasteful).
    summary_max_output_tokens_voice: int = 768
    # Voice-only completion: await project summary only, use sync fallback six-point, then LLM six-point in background.
    # Off by default so completion webhooks / payloads match the classic two-LLM path unless you opt in.
    voice_defer_six_point_summary: bool = False

    # Upstash Redis
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    session_ttl_hours: int = 24

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Quest parity: POST JSON on questionnaire completion (same idea as quest `QUESTIONNAIRE_WEBHOOK_URL`).
    # Set QUESTIONNAIRE_WEBHOOK_URL to your platform ingest URL; leave empty to disable.
    questionnaire_webhook_url: str = ""
    # Optional: Post Quest-style enquiry payload (conversationFlow + summary) to an external backend.
    # This is separate from QUESTIONNAIRE_WEBHOOK_URL so you can integrate with a different system safely.
    enquiry_webhook_url: str = ""
    enquiry_webhook_user_id: str = ""
    enquiry_webhook_service_id: str = ""
    enquiry_webhook_service_name: str = ""
    # Optional: Authorization bearer token for ENQUIRY_WEBHOOK_URL (e.g. devapi.propflow.com/users/api/enquiries).
    enquiry_webhook_bearer_token: str = ""
    # When true, refuse to POST to ENQUIRY_WEBHOOK_URL unless a bearer token is configured.
    # Prevents silent 401/400 loops against an auth-required PM backend.
    enquiry_webhook_require_auth: bool = False

    # Admin
    admin_password: str = "changeme"
    admin_api_key: str = "changeme"

    # App
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 8000
    # When true, logs QUEST_REPLY_PIPELINE (raw vs humanized lengths and text) per quest assistant turn.
    # Enable on Railway via LOG_QUEST_REPLY_PIPELINE=1 to debug cut-off replies; disable afterward.
    log_quest_reply_pipeline: bool = False
    # When true, logs QUEST_TURN_TIMING (opening / extraction / reply / summary ms) per process_quest_turn.
    log_quest_turn_timing: bool = False
    # When true, logs LLM_CALL_METRICS (per-call ms, tokens, phase) and CHANNEL_TURN_TIMING (WhatsApp segments).
    log_perf_analytics: bool = False
    # Active consultant persona ("sophia" or "ryan")
    consultant_persona: str = "sophia"
    # Public-facing base URL — used by Vapi to self-reference the webhook URL
    # Set this to your deployed domain, e.g. https://propflow.onrender.com
    base_url: str = "http://localhost:8000"
    # Allowed CORS origins — comma-separated list, e.g. https://admin.propflow.com
    # Use * only during local development
    cors_origins: str = "*"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS env var into a list."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
