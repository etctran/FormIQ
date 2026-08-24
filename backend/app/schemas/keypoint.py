from pydantic import BaseModel, ConfigDict


class Keypoint(BaseModel):
    """Mirrors formiq::Keypoint in cv-engine/include/keypoints.h."""

    model_config = ConfigDict(from_attributes=True)

    x: float
    y: float
    z: float
    visibility: float


class Frame(BaseModel):
    """Mirrors formiq::Frame in cv-engine/include/keypoints.h."""

    model_config = ConfigDict(from_attributes=True)

    timestamp_sec: float
    landmarks: list[Keypoint]
