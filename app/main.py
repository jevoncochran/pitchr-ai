import logging

from fastapi import Depends, FastAPI

from app.routers import lead_snapshot
from app.security import require_api_key

# Libraries only log warnings and errors; our own code (the "pitchr_ai" loggers,
# e.g. one line per Claude call) also logs info.
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("pitchr_ai").setLevel(logging.INFO)

# Every route requires the shared secret, except those listed in
# app.security.PUBLIC_PATHS. New routes are protected automatically.
app = FastAPI(title="Pitchr AI", dependencies=[Depends(require_api_key)])
app.include_router(lead_snapshot.router)


@app.get("/health")
def health():
    return {"status": "ok"}
