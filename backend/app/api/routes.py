import tempfile
from pathlib import Path

import cv_engine
from fastapi import APIRouter, UploadFile

from app.schemas.analysis import AnalysisResponse, Exercise

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze/{exercise}", response_model=AnalysisResponse)
async def analyze(exercise: Exercise, video: UploadFile) -> AnalysisResponse:
    suffix = Path(video.filename or "video.mp4").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await video.read())
        tmp.flush()
        frames = cv_engine.KeypointExtractor().extract(tmp.name)

    return AnalysisResponse(
        exercise=exercise, frame_count=len(frames), reps=[], frames=frames
    )
