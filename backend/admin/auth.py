"""
Aadhya – Admin Panel Authentication
Simple .env-based password + API key protection for /krsna routes.
"""
from __future__ import annotations
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import APIKeyHeader

from backend.config import get_settings

settings = get_settings()

# ─── Simple token store (in-memory, resets on restart) ───────────────────────
_active_tokens: dict[str, datetime] = {}
TOKEN_EXPIRY_HOURS = 8
API_KEY_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def generate_session_token() -> str:
    token = secrets.token_urlsafe(32)
    _active_tokens[token] = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    return token


def invalidate_token(token: str):
    _active_tokens.pop(token, None)


def is_valid_token(token: str) -> bool:
    expiry = _active_tokens.get(token)
    if not expiry:
        return False
    if datetime.utcnow() > expiry:
        _active_tokens.pop(token, None)
        return False
    return True


# ─── FastAPI dependencies ─────────────────────────────────────────────────────

async def verify_admin_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)):
    """Dependency: validates X-Admin-Key header against ADMIN_API_KEY env var."""
    if api_key and api_key == settings.admin_api_key:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing admin API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def verify_session_token(request: Request):
    """Dependency: validates Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if is_valid_token(token):
            return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session token",
    )


# Either API key or session token is acceptable
async def require_admin(
    request: Request,
    api_key: Optional[str] = Depends(API_KEY_HEADER),
):
    """Flexible admin check: accepts either X-Admin-Key header or Bearer session token."""
    # Direct API key access
    if api_key and api_key == settings.admin_api_key:
        return {"method": "api_key"}
    # Session token access (from browser login)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if is_valid_token(token):
            return {"method": "session_token"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
