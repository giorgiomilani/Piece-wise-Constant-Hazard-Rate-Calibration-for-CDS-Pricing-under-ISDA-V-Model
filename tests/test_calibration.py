from pathlib import Path

import yaml

from cds_calibration.calibration import calibrate_piecewise_hazard
from cds_calibration.cli import _build_discount_curve, _build_isda_params, _build_quotes  # type: ignore


def load_config():
    path = Path(__file__).resolve().parents[1] / "examples" / "sample_quotes.yaml"
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_calibration_matches_market():
    config = load_config()
    discount_curve = _build_discount_curve(config)
    quotes = _build_quotes(config)
    params = _build_isda_params(config)
    result = calibrate_piecewise_hazard(
        quotes=quotes,
        discount_curve=discount_curve,
        params=params,
    )

    assert all(seg.hazard_rate > 0 for seg in result.hazard_curve.segments)
    for quote, error in zip(quotes, result.par_spread_errors):
        assert abs(error) < 1e-10, f"Par spread mismatch for {quote.maturity}y"
