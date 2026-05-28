# PropFlow — CLAUDE.md

This file gives Claude Code the full context needed to work on this codebase effectively.

---

## What this project is

**PropFlow** (internally "Aadhya" / PropFlow Service Agents) is an **omnichannel AI intake platform** for property and design consultation services. It acts as an AI consultant that collects structured client requirements over WhatsApp and voice calls, then forwards them to a CRM/PM system.

The core user journey: a potential client texts or calls → the AI persona (Aadhya for interiors, Arvind for construction, etc.) holds a warm, intelligent conversation → collects 9 required fields → generates a project summary → posts a completion webhook to an external PM backend.

---

## Repository layout

```
PropFlow/
├── backend/                          # Python FastAPI backend (the core system)
│   ├── main.py                       # App entrypoint, route mounting, CORS
│   ├── config.py                     # Pydantic Settings — all env vars live here
│   ├── admin/
│   │   ├── router.py                 # All /admin/* API endpoints
│   │   └── auth.py                   # Password → session token auth
│   ├── agents/
│   │   ├── chat/whatsapp_handler.py  # Twilio webhook handler
│   │   └── voice/vapi_handler.py     # Vapi webhook + custom LLM endpoint
│   ├── intelligence/
│   │   ├── conversation_controller.py # Top-level controller + guardrails
│   │   ├── enquiry_engine.py          # Field priority selection
│   │   ├── persona.py                 # Named AI persona configs
│   │   └── llm_engine.py              # LLM abstraction shim
│   ├── llm/
│   │   ├── router.py                  # Multi-provider routing with fallback
│   │   ├── providers_gemini.py        # Google Gemini implementation
│   │   └── providers_openai_compat.py # OpenAI-compatible (OpenRouter, Groq, etc.)
│   ├── questionnaire/
│   │   ├── conversation_engine.py     # Core quest engine — 1200+ lines, most critical file
│   │   ├── coverage_policy.py         # Determines when questionnaire is "complete"
│   │   ├── completion_webhook.py      # Posts Quest-like payload to external backend
│   │   ├── summary_generator.py       # Generates project brief on completion
│   │   └── generated/                 # Auto-generated prompt templates + service parameters
│   ├── schemas/                       # Pydantic models: Session, Enquiry, Summary
│   ├── storage/
│   │   ├── redis_store.py             # Upstash REST API session cache
│   │   └── supabase_store.py          # Supabase PostgreSQL persistence
│   └── utils/                         # Logging, retry, perf metrics
├── admin-ui/                          # React + TypeScript admin dashboard
│   ├── src/
│   │   ├── App.tsx                    # Routes under /krsna/*
│   │   ├── pages/                     # Dashboard, Sessions, Enquiries, Summaries, Logs, System
│   │   └── api/                       # Typed API client for backend
│   ├── vercel.json                    # Vercel deployment (frontend only)
│   └── vite.config.ts                 # Dev proxy: /api → localhost:8000
├── tests/                             # pytest test suite
├── examples/                          # Demo scenarios + sample summary JSON
├── requirements.txt                   # Python deps
├── render.yaml                        # Render.com deployment config
├── .env.example                       # All env vars with descriptions
└── README.md
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend runtime | Python 3.11, FastAPI, Uvicorn |
| LLM (primary) | Google Gemini 2.0 Flash (`google-genai`) |
| LLM (fallback) | OpenAI-compatible (OpenRouter, Groq, etc.) |
| WhatsApp | Twilio webhook + `twilio` Python SDK |
| Voice | Vapi (custom LLM endpoint + SSE streaming) |
| Session cache | Upstash Redis (REST API, no redis-py) |
| Persistent storage | Supabase PostgreSQL (3 tables) |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Recharts |
| Frontend routing | React Router DOM 6 |
| Deployment | Render (backend), Vercel (admin UI) |

---

## The quest engine — most critical subsystem

`backend/questionnaire/conversation_engine.py` (~1200 lines) is the heart of the system. It is a Python port of a TypeScript "quest-characters" questionnaire library. Do not refactor it casually.

**9 required fields** that must be collected before the conversation completes:
`name`, `property_type`, `city`, `service_type`, `area`, `configuration`, `rooms`, `budget`, `timeline`

**Turn pipeline (per incoming message):**
1. Load session from Redis
2. Run extraction (LLM call → extract fields from user message)
3. Run coverage check (`coverage_policy.py`) — are all required fields confident?
4. If complete → generate summary → trigger completion webhook
5. Else → select next question via priority engine
6. Reply (streaming for voice, full text for WhatsApp)
7. Save session to Redis

**Session object** (defined in `backend/schemas/session.py`):
- `extracted_fields`: flat dict of all collected data + internal `__quest:*` metadata keys
- `conversation_history`: list of `{role, content, extracted_fields}` per turn
- `conversation_stage`: DISCOVERY → DETAIL_COLLECTION → CONFIRMATION → SUMMARY_GENERATED

---

## Guardrail system

Implemented in `backend/intelligence/conversation_controller.py`. Guards against:
- **Identity questions** ("are you a bot?", "who are you?") → warm deflection
- **Pricing questions** ("how much does it cost?") → defers to PM, never quotes
- **Off-topic messages** → politely redirects back to consultation
- **Scope promises** (timelines, discounts) → never commits

---

## Admin panel

URL: `/krsna` (password-protected React SPA)
The React frontend is built into `admin-ui/dist/` and served as static files by FastAPI.

Pages: Dashboard (KPIs + charts), Sessions (list + detail), Enquiries, Summaries, Logs, System Health

The admin password is set via `ADMIN_PASSWORD` env var. Login returns a session token stored in `sessionStorage`.

---

## Storage architecture

**Redis (Upstash REST)** — hot session cache
- Key: `session:<session_id>` (TTL: `SESSION_TTL_HOURS`, default 24h)
- Key: `lock:<session_id>` — distributed lock for concurrent messages
- Fallback: in-memory dict + asyncio locks if Redis not configured (single-process only)

**Supabase PostgreSQL** — cold persistent storage
- `enquiries` — snapshot on completion (session_id, phone, channel, extracted_fields JSONB)
- `project_summaries` — generated project briefs
- `sessions_log` — session metadata audit log

---

## Webhook completion flow

When all 9 fields are collected:
1. Summary is generated (`summary_generator.py`)
2. Session is saved to Supabase
3. If `ENQUIRY_WEBHOOK_URL` is set → POST Quest-like payload to external PM backend
4. Idempotency: session marked `__enquiry:webhook:sent=true` after 2xx — never re-posted

Audit trail stored on session: `__enquiry:webhook:lastStatus`, `lastOk`, `lastAt`, `lastPayload`

---

## Personas

Defined in `backend/intelligence/persona.py`. Each persona has:
- Name, role, domain knowledge, TTS voice settings
- Warm, locally-aware tone (India-focused, multilingual: English, Hindi, Kannada, Tamil)

Available: `aadhya` (interiors), `arvind` (construction), `manjunath_gowda`, and others.
Controlled by `CONSULTANT_PERSONA` env var.

---

## LLM routing

`backend/llm/router.py` — tries providers in order with fallback:
1. Primary: Gemini (`providers_gemini.py`)
2. Fallback: OpenAI-compatible (`providers_openai_compat.py`)

Gemini is used for: chat replies, JSON field extraction, summary generation, streaming (voice).

---

## Running locally

```bash
# Backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in API keys
uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000, docs at /docs

