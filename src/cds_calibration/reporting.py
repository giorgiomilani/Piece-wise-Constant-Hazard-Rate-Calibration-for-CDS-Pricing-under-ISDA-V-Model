"""Reporting helpers for CLI/scripts."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Sequence

from .curves import DiscountCurve
from .hazard import PiecewiseHazardRateCurve
from .valuation import (
    CDSQuote,
    ISDAVParameters,
    par_spread,
    premium_leg_breakdown,
    protection_leg_pv,
)


@dataclass(slots=True)
class PricingRow:
    """Container describing PV contributions for a given tenor."""

    maturity: float
    premium: float
    protection: float
    net: float
    coupon: float
    accrual: float

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass(slots=True)
class ParErrorRow:
    """Market vs model par spread reconciliation."""

    maturity: float
    market_bps: float
    model_bps: float
    error_bps: float

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


def price_quotes(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    quotes: Sequence[CDSQuote],
    params: ISDAVParameters,
) -> List[PricingRow]:
    rows: List[PricingRow] = []
    for quote in quotes:
        breakdown = premium_leg_breakdown(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            maturity=quote.maturity,
            spread=quote.spread_decimal,
            params=params,
        )
        protection = protection_leg_pv(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            maturity=quote.maturity,
            params=params,
        )
        rows.append(
            PricingRow(
                maturity=quote.maturity,
                premium=breakdown.total,
                protection=protection,
                net=protection - breakdown.total,
                coupon=breakdown.coupon_pv,
                accrual=breakdown.accrual_on_default_pv,
            )
        )
    return rows


def par_reconciliation(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    quotes: Sequence[CDSQuote],
    params: ISDAVParameters,
) -> List[ParErrorRow]:
    rows: List[ParErrorRow] = []
    for quote in quotes:
        model = par_spread(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            maturity=quote.maturity,
            params=params,
        )
        rows.append(
            ParErrorRow(
                maturity=quote.maturity,
                market_bps=quote.spread_bps,
                model_bps=model * 10_000.0,
                error_bps=(model - quote.spread_decimal) * 10_000.0,
            )
        )
    return rows
