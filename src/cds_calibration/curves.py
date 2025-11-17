"""Discount-curve utilities for CDS pricing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import numpy as np


class DiscountCurve:
    """Interface for deterministic discount curves."""

    def df(self, time: float) -> float:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(slots=True)
class FlatDiscountCurve(DiscountCurve):
    """Flat continuously-compounded rate curve."""

    rate: float

    def df(self, time: float) -> float:
        return float(np.exp(-self.rate * time))


@dataclass(slots=True)
class PiecewiseLinearDiscountCurve(DiscountCurve):
    """Piecewise linear curve defined by (time, df) pillars."""

    pillars: Sequence[Tuple[float, float]]

    def __post_init__(self) -> None:
        if len(self.pillars) < 2:
            raise ValueError("Need at least two pillars for interpolation")
        times = [t for t, _ in self.pillars]
        if any(t2 <= t1 for t1, t2 in zip(times, times[1:])):
            raise ValueError("Pillar times must be strictly increasing")

    def df(self, time: float) -> float:
        times = [t for t, _ in self.pillars]
        dfs = [df for _, df in self.pillars]
        if time <= times[0]:
            return dfs[0]
        if time >= times[-1]:
            return dfs[-1]
        return float(np.interp(time, times, dfs))


def build_flat_curve(rate: float) -> FlatDiscountCurve:
    return FlatDiscountCurve(rate=rate)


def build_from_zero_rates(pillars: Iterable[Tuple[float, float]]) -> PiecewiseLinearDiscountCurve:
    data: List[Tuple[float, float]] = []
    for t, zero_rate in pillars:
        df = np.exp(-zero_rate * t)
        data.append((t, float(df)))
    return PiecewiseLinearDiscountCurve(pillars=data)