# Admin UI (separate terminal)
cd admin-ui
npm install
npm run dev
# → http://localhost:5173/krsna (proxies /api → localhost:8000)
```

Minimal env vars for local testing (WhatsApp + LLM only):
```
GEMINI_API_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
ADMIN_PASSWORD=localdev
BASE_URL=http://localhost:8000
```

---

## Key invariants — do not break

1. **Quest engine parity**: The Python engine must stay in sync with the TypeScript quest-characters source. Field names, coverage logic, and prompt templates are not to be changed without understanding both sides.
2. **Webhook idempotency**: Never remove the `__enquiry:webhook:sent` guard — double-posting to the external CRM would create duplicate leads.
3. **Voice streaming**: The Vapi endpoint (`/webhook/vapi/chat/completions`) must remain OpenAI-compatible and SSE-capable. The `endCall` tool payload format must not change.
4. **Session locking**: Redis distributed locks prevent race conditions on rapid multi-message bursts. Do not simplify this away.
5. **Guardrails must fire before quest engine**: The controller checks guardrails before passing to the quest engine — this order is intentional.

---

## Common tasks

**Adding a new service type**: Add the service code to `backend/questionnaire/generated/service_parameters_generated.py` and `backend/questionnaire/service_codes.py`. Update the LLM routing config if the service needs a different persona.

**Changing prompt templates**: Edit files in `backend/questionnaire/generated/`. These are the live prompts — changes affect all active conversations immediately.

**Adding an admin dashboard page**: Add a new `.tsx` file in `admin-ui/src/pages/`, add a route in `admin-ui/src/App.tsx`, and add a corresponding GET endpoint in `backend/admin/router.py`.

**Deploying the admin UI to Vercel**: `cd admin-ui && vercel` — the `vercel.json` is already configured with SPA rewrites and the `/krsna` base path.

**Running tests**: `pytest tests/ -v`

---

## Environment variables reference

See `.env.example` for the full annotated list. Critical ones:

| Var | Purpose |
|---|---|
| `GEMINI_API_KEY` | Primary LLM |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | WhatsApp |
| `VAPI_API_KEY` | Voice agent |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Session cache |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Persistent DB |
| `ADMIN_PASSWORD` | Admin panel access |
| `ENQUIRY_WEBHOOK_URL` | External CRM endpoint |
| `BASE_URL` | Public origin (no trailing slash) — used by Vapi for self-referencing URLs |
| `CONSULTANT_PERSONA` | Which AI persona to use (`aadhya`, `arvind`, etc.) |
