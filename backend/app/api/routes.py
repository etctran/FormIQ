import logging
import tempfile
from pathlib import Path

import cv_engine
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.history import service
from app.history.database import get_session
from app.schemas.analysis import AnalysisResponse, Exercise

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze/{exercise}", response_model=AnalysisResponse)
async def analyze(
    exercise: Exercise, video: UploadFile, session: Session = Depends(get_session)
) -> AnalysisResponse:
    suffix = Path(video.filename or "video.mp4").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await video.read())
        tmp.flush()
        frames = cv_engine.KeypointExtractor().extract(tmp.name)

    response = AnalysisResponse(exercise=exercise, frame_count=len(frames), reps=[], frames=frames)

    try:
        service.log_video_entry(session, exercise, response)
    except Exception:
        logger.warning(
            "Failed to auto-log history entry for %s analysis", exercise.value, exc_info=True
        )

    return response
