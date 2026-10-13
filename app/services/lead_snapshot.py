"""The lead snapshot feature: facts computed in code, plus Claude's analysis.

See docs/lead-snapshot.md for the spec.
"""

from app.prompts.lead_snapshot import SYSTEM_PROMPT, build_prompt
from app.schemas.lead_snapshot import (
    LeadSnapshotRequest,
    LeadSnapshotResponse,
    SnapshotAnalysis,
)
from app.services.claude import generate_structured
from app.services.snapshot_facts import compute_facts

FEATURE = "lead_snapshot"

# How hard Claude thinks. "low" matched "medium" in the tuning evals and is
# about 3 seconds faster per snapshot.
EFFORT = "low"


def create_snapshot(
    request: LeadSnapshotRequest, effort: str = EFFORT
) -> LeadSnapshotResponse:
    """Build a complete snapshot for one lead. `effort` can be overridden for evals.

    Raises ClaudeError (from the Claude helper) if Claude can't produce the analysis.
    """
    # 1. The facts: plain Python, no AI
    facts = compute_facts(request)

    # 2. The judgment parts: Claude reads the lead's data, facts included
    analysis = generate_structured(
        feature=FEATURE,
        system=SYSTEM_PROMPT,
        prompt=build_prompt(request, facts),
        output_model=SnapshotAnalysis,
        effort=effort,
    )

    # 3. Combine both into the response NestJS receives
    return LeadSnapshotResponse(
        last_contact=facts.last_contact,
        last_activity=facts.last_activity,
        effort=facts.effort,
        analysis=analysis,
    )
