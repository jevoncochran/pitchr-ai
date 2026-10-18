"""HTTP endpoint for the visit debrief feature. Called by NestJS, never the browser."""

from fastapi import APIRouter, HTTPException

from app.core.claude import ClaudeError
from app.features.visit_debrief.schemas import VisitDebriefRequest, VisitDebriefResponse
from app.features.visit_debrief.service import debrief_visit

router = APIRouter(prefix="/visits", tags=["visit debrief"])


@router.post("/debrief")
def visit_debrief(request: VisitDebriefRequest) -> VisitDebriefResponse:
    """Turn a note dictated after an in-person visit into a proposal for the visit form."""
    try:
        return debrief_visit(request)
    except ClaudeError as error:
        raise HTTPException(
            status_code=502, detail="Couldn't fill in the form. Try again."
        ) from error
