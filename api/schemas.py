"""Frozen result contract (draft v0). Field names are agreed with the server owner at the contract meeting."""
from dataclasses import dataclass, field, asdict
from typing import Literal

Status = Literal["ok", "insufficient_data", "error"]
Source = Literal["live", "saved", "sample"]
Confidence = Literal["High", "Medium", "Lower"]
Label = Literal["likely_became_water", "likely_water_receded", "no_change"]


@dataclass
class PassRef:
    scene: str
    date: str          # ISO date
    track: int
    direction: str     # ASCENDING | DESCENDING
    frame: int
    quality: str       # BETA | PROVISIONAL | VALIDATED


@dataclass
class ChangeResult:
    status: Status
    source: Source
    bbox: tuple[float, float, float, float]    # lon_min, lat_min, lon_max, lat_max
    before: list[PassRef] = field(default_factory=list)
    after: list[PassRef] = field(default_factory=list)
    area_ha: dict[str, float] = field(default_factory=dict)  # keyed by Label
    confidence: Confidence | None = None
    confidence_reason: str = ""
    masked_fraction: float = 0.0
    limits: list[str] = field(default_factory=list)
    result_map: str | None = None              # path/URL of overlay
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
