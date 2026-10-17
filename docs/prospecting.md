# Prospecting agent

**Status:** Draft (idea, parked until [business card scan](https://github.com/jevoncochran/pitchr-server/blob/HEAD/docs/business-card-scan.md) and the [visit debrief](https://github.com/jevoncochran/pitchr-server/blob/HEAD/docs/visit-debrief.md) are built). No build plan yet.

Growing the leads list today means researching businesses by hand. The prospecting agent takes a request like **"aesthetics businesses in Orlando, about 50"** or **"home renovation companies in Orlando"**, finds and checks candidates, and returns a list to review. The ones you tick become leads.

It's Pitchr's first real agent: Claude decides which searches to run, what to check and when it's done. The features before it (lead snapshot, business card scan, visit debrief, follow-up emails) are workflows: single Claude calls inside steps the code controls.

## What you'd see

- A request box (what kind of business, where, roughly how many) and a run that works in the background, showing progress: "Searching 'IV therapy Lake Nona'… 34 found, 12 qualified".
- A review list: business, type, area, website and Instagram, why it fits, notes. Businesses already in Pitchr are marked and can't be added twice.
- **Add selected as leads**: stage `NEW`, with address, coordinates and Google place ID (so they can go straight into a session and route planning). Origin stays empty until we reach out (see pitchr-server's lead-origin.md).

## Why it's an agent

Finding businesses is a Google Places search. The judgment around it is the agent's job:

- **Breaking the request into searches**: "aesthetics" covers med spas, injectables, laser hair removal, IV therapy, brow and lash studios; "Orlando" covers Winter Park, Kissimmee, Lake Nona, Dr. Phillips. It looks at what comes back and adds searches where results are thin.
- **Coverage and duplicates**: pages through results, merges duplicates across searches, checks each against existing leads.
- **Qualifying**: opens the website and Instagram of promising candidates to judge fit (posts video or not, single location or chain, owner named).
- **Stopping**: at the requested count, at the budget, or when new searches only return what it already has.

## Tools (sketch)

- `places_search`: Google Places, through pitchr-server's server key.
- `check_existing_leads`: an internal pitchr-server endpoint (match by place ID, name, phone).
- `fetch_page`, `web_search`: for qualifying.
- `save_candidate`: writes to the review list, never straight to leads.

Architecture: pitchr-ai runs the loop; its tools call internal pitchr-server endpoints with the shared key, so NestJS keeps owning the database. This changes ground rule 2 in CLAUDE.md (pitchr-ai is stateless and sent everything it needs), so it gets agreed before building.

## Cost

Google Places is billed per request and by which fields are asked for (ratings and review counts cost more than an address); a 50-business run could be dozens of searches plus a details lookup per candidate. Claude: the loop plus reading websites, roughly cents to a dollar per run depending on how deep it qualifies. Real numbers from current pricing go in the spec; every run gets a cost cap, and nothing runs without the owner's OK. Check Google's terms on storing Places data.

## What it would show (portfolio)

A long-running agent with progress, tool design, step and budget limits, approval before anything is saved, a visible trace of what it searched and why, and an agent eval: for a fixed request, how many results were real fits, how many were duplicates, and how many good businesses it missed against a hand-checked list.

## Open questions

1. What makes a good prospect? (Has a website, active Instagram, little or no video, single location, minimum reviews; anything that rules one out, like chains.)
2. What should the review list show, and what should a new lead come with? (Address, phone, website, Instagram, rating and reviews, why it fits.)
3. Typical run size: about 50 per city and industry, or bigger sweeps?

## Related agent and RAG ideas

- **Research one lead**: the qualifying step above, run on a single business ("Research Lopez Med Spa"), with sources and Replace/Keep approval.
- **Ask Pitchr**: questions about the pipeline in plain words, answered with read-only tools plus semantic search over touchpoint summaries, notes and replies (pgvector in Neon; Voyage AI embeddings).
- **Session planner**: "plan tomorrow's session in South Tampa, about 3 hours", using due follow-ups, come-back dates and priorities, with the route optimizer as a tool.
- **Past-work library (RAG)**: Intercon Visuals case studies by industry, retrieved when drafting follow-up emails instead of the hard-coded industry list.
