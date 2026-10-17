"""HTTP endpoint for the business card scan feature. Called by NestJS, never the browser."""

from fastapi import APIRouter, HTTPException

from app.core.claude import ClaudeError
from app.features.business_card_scan.schemas import (
    BusinessCardScanRequest,
    BusinessCardScanResponse,
)
from app.features.business_card_scan.service import scan_business_cards

router = APIRouter(prefix="/business-cards", tags=["business card scan"])


@router.post("/scan")
def business_card_scan(request: BusinessCardScanRequest) -> BusinessCardScanResponse:
    """Read up to 6 photos of one business's business cards together, and match each person to a contact."""
    try:
        return scan_business_cards(request)
    except ClaudeError as error:
        raise HTTPException(
            status_code=502, detail="Couldn't read the photo. Try again."
        ) from error
