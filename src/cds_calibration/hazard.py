"""Piece-wise hazard rate helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import numpy as np


@dataclass(slots=True)
class HazardSegment:
    start: float
    end: float
    hazard_rate: float

    def survival_factor(self, time: float) -> float:
        clamped = max(0.0, min(time, self.end) - self.start)
        return float(np.exp(-self.hazard_rate * clamped))


@dataclass(slots=True)
class PiecewiseHazardRateCurve:
    segments: Sequence[HazardSegment]

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("segments are required")
        starts = [seg.start for seg in self.segments]
        if starts[0] != 0.0:
            raise ValueError("curve must start at 0")
        for prev, cur in zip(self.segments, self.segments[1:]):
            if cur.start != prev.end:
                raise ValueError("segments must be contiguous")

    @property
    def maturities(self) -> List[float]:
        return [segment.end for segment in self.segments]

    def survival_probability(self, time: float) -> float:
        total_log = 0.0
        for seg in self.segments:
            if time <= seg.start:
                break
            contrib = max(0.0, min(time, seg.end) - seg.start)
            total_log += seg.hazard_rate * contrib
            if time <= seg.end:
                break
        return float(np.exp(-total_log))

    def intensity(self, time: float) -> float:
        for seg in self.segments:
            if seg.start <= time <= seg.end:
                return seg.hazard_rate
        return self.segments[-1].hazard_rate

    def replace_last_segment(self, hazard_rate: float) -> "PiecewiseHazardRateCurve":
        *head, last = self.segments
        new_last = HazardSegment(start=last.start, end=last.end, hazard_rate=hazard_rate)
        return PiecewiseHazardRateCurve(segments=[*head, new_last])

    @classmethod
    def from_hazard_rates(cls, maturities: Sequence[float], hazards: Sequence[float]) -> "PiecewiseHazardRateCurve":
        if len(maturities) != len(hazards):
            raise ValueError("maturities and hazards length mismatch")
        segments: List[HazardSegment] = []
        last = 0.0
        for maturity, hazard in zip(maturities, hazards):
            segments.append(HazardSegment(start=last, end=maturity, hazard_rate=hazard))
            last = maturity
        return cls(segments=segments)

    def extend(self, maturity: float, hazard_rate: float) -> "PiecewiseHazardRateCurve":
        segments = list(self.segments)
        segments.append(HazardSegment(start=segments[-1].end, end=maturity, hazard_rate=hazard_rate))
        return PiecewiseHazardRateCurve(segments=segments)

    @classmethod
    def flat(cls, hazard_rate: float, maturity: float, steps: int) -> "PiecewiseHazardRateCurve":
        dt = maturity / steps
        segments = [HazardSegment(start=i * dt, end=(i + 1) * dt, hazard_rate=hazard_rate) for i in range(steps)]
        return cls(segments=segments)


def bootstrap_grid(maturities: Iterable[float]) -> List[Tuple[float, float]]:
    sorted_mats = sorted(set(float(m) for m in maturities))
    grid: List[Tuple[float, float]] = []
    last = 0.0
    for maturity in sorted_mats:
        grid.append((last, maturity))
        last = maturity
    return grid

