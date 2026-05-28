"""
PropFlow – FastAPI Application Entry Point
Registers all routers.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.questionnaire.conversation_engine import QUEST_MERGED_EXTRACT_REPLY
from backend.agents.chat.whatsapp_handler import router as whatsapp_router
from backend.agents.voice.vapi_handler import router as vapi_router
from backend.agents.web.web_handler import router as web_router
from backend.admin.router import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("PropFlow — Starting up")
    print(f"   Quest merged extract+reply: {'on' if QUEST_MERGED_EXTRACT_REPLY else 'OFF (set QUEST_MERGED_EXTRACT_REPLY=true)'}")
    print("   Gemini intelligence: ready")
    print("   WhatsApp webhook: /webhook/whatsapp")
    print("   Vapi webhook: /webhook/vapi")
    print("   Web demo webhook: /webhook/web")
    yield
    print("PropFlow — Shutting down")


app = FastAPI(
    title="PropFlow – AI Intake Platform",
    description="PropFlow omnichannel AI consulting system (WhatsApp + Voice + Web)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=_settings.cors_origins_list != ["*"],  # credentials only when origins are restricted
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Agent Webhooks ────────────────────────────────────────────────────────────
app.include_router(whatsapp_router)
app.include_router(vapi_router)
app.include_router(web_router)

# ─── Admin API ─────────────────────────────────────────────────────────────────
app.include_router(admin_router)

# ─── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "PropFlow AI Intake Platform",
        "version": "1.0.0",
        "company": "PropFlow",
        "status": "operational",
        "endpoints": {
            "whatsapp_webhook": "/webhook/whatsapp",
            "vapi_webhook": "/webhook/vapi",
            "web_webhook": "/webhook/web",
            "admin_api": "/admin",
            "docs": "/docs",
        }
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "propflow"}


@app.get("/ping")
async def ping():
    return {"pong": True}
