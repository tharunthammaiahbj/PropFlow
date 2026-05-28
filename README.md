# PropFlow — Omnichannel AI Intake Platform

**PropFlow** (powered by PropFlow) is a production-grade AI intake system that acts as a named consultant persona over **WhatsApp** and **Voice calls**. It collects structured client requirements through natural conversation, generates a project brief, and forwards a completion payload to an external PM/CRM backend.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Key features](#key-features)
- [Running locally](#running-locally)
- [Deployment](#deployment)
- [Environment variables](#environment-variables)
- [Admin panel (`/krsna`)](#admin-panel-krsna)
- [QA checklist](#qa-checklist)
- [Troubleshooting](#troubleshooting)

---

## What it does

A potential client sends a WhatsApp message or makes a phone call → the AI persona (e.g. *Aadhya*, an interior design consultant) holds a warm, intelligent conversation → collects **9 required fields** (name, property type, city, service type, area, configuration, rooms, budget, timeline) → generates a structured project summary → posts a completion webhook to your CRM.

Channels:
- **WhatsApp** via Twilio — text-based, full questionnaire flow
- **Voice** via Vapi — phone calls with streaming TTS, ASR, and graceful call closure

Both channels share the same quest questionnaire engine, so behavior is consistent.

---

## Architecture

```
Caller (Phone) ─── Vapi ──►  POST /webhook/vapi            (assistant config)
                   Vapi ──►  POST /webhook/vapi/chat/completions  (Custom LLM, SSE streaming)
                                           │
WhatsApp User ─── Twilio ─►  POST /webhook/whatsapp
                                           │
                                  ConversationController
                                  (guardrails → quest engine)
                                           │
                               Quest Questionnaire Engine
                          (extraction → coverage → next question)
                                           │
                          Redis (session cache) + Supabase (persistent)
                                           │
                              Completion webhook → external CRM/PM
                                           │
                                    Admin UI: /krsna
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| LLM — primary | Google Gemini 2.0 Flash |
| LLM — fallback | OpenAI-compatible (OpenRouter, Groq, etc.) |
| WhatsApp | Twilio webhook |
| Voice | Vapi (custom LLM endpoint + SSE) |
| ASR | Deepgram (via Vapi) |
| TTS | Cartesia or ElevenLabs (via Vapi) |
| Session cache | Upstash Redis (REST API) |
| Persistent storage | Supabase PostgreSQL |
| Admin frontend | React 18, TypeScript, Vite, TailwindCSS, Recharts |
| Deployment | Render (backend), Vercel (admin UI) |

---

## Key features

### Conversational quest engine
- Service-specific required fields (9 minimum per lead)
- Dynamic question routing based on what's been extracted vs. still missing
- Multi-turn confidence tracking — tentative vs. confirmed field values
- Automatic completion detection with graceful voice call closure

### AI personas
- Named consultants per service type (Aadhya for interiors, Arvind for construction, etc.)
- Warm, empathetic tone; locally aware (India-focused)
- Multilingual: English, Hindi, Kannada, Tamil with code-switching support
- Configured via `CONSULTANT_PERSONA` env var

### Guardrail system
- Identity deflection ("are you a bot?" → warm response, never breaks persona)
- Pricing guardrails (never quotes costs, defers to project manager)
- Off-topic redirection (non-dismissive, guides back to consultation)
- No scope promises (timelines, discounts)

### Voice-specific
- True SSE streaming to Vapi so TTS starts before full response is ready
- ASR confusion normalization (e.g. "solor" → "solar")
- Opening message guaranteed on first turn (no jumping straight to questions)
- `endCall` tool emitted after closing message — Vapi hangs up cleanly

### Completion webhooks
- POST Quest-like payload to external PM backend on questionnaire completion
- Bearer token auth, idempotent (sent once only after 2xx response)
- Full audit trail stored on session

### Admin panel (`/krsna`)
- Live dashboard: active sessions, completion rates, channel distribution, messages/hour
- Session browser with full transcript + extracted fields + thinking traces
- Enquiry and summary lists
- System health check (Redis, Supabase, LLM connectivity)
- Session actions: reset, force summary, close

---

## Running locally

### Backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your API keys
uvicorn backend.main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

### Admin UI

```bash
cd admin-ui
npm install
npm run dev
```

- Admin UI: `http://localhost:5173/krsna`  
  (Vite proxies `/api` → `localhost:8000`)

### Minimal env for local WhatsApp testing

```env
GEMINI_API_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
ADMIN_PASSWORD=localdev
BASE_URL=http://localhost:8000
```

### Simulate webhooks via curl

```bash
# WhatsApp message
curl -X POST http://localhost:8000/webhook/whatsapp \
  -d "From=whatsapp%3A%2B919876543210&Body=Hi+I+need+interior+design+help"

# Vapi assistant-request
curl -X POST http://localhost:8000/webhook/vapi \
  -H "Content-Type: application/json" \
  -d '{"message":{"type":"assistant-request"}}'

# Vapi custom LLM (non-streaming)
curl -X POST http://localhost:8000/webhook/vapi/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"stream":false,"messages":[{"role":"user","content":"Hello"}],"call":{"id":"test_001","customer":{"number":"+919876543210"}}}'
```

---

## Deployment

### Backend (Render)

Render config is in `render.yaml`. Key steps:
- Set all environment variables in the Render dashboard
- Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Set `BASE_URL` to your public Render URL (no trailing slash)
- Ensure `CORS_ORIGINS` includes your admin UI domain

Alternatively, use `nixpacks.toml` for Nixpacks-compatible platforms (Railway, etc.).

### Admin UI (Vercel)

```bash
cd admin-ui
vercel
```

`vercel.json` is already configured with SPA rewrites for the `/krsna` base path.  
Set `VITE_API_URL` in Vercel environment settings to your backend's public URL.

---

## Environment variables

Full annotated list is in `.env.example`. Summary of required variables:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key (primary LLM) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_WHATSAPP_FROM` | Twilio WhatsApp sender number |
| `VAPI_API_KEY` | Vapi API key |
| `TTS_PROVIDER` | `cartesia` or `11labs` |
| `CARTESIA_VOICE_ID` | Cartesia voice ID (if using Cartesia) |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice ID (if using ElevenLabs) |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST URL |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis auth token |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `ADMIN_PASSWORD` | Password for `/krsna` admin panel |
| `ENQUIRY_WEBHOOK_URL` | External CRM/PM webhook URL |
| `ENQUIRY_WEBHOOK_BEARER_TOKEN` | Bearer token for webhook auth |
| `BASE_URL` | Public backend URL (no trailing slash) |
| `CONSULTANT_PERSONA` | `aadhya`, `arvind`, etc. |

### Quest engine tuning (optional)

| Variable | Default | Description |
|---|---|---|
| `QUEST_MERGED_EXTRACT_REPLY` | `true` | Single LLM call for extract + reply (WhatsApp) |
| `QUEST_EXTRACTION_MAX_OUTPUT` | `768` | Max tokens for field extraction |
| `QUEST_GEMINI_MAX_OUTPUT_VOICE` | `220` | Max tokens per voice turn |
| `QUEST_LLM_TEMPERATURE` | `0.35` | LLM temperature for questionnaire responses |
| `SESSION_TTL_HOURS` | `24` | Redis session TTL |
| `VAPI_STREAM_FLUSH_CHARS` | `80` | Stream flush chunk size (lower = faster TTS start) |

---

## Admin panel (`/krsna`)

Access: `<your-backend-url>/krsna` → enter `ADMIN_PASSWORD`

| Page | URL | Purpose |
|---|---|---|
| Dashboard | `/krsna/dashboard` | KPIs, charts, real-time metrics |
| Sessions | `/krsna/sessions` | All conversations, filterable by service |
| Session detail | `/krsna/sessions/:id` | Full transcript, extracted fields, webhook audit |
| Enquiries | `/krsna/enquiries` | Completed leads list |
| Summaries | `/krsna/summaries` | Generated project briefs |
| Logs | `/krsna/logs` | System event log |
| System | `/krsna/system` | Health check: Redis, Supabase, LLM |

Use the session detail view to validate:
- `__quest:parameters` populated correctly for the service
- `__quest:conversationFlow` shows question+answer pairs in order
- `__enquiry:webhook:lastOk=true` after completion

---

## QA checklist

### Voice (per service/persona)

- Call → say "Hello, who is this?" → confirm intro (name + role) is spoken before first question
- Answer each question once — verify no topic is repeated
- Confirm no blank/silent assistant turns
- After final answer → confirm closing message is spoken and call ends cleanly

### WhatsApp

- Complete a questionnaire end-to-end
- Send "ok" / "done" after completion → confirm no repeated closing message

### Webhook (if enabled)

- In logs: verify `ENQUIRY_WEBHOOK_START` then `ENQUIRY_WEBHOOK_OK`
- In admin session detail: `__enquiry:webhook:lastOk=true`, `lastStatus` is 2xx, `lastPayload` matches expected shape

---

## Troubleshooting

**No intro on voice calls**  
Check logs for `phase:"opening"` on the first user message turn. If missing, check that `session.turn_count == 0` is being detected correctly in `vapi_handler.py`.

**Repeated questions**  
Usually means the user's answer was ambiguous (low extraction confidence) so the engine intentionally re-asks. Check `__quest:conversationFlow` in the admin session detail to see confidence scores per turn.

**Webhook 400 / 401 / 403**  
- `ENQUIRY_WEBHOOK_MISCONFIGURED` in logs → set `ENQUIRY_WEBHOOK_BEARER_TOKEN`
- Validation errors for `userId`/`serviceId` → ensure `ENQUIRY_WEBHOOK_USER_ID` / `ENQUIRY_WEBHOOK_SERVICE_ID` match the format expected by your external backend (often MongoDB ObjectIds)

**Redis fallback active (in-memory sessions)**  
If `UPSTASH_REDIS_REST_URL` is not set, sessions are stored in-memory. This means sessions are lost on restart and won't work across multiple server processes. Set Upstash credentials for production.

**LLM provider errors**  
Check `GET /admin/health` in the admin panel for LLM status. The system automatically falls back from Gemini to the OpenAI-compatible provider if configured.
