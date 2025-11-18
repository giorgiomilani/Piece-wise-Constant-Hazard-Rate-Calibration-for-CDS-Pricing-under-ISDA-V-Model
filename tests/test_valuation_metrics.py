import math

from cds_calibration.curves import FlatDiscountCurve
from cds_calibration.hazard import HazardSegment, PiecewiseHazardRateCurve
from cds_calibration.valuation import (
    ISDAVParameters,
    premium_leg_annuity,
    premium_leg_pv,
    pv01,
)


def _fixtures():
    hazard = PiecewiseHazardRateCurve(segments=[HazardSegment(start=0.0, end=5.0, hazard_rate=0.02)])
    discount = FlatDiscountCurve(rate=0.01)
    params = ISDAVParameters(recovery_rate=0.4, frequency=4)
    return hazard, discount, params


def test_pv01_aligns_with_annuity():
    hazard, discount, params = _fixtures()
    annuity = premium_leg_annuity(hazard_curve=hazard, discount_curve=discount, maturity=5.0, params=params)
    pv01_value = pv01(hazard_curve=hazard, discount_curve=discount, maturity=5.0, params=params)
    assert math.isclose(annuity, pv01_value * 10_000.0, rel_tol=1e-12)


def test_premium_leg_scales_with_coupon():
    hazard, discount, params = _fixtures()
    annuity = premium_leg_annuity(hazard_curve=hazard, discount_curve=discount, maturity=5.0, params=params)
    spread = 150.0 / 10_000.0
    premium = premium_leg_pv(
        hazard_curve=hazard,
        discount_curve=discount,
        maturity=5.0,
        coupon=spread,
        params=params,
    )
    assert math.isclose(premium, annuity * spread, rel_tol=1e-12)
