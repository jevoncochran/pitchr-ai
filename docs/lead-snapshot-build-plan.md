# Lead snapshot: build plan

How the lead snapshot feature gets built, step by step. The feature itself is described in [lead-snapshot.md](lead-snapshot.md).

**Status:** ✅ done · ⏭️ next · ⬜ not started

File paths reflect the feature-based layout (`app/core/`, `app/features/lead_snapshot/`) adopted after step 12.

## How a request flows

```
You click "Snapshot" on a lead page            (pitchr-client)
  → NestJS gathers that lead's data            (pitchr-server)
    → sends it to pitchr-ai
      → Python computes the facts               (step 3)
      → Claude writes the judgment parts        (steps 5–6)
      → the Claude call is logged               (step 5)
    ← returns the finished snapshot
  ← NestJS passes it back
← The page shows it
```

---

## Part 1: pitchr-ai (Python service)

### ✅ Step 1: The spec
**File:** `docs/lead-snapshot.md`

The agreed plan, saved in the repo: what the snapshot contains, the conversion-odds rules, the input data and the prompt rules. No real lead data, since the repo is public.

### ✅ Step 2: The contract (request and response models)
**File:** `app/features/lead_snapshot/schemas.py`

Pydantic models for exactly what NestJS sends and what we send back. FastAPI uses them to reject malformed requests automatically.

- `CamelModel`: Python uses `snake_case`, JSON uses `camelCase`; this converts between them in both directions
- Request: `LeadInfo`, `ContactInfo`, `TouchpointInfo`, `SignalInfo`, `NoteInfo`, `TaskInfo`, bundled in `LeadSnapshotRequest`
- Response: `LastContact`, `LastActivity`, `EffortCounts` (computed in code) and `SnapshotAnalysis` (written by Claude), bundled in `LeadSnapshotResponse`

### ✅ Step 3: The facts (no AI)
**File:** `app/features/lead_snapshot/facts.py`

Plain Python that computes the facts, so they're right every time:

- **Last contact**: our most recent touchpoint
- **Last activity**: their most recent action (a signal, or a response to our outreach)
- **Effort counts**: every touchpoint type is counted: visits (including visit attempts), emails, calls, DMs, texts, meetings, networking events, walk-ups, referral outreach, and "other" as a catch-all for anything else

### ✅ Step 4: Settings
**Files:** `app/core/config.py`, `.env.example`

Reads settings from environment variables, or from a local `.env` file.

- `ANTHROPIC_API_KEY`: required; stored as a `SecretStr` so it never shows up in logs
- `CLAUDE_MODEL`: optional; defaults to `claude-opus-5-5`
- `.env.example` is the committed template; your real `.env` stays out of git

### ✅ Step 5: The shared Claude helper
**File:** `app/core/claude.py`

`generate_structured()`: every Claude call in the project goes through it (CLAUDE.md rule 3).

- Forces Claude's answer to match a Pydantic model (structured output)
- Logs feature, model, input/output tokens, duration, stop reason and request ID
- Raises `ClaudeError` on failures, refusals, cut-off answers or a bad format
- Refusal fallback on: if a request is declined, Anthropic retries it on another model automatically
- `effort` setting: how hard Claude thinks (`low` / `medium` / `high`...)

Tested with one real call: works, about $0.002.

### ✅ Step 6: The prompt
**File:** `app/features/lead_snapshot/prompt.py`

Instructions for Claude: who's reading the snapshot and why, the conversion-odds rules, and the prompt rules from the spec. Kept in its own file because it's the part that changes most during tuning.

- `SYSTEM_PROMPT`: the standing instructions, the same for every lead (about 580 words)
- `build_prompt()`: lays out one lead's data in labeled sections (`<lead>`, `<computed_facts>`, `<contacts>`, `<touchpoints>`, `<signals>`, `<notes>`, `<open_tasks>`), with dates like `5/7/26 (159 days ago)`
- Up to 25 most recent touchpoints, shown oldest first so they read as a story
- No example snapshots yet: we'll decide at the tuning checkpoint whether made-up examples help

### ✅ Step 7: The feature logic
**File:** `app/features/lead_snapshot/service.py`

Combines step 3's facts with Claude's analysis (steps 5–6) into one snapshot.

`create_snapshot()`: compute the facts → build the prompt → call Claude → combine into `LeadSnapshotResponse`. Uses `effort="medium"` for now.

First end-to-end run on a made-up lead: about 2,300 tokens in, 410 out, ~8 seconds, ~$0.02.

### ✅ Step 8: The endpoint
**Files:** `app/features/lead_snapshot/router.py`, `app/main.py`

`POST /leads/snapshot`: receives the request, calls step 7 and returns the result. Also turns on logging in `main.py` so the Claude log lines appear when the app runs.

| Situation | Response |
| --- | --- |
| Valid request | `200` with the snapshot (camelCase JSON) |
| Malformed request | `422` listing what's wrong (automatic, from the step 2 models) |
| Claude fails | `502` "Couldn't generate the snapshot. Try again." |

### ✅ Step 9: Tests
**Folder:** `tests/`

17 tests, all passing in under a second. Run them with `uv run pytest`.

- `test_facts.py`: last contact, last activity, signal descriptions, effort counts
- `test_prompt.py`: date formatting, the 25-touchpoint limit, empty sections
- `test_endpoint.py`: success (camelCase JSON), what gets sent to Claude, Claude failing (502), bad input (422). Claude is faked, so these are free.
- New dev dependency: `pytest`. Ruff lint and format pass on the whole project.

### ✅ Checkpoint: tune the prompt
**Files:** `evals/lead_snapshot/cases/` (4 cases), `evals/run_lead_snapshot.py`

