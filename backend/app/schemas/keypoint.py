from pydantic import BaseModel


class Keypoint(BaseModel):
    """Mirrors formiq::Keypoint in cv-engine/include/keypoints.h."""

    x: float
    y: float
    z: float
    visibility: float


class Frame(BaseModel):
    """Mirrors formiq::Frame in cv-engine/include/keypoints.h."""

    timestamp_sec: float
    landmarks: list[Keypoint]
