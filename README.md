# pitchr-ai

AI service for [Pitchr](https://github.com/jevoncochran/pitchr-client), a sales CRM for managing leads, outreach sequences and follow-ups.

Built with Python and FastAPI, using the Claude API.

## How it fits into Pitchr

Pitchr is split into three services:

| Repo | Role | Stack |
| --- | --- | --- |
| [pitchr-client](https://github.com/jevoncochran/pitchr-client) | Web app | React, TypeScript, Vite |
| [pitchr-server](https://github.com/jevoncochran/pitchr-server) | Main API, auth, database | NestJS, Prisma, Postgres |
| **pitchr-ai** | AI features | Python, FastAPI, Claude API |

The browser never calls this service directly. Requests flow through the main API, which handles authentication:

```
pitchr-client  →  pitchr-server  →  pitchr-ai  →  Claude API
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs the right Python version automatically)
- Python 3.14

## Getting started

Install dependencies:

```bash
uv sync
```

Start the development server (auto-reloads on changes):

```bash
uv run fastapi dev
```

The API runs at http://localhost:8000. Interactive API docs are at http://localhost:8000/docs.

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Returns `{"status": "ok"}` when the service is running |
| `POST` | `/leads/snapshot` | Short AI summary of a lead's current state and how to approach them. Requires the `X-Internal-Api-Key` header. |

## Docs

| Doc | What it covers |
| --- | --- |
| [Lead snapshot](docs/lead-snapshot.md) | Spec: what the snapshot contains, the odds rules, prompt rules, model choice |
| [Lead snapshot build plan](docs/lead-snapshot-build-plan.md) | How the feature was built, step by step, including the evals and model comparison |
| [Outreach sessions](https://github.com/jevoncochran/pitchr-server/blob/HEAD/docs/outreach-sessions.md) (in pitchr-server) | Spec draft: logging outreach sessions, planned routes, analytics |

Specs describe how a feature works now and are updated whenever it changes; build plans are a record of how it was built.

## Project structure

Organized by feature, like pitchr-server: shared code lives in `app/core/`, and each AI feature gets its own folder in `app/features/`.

```
pitchr-ai/
├── app/
│   ├── main.py                 # Creates the app, attaches the API key check, includes feature routers
│   ├── core/                   # Shared by every feature
│   │   ├── config.py           # Settings from environment variables / .env
│   │   ├── security.py         # Shared-secret check on every route (except PUBLIC_PATHS)
│   │   ├── claude.py           # The one helper all Claude calls go through (logs every call)
│   │   └── schemas.py          # CamelModel: snake_case in Python, camelCase in JSON
│   └── features/
│       └── lead_snapshot/      # One folder per AI feature
│           ├── router.py       # POST /leads/snapshot
│           ├── schemas.py      # Request and response models
│           ├── facts.py        # Facts computed in code (no AI)
│           ├── prompt.py       # System prompt and how lead data is laid out for Claude
│           └── service.py      # Ties it together: facts + Claude's analysis
├── tests/                      # Mirrors app/: tests/core/, tests/lead_snapshot/
├── evals/                      # Real-Claude quality checks, one folder per feature
├── docs/                       # Feature specs and build plans
├── pyproject.toml              # Project settings and dependencies
└── uv.lock                     # Exact dependency versions (managed by uv)
```

### Adding a feature

1. Create `app/features/<feature_name>/` with its own `router.py`, `schemas.py`, `service.py` (and `prompt.py` if it calls Claude).
2. Include its router in `app/main.py`. It's protected by the API key automatically.
3. Call Claude only through `app.core.claude.generate_structured`, with a `feature` name for the logs.
4. Add tests in `tests/<feature_name>/` and, for anything Claude writes, eval cases in `evals/<feature_name>/`.
