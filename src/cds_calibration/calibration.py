"""Piece-wise hazard calibration routines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import numpy as np
from scipy.optimize import brentq

from .curves import DiscountCurve
from .hazard import HazardSegment, PiecewiseHazardRateCurve
from .valuation import CDSQuote, ISDAVParameters, par_spread


CALIBRATION_BOUNDS = (1e-6, 5.0)


@dataclass(slots=True)
class CalibrationResult:
    hazard_curve: PiecewiseHazardRateCurve
    par_spread_errors: List[float]


def calibrate_piecewise_hazard(
    quotes: Iterable[CDSQuote],
    discount_curve: DiscountCurve,
    params: ISDAVParameters,
) -> CalibrationResult:
    sorted_quotes = sorted(quotes, key=lambda q: q.maturity)
    if not sorted_quotes:
        raise ValueError("quotes are required")

    segments: List[HazardSegment] = []
    par_errors: List[float] = []

    for quote in sorted_quotes:
        start = segments[-1].end if segments else 0.0
        segments.append(HazardSegment(start=start, end=quote.maturity, hazard_rate=0.01))

        def objective(hazard: float) -> float:
            segments[-1] = HazardSegment(start=start, end=quote.maturity, hazard_rate=hazard)
            curve = PiecewiseHazardRateCurve(segments=list(segments))
            model = par_spread(
                hazard_curve=curve,
                discount_curve=discount_curve,
                maturity=quote.maturity,
                params=params,
            )
            return model - quote.spread_decimal

        root = brentq(objective, *CALIBRATION_BOUNDS)
        segments[-1] = HazardSegment(start=start, end=quote.maturity, hazard_rate=root)
        curve = PiecewiseHazardRateCurve(segments=list(segments))
        error = objective(root)
        par_errors.append(error)

    final_curve = PiecewiseHazardRateCurve(segments=segments)
    return CalibrationResult(hazard_curve=final_curve, par_spread_errors=par_errors)

