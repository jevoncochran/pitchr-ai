# pitchr-ai

AI service for the Pitchr CRM. Python, FastAPI, Claude API. Managed with uv; app code lives in `app/`. Sibling repos: `../pitchr-client` (React) and `../pitchr-server` (NestJS).

## Ground rules

### 1. Only NestJS calls this service

```
pitchr-client  →  pitchr-server (NestJS)  →  pitchr-ai  →  Claude API
```

- The browser never talks to pitchr-ai. Don't add CORS settings, browser-facing auth, or endpoints designed for the client.
- pitchr-server decides when to call this service. User auth (JWT) stays in NestJS; this service does not know about users or sessions.
- Treat requests as coming from a trusted internal caller, but still validate every request body with Pydantic models.

### 2. NestJS sends the data each request needs (for now)

- This service is stateless and has no database connection. Everything a feature needs (lead details, touchpoints, sequence step, etc.) arrives in the request body.
- Define a Pydantic request model per endpoint describing exactly what NestJS must send.
- This is expected to change later (e.g. RAG with embeddings stored in Postgres/pgvector). Don't add database access without discussing it first.

### 3. Log every Claude call

Every call to the Claude API must record:

- **feature**: which feature made the call (e.g. `draft_outreach_email`)
- **tokens used**: input and output tokens, from the API response's `usage`
- **duration**: how long the call took

Route all Claude calls through one shared helper so logging can't be skipped. Never call the Anthropic SDK directly from a route.
