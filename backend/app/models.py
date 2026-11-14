"""Request shapes (the contract shared with the website)."""
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


def check_bbox(b: list[float]) -> list[float]:
    if len(b) != 4:
        raise ValueError("bbox must be [west, south, east, north]")
    w, s, e, n = b
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("bbox values are out of order or out of range")
    return b


class _HasBBox(BaseModel):
    bbox: list[float] = Field(..., description="[west, south, east, north] in degrees")

    @field_validator("bbox")
    @classmethod
    def _bbox(cls, v):
        return check_bbox(v)


class AvailabilityRequest(_HasBBox):
    start: str = "2026-06-17"
    end: Optional[str] = None


class AnalysisRequest(_HasBBox):
    name: str = "Study area"
    question: Literal["change", "diff", "much", "why", "now"] = "change"
    event_date: Optional[str] = Field(None, description="Change date YYYY-MM-DD: passes before it vs on/after it")
    before: Optional[list[str]] = Field(None, description="[start, end] window for the before group")
    after: Optional[list[str]] = Field(None, description="[start, end] window for the after group")
    looking_for: list[str] = ["water"]
    quick: bool = False


class DownloadRequest(_HasBBox):
    name: str = "Study area"
    event_date: Optional[str] = Field(None, description="With scope 'question': the change date of the question")
    scope: Literal["all", "question"] = Field("all", description="all = every pass on the best track; question = the 2+2 passes an analysis needs")
    extras: bool = Field(True, description="Also fetch rain, land height and fires for the Why screen")


class WatchRequest(_HasBBox):
    name: str = "Study area"
    last_result_date: Optional[str] = None
    analysis_id: Optional[str] = None


class Pass(BaseModel):
    date: str
    track: str
    direction: str
    frame: Optional[str] = None
    quality: str = "Unknown"
    polarizations: list[str] = []
    url: Optional[str] = None
    name: Optional[str] = None
