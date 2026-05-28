"""
Aadhya – Gemini Intelligence Engine
Wraps Google Gemini API (google-genai SDK) with per-session conversation history.
"""
from __future__ import annotations
import json
from typing import Optional

from google import genai
from google.genai import types

from backend.config import get_settings
from backend.utils.logger import log_event
from backend.utils.retry import with_retry

settings = get_settings()

# Initialize client
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options={'api_version': 'v1beta'}
        )
    return _client


class GeminiEngine:
    """
    Manages Gemini chat sessions per user.
    Maintains conversation history in-process (backed by session store).
    """

    def __init__(self):
        self.model_name = settings.gemini_model

    async def chat(
        self,
        session_id: str,
        user_message: str,
        system_prompt: str,
        history: list[dict],
    ) -> str:
        """
        Send a message to Gemini and get a response.

        Args:
            session_id: For logging
            user_message: The user's latest message
            system_prompt: Full system prompt (persona + context injection)
            history: List of {"role": "user"|"model", "parts": [{"text": "..."}]}

        Returns:
            AI response text
        """
        return await with_retry(
            self._chat_once,
            session_id,
            user_message,
            system_prompt,
            history,
            session_id=session_id,
        )

    async def _chat_once(
        self,
        session_id: str,
        user_message: str,
        system_prompt: str,
        history: list[dict],
    ) -> str:
        import asyncio
        client = _get_client()

        # Build contents list
        contents = []
        for item in history:
            role = item.get("role", "user")
            text = item.get("parts", [{}])[0].get("text", "")
            contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.85,
            top_p=0.95,
            max_output_tokens=512,
        )

        # Run sync Gemini call in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        )

        text = response.text.strip() if response.text else ""
        await log_event("GEMINI_RESPONSE", session_id=session_id,
                        data={"response_preview": text[:120]})
        return text

    async def extract_json(
        self,
        session_id: str,
        extraction_prompt: str,
    ) -> dict:
        """
        Call Gemini in JSON-output mode for structured field extraction.
        Returns parsed dict or {} on failure.
        """
        import asyncio
        import re
        try:
            client = _get_client()
            config = types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
                response_mime_type="application/json",
            )
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self.model_name,
                    contents=extraction_prompt,
                    config=config,
                )
            )
            text = response.text.strip() if response.text else "{}"
            return self._safe_parse_json(text)
        except (json.JSONDecodeError, Exception) as e:
            await log_event("API_ERROR", session_id=session_id,
                            data={"error": str(e), "phase": "json_extraction"})
            return {}

    def _safe_parse_json(self, text: str) -> dict:
        """
        Robust JSON parser with multiple fallback strategies.
        Gemini 3 Flash Preview sometimes returns slightly malformed JSON.
        """
        import re

        # Strategy 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code fences
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Strategy 3: Find the first {...} block in the text
        brace_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Strategy 4: Try to find nested JSON with balanced braces
        depth = 0
        start = None
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass

        # Strategy 5: Extract key-value pairs via regex as last resort
        result = {}
        kv_pattern = re.compile(r'"(\w+)"\s*:\s*"([^"]*)"')
        for match in kv_pattern.finditer(text):
            result[match.group(1)] = match.group(2)
        return result

    def build_history(self, conversation_history: list) -> list[dict]:
        """
        Convert Session.conversation_history → Gemini API history format.
        Excludes system messages.
        """
        history = []
        for msg in conversation_history:
            if msg.role in ("user", "assistant"):
                role = "model" if msg.role == "assistant" else "user"
                history.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })
        return history


# Singleton
_engine: Optional[GeminiEngine] = None


def get_gemini_engine() -> GeminiEngine:
    global _engine
    if _engine is None:
        _engine = GeminiEngine()
    return _engine
