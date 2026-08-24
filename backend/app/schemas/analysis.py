from enum import Enum

from pydantic import BaseModel

from app.schemas.keypoint import Frame


class Exercise(str, Enum):
    SQUAT = "squat"
    DEADLIFT = "deadlift"
    BENCH_PRESS = "bench_press"
    OVERHEAD_PRESS = "overhead_press"
    LUNGE = "lunge"
    PUSHUP = "pushup"
    PULLUP = "pullup"
    ROW = "row"


class RepScore(BaseModel):
    rep_index: int
    start_sec: float
    end_sec: float
    form_accuracy: float
    faults: list[str] = []


class AnalysisResponse(BaseModel):
    exercise: Exercise
    frame_count: int
    reps: list[RepScore]
    frames: list[Frame]
