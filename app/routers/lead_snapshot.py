"""HTTP endpoint for the lead snapshot feature. Called by NestJS, never the browser."""

from fastapi import APIRouter, HTTPException

from app.schemas.lead_snapshot import LeadSnapshotRequest, LeadSnapshotResponse
from app.services.claude import ClaudeError
from app.services.lead_snapshot import create_snapshot

router = APIRouter(prefix="/leads", tags=["lead snapshot"])


@router.post("/snapshot")
def lead_snapshot(request: LeadSnapshotRequest) -> LeadSnapshotResponse:
    """Summarize a lead's current state before contacting or visiting them."""
    try:
        return create_snapshot(request)
    except ClaudeError as error:
        # 502 = "a service we depend on (Claude) failed", not a problem with the request
        raise HTTPException(
            status_code=502, detail="Couldn't generate the snapshot. Try again."
        ) from error
