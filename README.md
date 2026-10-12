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

## Project structure

```
pitchr-ai/
├── app/
│   ├── __init__.py
│   └── main.py        # FastAPI app and routes
├── pyproject.toml     # Project settings and dependencies
└── uv.lock            # Exact dependency versions (managed by uv)
```
