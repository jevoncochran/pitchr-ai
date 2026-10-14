# Feature: Lead snapshot

**Status:** Built (October 2026)

A short summary of a lead's current state, pulled up right before contacting or visiting them, so the person doing field outreach can decide how to approach the lead. It should read in about 30 seconds.

## Where it runs

- **In the app:** the "✨ Lead snapshot" card at the top of each lead's page. Nothing runs until you click **Generate**; **Refresh** makes a new one. Snapshots aren't saved.
- **pitchr-client** calls **pitchr-server** `GET /api/leads/:id/snapshot`, which loads the lead's data and calls **pitchr-ai** `POST /leads/snapshot` (with the shared API key).
- **Model:** Claude Sonnet 5.5 at effort `low`: about 1¢ and 5 seconds per snapshot. Chosen over Opus 5.5 and Haiku 5.5 with the evals (see the build plan).

## Output

Facts are computed in Python. Claude only writes the parts that need judgment.

**Computed in code**

- **Last contact**: date, days ago, and how (most recent touchpoint, i.e. our outreach)
- **Last activity**: date, days ago, and what (most recent signal or response from them). Empty if none.
- **Effort so far**: counts of every touchpoint by type: visits, emails, calls, DMs, texts, meetings, networking events, walk-ups, referral outreach and other

**Written by Claude**

- **Headline**: one line, under 15 words
- **Decision-maker**: name, role and status, or "Unknown"
- **Key facts**: 1-4 short bullets, only things the data says; fewer when the data is thin
- **Odds**: `high` / `medium` / `low` / `unknown`, plus a one-sentence reason grounded in the data
- **Goal**: one sentence on what this contact should achieve
- **Suggested approach**: 1-2 sentences

## Conversion odds

| Odds | When |
| --- | --- |
| High | The decision-maker showed clear intent recently (asked for a meeting or proposal, described a specific need), or the lead reached out first (website form, DM asking about services) within 30 days |
| Medium | Real interest but stalled (the decision-maker was receptive or asked us to follow up, then went quiet), a gatekeeper says they're interested, or there's a recent signal |
| Low | They said no, have a video provider they're happy with, or reacted lukewarm while talking to a competitor; or the decision-maker has been unreachable after 3+ attempts with no engagement |
| Unknown | Too little to judge, e.g. one or two touches and no response |

How signals and time affect the odds:

- A signal in the last 30 days raises the odds to at least medium. A signal alone never makes a lead high.
- Signals from 31-90 days ago are mentioned as context but don't change the odds. Older ones don't count.
- With no contact in 90+ days and no recent activity from them, the odds can still be medium, but the reason must say interest may have cooled. Not when they've shown interest recently.

## Input (sent by NestJS)

- **Today's date**
- **Lead**: business name, industry, business type, pipeline stage, sequence step, hot flag, priority, source, discovered via, referred by, dormant reason and revisit date
- **Contacts**: name, title, decision-maker flag, how we met, bio
- **Touchpoints**: date, type, whether they responded, contact names, full summary (up to the 25 most recent)
- **Signals**: date, type, platform, note
- **Notes**: date and text
- **Open tasks**: due date, type, note

Deliberately left out: ownership flags, follower counts, phone numbers and email addresses.

## Existing providers

We don't want to come across as pushy salespeople, or spend time on leads that are happy where they are.

- **Video provider they're happy with**: low odds, low priority. Don't try to win them over; keep it light and spend effort elsewhere.
- **Marketing agency**: not a dead end. Find out whether the agency does video, and offer video if it doesn't.
- **"Someone," type unclear**: find out what kind, without pressing. If it turns out to be a video provider they're happy with, deprioritize the lead.

## Prompt rules

- Use only facts in the data. If something is missing, say so.
- Treat pipeline stage and sequence fields as possibly out of date; trust the touchpoint history over them.
- Never describe people's appearance, race or other personal traits.
- Pay attention to timing in summaries. A missed "follow up by" date is a missed commitment; a passed "not until August" date means the window is now open.
- Key facts don't repeat last contact, last activity or effort counts, which the page already shows.
- The suggested approach is one or two short sentences.
- Only suggest referencing work from industries we have examples for: med spas and aesthetics, roofers and contractors, restaurants, and medical practices (physicians, chiropractors).

## Decisions

- **Last contact vs. last activity**: our outreach and their actions are shown separately.
- **Unknown decision-maker**: the goal becomes identifying them and making contact.
- **Most useful information lives in touchpoint summaries**, not structured fields, so summaries are always sent in full.
