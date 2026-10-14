# pitchr-ai

AI service for the Pitchr CRM. Python, FastAPI, Claude API. Managed with uv. Organized by feature: shared code in `app/core/` (config, security, the Claude helper, `CamelModel`), one folder per AI feature in `app/features/` (router, schemas, service, prompt). Tests and evals mirror that layout. See the README's "Adding a feature". Sibling repos: `../pitchr-client` (React) and `../pitchr-server` (NestJS).

## Ground rules

### 1. Only NestJS calls this service

```
pitchr-client  →  pitchr-server (NestJS)  →  pitchr-ai  →  Claude API
```

- The browser never talks to pitchr-ai. Don't add CORS settings, browser-facing auth, or endpoints designed for the client.
- pitchr-server decides when to call this service. User auth (JWT) stays in NestJS; this service does not know about users or sessions.
- Treat requests as coming from a trusted internal caller, but still validate every request body with Pydantic models.
- Every route requires the shared secret automatically (the check is attached to the whole app in `main.py`). NestJS sends it in the `X-Internal-Api-Key` header. The only way to make a route public is adding it to `PUBLIC_PATHS` in `app/core/security.py`; currently just `/health`, for Railway's health checks. Don't add to it without a good reason.

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

### 4. Never spend money without asking

Evals (`evals/`), live calls to an endpoint, and anything else that calls the real Claude API cost money. Never run them without the user's permission, even when a build plan says to rerun an eval. Suggest when a run is worth it and roughly what it costs, then wait for a yes. The test suite (`uv run pytest`) doesn't call Claude and is fine to run anytime.

## Docs

- **Specs** (`docs/<feature>.md`) describe how a feature works **now** and why. Keep the status line current (Draft → Building → Built). When you change a feature's behavior, update its spec in the same change; once built, remove open questions and rewrite plans as plain descriptions.
- **Build plans** (`docs/<feature>-build-plan.md`) record how a feature was built, step by step. Update them while building; once the feature ships, mark them complete and leave them as history.
- List new docs in the README's **Docs** section.
