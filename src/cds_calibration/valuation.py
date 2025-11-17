"""ISDA V premium/protection leg valuation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .curves import DiscountCurve
from .hazard import PiecewiseHazardRateCurve


DEFAULT_DAY_COUNT = 365.0


@dataclass(slots=True)
class ISDAVParameters:
    """Container for ISDA V timing conventions."""

    recovery_rate: float
    frequency: int = 4
    step_in_days: int = 1
    cash_settle_days: int = 3
    accrual_day_count: float = DEFAULT_DAY_COUNT
    accrual_on_default: bool = True

    @property
    def step_in_years(self) -> float:
        return self.step_in_days / self.accrual_day_count

    @property
    def cash_settle_years(self) -> float:
        return self.cash_settle_days / self.accrual_day_count

    @property
    def payment_offset(self) -> float:
        return self.step_in_years + self.cash_settle_years

    @property
    def lgd(self) -> float:
        return 1.0 - self.recovery_rate


@dataclass(slots=True)
class PremiumLegBreakdown:
    """Premium leg decomposition showing coupon vs accrual PV."""

    coupon_pv: float
    accrual_on_default_pv: float

    @property
    def total(self) -> float:
        return self.coupon_pv + self.accrual_on_default_pv


def year_fractions(maturity: float, frequency: int) -> np.ndarray:
    count = int(round(maturity * frequency))
    if count <= 0:
        return np.array([], dtype=float)
    times = np.arange(1, count + 1) / frequency
    return times


def conditional_survival_probabilities(
    curve: PiecewiseHazardRateCurve, times: Sequence[float], params: ISDAVParameters
) -> np.ndarray:
    if len(times) == 0:
        return np.array([], dtype=float)
    offset = params.step_in_years
    base = curve.survival_probability(offset)
    if base <= 0.0:
        raise ValueError("Invalid survival probability at step-in date")
    surv = np.array([curve.survival_probability(offset + float(t)) for t in times], dtype=float)
    return surv / base


def _period_starts(times: np.ndarray) -> np.ndarray:
    if times.size == 0:
        return np.array([], dtype=float)
    return np.concatenate(([0.0], times[:-1]))


def _discount_factors(curve: DiscountCurve, times: np.ndarray, offset: float) -> np.ndarray:
    if times.size == 0:
        return np.array([], dtype=float)
    return np.array([curve.df(float(offset + t)) for t in times], dtype=float)


def premium_leg_breakdown(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    maturity: float,
    spread: float,
    params: ISDAVParameters,
) -> PremiumLegBreakdown:
    times = year_fractions(maturity, params.frequency)
    if times.size == 0:
        return PremiumLegBreakdown(coupon_pv=0.0, accrual_on_default_pv=0.0)
    starts = _period_starts(times)
    accruals = times - starts
    surv_end = conditional_survival_probabilities(hazard_curve, times, params)
    dfs_coupon = _discount_factors(discount_curve, times, params.payment_offset)
    coupon_leg = float(np.sum(spread * accruals * dfs_coupon * surv_end))

    if not params.accrual_on_default:
        return PremiumLegBreakdown(coupon_pv=coupon_leg, accrual_on_default_pv=0.0)

    accrual_on_default = _accrual_on_default_pv(
        hazard_curve=hazard_curve,
        discount_curve=discount_curve,
        params=params,
        starts=starts,
        ends=times,
        spread=spread,
    )
    return PremiumLegBreakdown(coupon_pv=coupon_leg, accrual_on_default_pv=accrual_on_default)


def premium_leg_pv(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    maturity: float,
    spread: float,
    params: ISDAVParameters,
) -> float:
    breakdown = premium_leg_breakdown(
        hazard_curve=hazard_curve,
        discount_curve=discount_curve,
        maturity=maturity,
        spread=spread,
        params=params,
    )
    return breakdown.total


def _default_densities(
    hazard_curve: PiecewiseHazardRateCurve,
    times: np.ndarray,
    params: ISDAVParameters,
) -> np.ndarray:
    if times.size == 0:
        return np.array([], dtype=float)
    offset = params.step_in_years
    base = hazard_curve.survival_probability(offset)
    if base <= 0.0:
        raise ValueError("Invalid survival probability at step-in date")
    densities = []
    for t in times:
        absolute = offset + float(t)
        survival = hazard_curve.survival_probability(absolute)
        intensity = hazard_curve.intensity(absolute)
        densities.append(intensity * survival / base)
    return np.array(densities, dtype=float)


def _integration_steps(length: float, params: ISDAVParameters) -> int:
    # Resolve to at least monthly granularity so the accrual integral follows Burgess (2022) notation.
    approx_days = max(length * params.accrual_day_count, 1.0)
    steps = max(6, int(np.ceil(approx_days / 15.0)))
    return min(512, steps)


def _accrual_on_default_pv(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    params: ISDAVParameters,
    starts: np.ndarray,
    ends: np.ndarray,
    spread: float,
) -> float:
    total = 0.0
    for start, end in zip(starts, ends):
        if end <= start:
            continue
        length = float(end - start)
        steps = _integration_steps(length, params)
        grid = np.linspace(start, end, steps + 1)
        densities = _default_densities(hazard_curve, grid, params)
        dfs = np.array([discount_curve.df(params.payment_offset + float(t)) for t in grid], dtype=float)
        integrand = (grid - start) * densities * dfs
        total += float(np.trapezoid(integrand, grid))
    return spread * total


def protection_leg_pv(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    maturity: float,
    params: ISDAVParameters,
) -> float:
    times = year_fractions(maturity, params.frequency)
    if times.size == 0:
        return 0.0
    starts = _period_starts(times)
    accruals = times - starts
    surv_end = conditional_survival_probabilities(hazard_curve, times, params)
    surv_start = conditional_survival_probabilities(hazard_curve, starts, params)
    defaults = surv_start - surv_end
    default_times = starts + 0.5 * accruals
    dfs = _discount_factors(discount_curve, default_times, params.payment_offset)
    return float(np.sum(params.lgd * dfs * defaults))


def par_spread(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    maturity: float,
    params: ISDAVParameters,
) -> float:
    prot = protection_leg_pv(
        hazard_curve=hazard_curve,
        discount_curve=discount_curve,
        maturity=maturity,
        params=params,
    )
    annuity = premium_leg_pv(
        hazard_curve=hazard_curve,
        discount_curve=discount_curve,
        maturity=maturity,
        spread=1.0,
        params=params,
    )
    if annuity == 0:
        raise ValueError("Premium leg annuity is zero; invalid maturity/frequency")
    return float(prot / annuity)


@dataclass(slots=True)
class CDSQuote:
    maturity: float
    spread_bps: float

    @property
    def spread_decimal(self) -> float:
        return self.spread_bps / 10000.0


def generate_quotes(data: Iterable[tuple[float, float]]) -> list[CDSQuote]:
    return [CDSQuote(maturity=maturity, spread_bps=spread) for maturity, spread in data]

