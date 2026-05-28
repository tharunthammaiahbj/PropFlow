"""
Aadhya – Twilio WhatsApp Sender
"""
from __future__ import annotations
from backend.config import get_settings

settings = get_settings()
_twilio_client = None


def _get_client():
    global _twilio_client
    if _twilio_client is None:
        try:
            from twilio.rest import Client
            _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        except Exception as e:
            print(f"[Twilio] Client init error: {e}")
    return _twilio_client


async def send_whatsapp_message(to: str, body: str) -> bool:
    """
    Send a WhatsApp message via Twilio REST API.
    'to' should be in format 'whatsapp:+91...'
    """
    client = _get_client()
    if not client:
        print(f"[Twilio] Not configured — would send to {to}: {body[:80]}")
        return False
    try:
        from backend.utils.retry import with_retry
        await with_retry(
            _send_once,
            client=client,
            to=to,
            body=body,
            session_id=to,
        )
        return True
    except Exception as e:
        print(f"[Twilio] Send error: {e}")
        return False


async def _send_once(client, to: str, body: str, session_id: str = ""):
    # Twilio client is sync — run in executor
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=to,
            body=body,
        )
    )


def twiml_response(body: str) -> str:
    """Build a TwiML XML response string."""
    # Escape XML special chars
    safe = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Message>' + safe + '</Message></Response>'
    )
