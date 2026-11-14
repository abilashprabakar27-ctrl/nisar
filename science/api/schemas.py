"""Frozen result contract (draft v0). Field names are agreed with the server owner at the contract meeting."""
from dataclasses import dataclass, field, asdict
from typing import Literal

Status = Literal["ok", "insufficient_data", "error"]
Source = Literal["live", "saved", "sample"]
Confidence = Literal["High", "Medium", "Lower"]
Label = Literal["likely_became_water", "likely_water_receded", "likely_flooded_vegetation", "no_change"]


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
    # --- provenance (Final Architecture s4/s9): API rejects 'ok' results without these ---
    quality_level: str | None = None           # lowest level among passes used
    polarization: str | None = None            # e.g. "HH", "HH+HV"
    method_version: str | None = None
    referee_files: list[str] = field(default_factory=list)
    measured: str = ""                         # what the radar measured
    interpreted: str = ""                      # what it probably means (always 'likely')

    def to_dict(self) -> dict:
        return asdict(self)


def validate_result(d: dict) -> None:
    """Honesty rule: an 'ok' result must carry quality, confidence, provenance. Raises ValueError."""
    if d.get("status") != "ok":
        return
    missing = [k for k in ("quality_level", "confidence", "polarization", "method_version", "measured", "interpreted")
               if not d.get(k)]
    if not d.get("before") or not d.get("after"):
        missing.append("before/after passes")
    if missing:
        raise ValueError("result missing required provenance: " + ", ".join(missing))
