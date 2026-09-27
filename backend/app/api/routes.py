import logging
import tempfile
from pathlib import Path

import cv_engine
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.history import service
from app.history.database import get_session
from app.schemas.analysis import AnalysisResponse, Exercise
from app.schemas.keypoint import Frame as FrameSchema
from app.scoring import pipeline as scoring_pipeline
from app.security import require_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/analyze/{exercise}",
    response_model=AnalysisResponse,
    dependencies=[Depends(require_api_key)],
)
async def analyze(
    exercise: Exercise, video: UploadFile, session: Session = Depends(get_session)
) -> AnalysisResponse:
    suffix = Path(video.filename or "video.mp4").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await video.read())
        tmp.flush()
        frames = cv_engine.KeypointExtractor().extract(tmp.name)

    frame_models = [FrameSchema.model_validate(f) for f in frames]
    reps = scoring_pipeline.analyze(exercise, frame_models)

    response = AnalysisResponse(
        exercise=exercise, frame_count=len(frame_models), reps=reps, frames=frame_models
    )

    try:
        service.log_video_entry(session, exercise, response)
    except Exception:
        logger.warning(
            "Failed to auto-log history entry for %s analysis", exercise.value, exc_info=True
        )

    return response