Your four example leads, rewritten with made-up names, each with your hand-written snapshot and a "must get right" checklist. The runner sends every case through the real feature and writes a side-by-side report (about 2¢ per case):

```bash
uv run python -m evals.run_lead_snapshot --label my-run
```

Reports go to `evals/lead_snapshot/results/` (not committed). Rerun after any prompt change and compare.

**What changed after the baseline run:**

- **"May have cooled"** now only applies when there's no recent activity from them either. A fresh signal means their interest is current.
- **Timing:** missed "follow up by" dates are called out as missed; a passed "not until August" date means the window is now open.
- **Key facts** don't repeat last contact, last activity or effort counts (the page shows those). Fewer bullets when the data is thin; one is fine.
- **Approach** is one or two short sentences.
- **Portfolio:** Claude only suggests work from industries we have: med spas and aesthetics, roofers and contractors, restaurants, medical practices (physicians, chiropractors).
- **Existing providers (new rule):** a happy video provider means low odds and low priority, no pushing. A marketing agency means find out if they do video. "Someone," type unclear, means find out without pressing, and deprioritize if it's a happy video provider.
- **Effort: `low`.** Same quality as `medium` in the evals, about 5.4s instead of 8.4s, about 2¢ per snapshot.

The last two prompt tweaks (the deprioritize wording and fewer bullets for thin data) were verified in the model comparison below.

### ✅ Model comparison: switched to Sonnet 5.5
Same prompt, same four cases, effort `low`, on three models:

| | Opus 5.5 | **Sonnet 5.5 (chosen)** | Haiku 5.5 |
| --- | --- | --- | --- |
| Cost per snapshot | ~2.0¢ | **~1.0¢** | ~0.06¢ |
| Average time | ~5.4s (one 12.7s outlier) | **~4.7s** | ~3.9s |
| Checklists | All passed | **All passed** | Missed 2 points |
| Invented facts | None | **None** | One serious one |

- **Sonnet** matched Opus on every case, so it's the default now (`claude_model` in `app/core/config.py`).
- **Haiku** wrote that the med spa has "an existing video provider" when the data only says "someone." That's exactly the distinction the existing-provider rule depends on, so it would have led us to drop a lead wrongly. Not used for this feature.
- Four cases is a small sample: if a real snapshot ever misleads, add that lead (with made-up names) as a new eval case and rerun. Switching models is one setting (`CLAUDE_MODEL`), no code change.

---

## Part 2: pitchr-server (NestJS)

### ✅ Step 10: Snapshot endpoint in NestJS
**Files (pitchr-server):** `src/leads/lead-snapshot.service.ts` (new), `leads.controller.ts`, `leads.module.ts`, `.env.example`

`GET /api/leads/:id/snapshot` (behind the login guard): loads the lead's data, reshapes it to match the contract (step 2), calls pitchr-ai and returns the result.

- `PITCHR_AI_URL` setting, defaulting to `http://localhost:8000`
- "Today" is computed in Tampa time (`America/New_York`), not UTC
- Only the 25 most recent touchpoints and open tasks are loaded; phones, emails and ownership flags are never sent
- Errors: lead not found `404`, pitchr-ai down or too slow (60s) `503`, pitchr-ai failed `502`

Checked: the request built for all 195 leads in the database validates against pitchr-ai's models; a real Rabbit Roofing snapshot came back in 5.4s.

### ✅ Step 11: Shared secret
**Files:** `app/core/security.py` (new), `app/main.py`, `app/core/config.py`, `tests/conftest.py`, `tests/core/test_security.py` (pitchr-ai); `src/leads/lead-snapshot.service.ts` (pitchr-server); both `.env.example` files

**Secure by default:** every pitchr-ai route requires the `X-Internal-Api-Key` header to match `PITCHR_AI_API_KEY`, or it returns `401`. The check is attached to the whole app in `main.py`, so new routes are protected automatically. The only exceptions are listed in `PUBLIC_PATHS` in `app/core/security.py`: just `/health`, for Railway's health checks.

- NestJS sends the header on every call. Same setting name, `PITCHR_AI_API_KEY`, in both services
- Compared with `secrets.compare_digest`, so the key can't be guessed by timing responses
- `/docs` has an **Authorize** button: enter the key once to use "Try it out"
- Tests: no key, wrong key, health public, only health public, routes added later are protected, Authorize button. 23 tests total
- Tests can never call the real Claude API: `tests/conftest.py` blocks it
- Local `.env` files in both repos have a generated secret; on Railway, generate a new one

---

## Part 3: pitchr-client (React)

### ✅ Step 12: Snapshot button and panel
**Files (pitchr-client):** `src/components/leads/LeadSnapshot.tsx` (new), `src/pages/LeadDetailPage.tsx`

A "✨ Lead snapshot" card at the top of each lead's page, above the pipeline stage.

- Nothing runs until **Generate** is clicked (on demand, no cost for just opening a lead); **Refresh** makes a new one
- States: not generated · loading (about 5s) · error (NestJS's message + Try again) · snapshot
- Layout: headline, odds badge (color-coded), last contact / last activity, effort chips, decision-maker, key facts, a highlighted Goal + Approach box, the odds reason, and when it was generated
- Dates from pitchr-ai (`YYYY-MM-DD`) are formatted by hand, because `new Date("2026-05-06")` is UTC midnight and shows the previous day in US time zones
- Not saved: it doesn't update by itself after new touchpoints; Refresh does

Tested end to end in the app.
---

## Part 4: Deploy

### ⏭️ Step 13: Railway
A Dockerfile for pitchr-ai, a new Railway service on private networking, and the environment variables.

---

## Setup to-dos

- ✅ Anthropic API key created and added to `.env`
