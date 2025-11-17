from pathlib import Path

import pandas as pd
import yaml

from cds_calibration.calibration import calibrate_piecewise_hazard
from cds_calibration.cli import _build_discount_curve, _build_isda_params, _build_quotes  # type: ignore


def _render_table(df: pd.DataFrame, title: str) -> str:
    """Return a simple console-friendly table with a title banner."""

    # Align headers nicely and avoid pandas printing the index column.
    content = df.to_string(index=False, float_format=lambda x: f"{x:,.6f}")
    border = "=" * len(title)
    return f"{title}\n{border}\n{content}\n"


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

    # Produce a verbose summary of the calibration so pytest -s shows useful context.
    hazard_table = pd.DataFrame(
        [
            {
                "Start (y)": seg.start,
                "End (y)": seg.end,
                "Hazard Rate (bps)": seg.hazard_rate * 10_000,
            }
            for seg in result.hazard_curve.segments
        ]
    )
    print(_render_table(hazard_table, "Hazard Curve Segments"))

    error_table = pd.DataFrame(
        [
            {
                "Maturity (y)": quote.maturity,
                "Market Spread (bps)": quote.spread_decimal * 10_000,
                "Model Error (bps)": error * 10_000,
            }
            for quote, error in zip(quotes, result.par_spread_errors)
        ]
    )
    commentary = (
        "All model errors are effectively zero (floating point noise), which means the "
        "piece-wise hazard curve exactly reproduces the market par spreads for the sample "
        "quotes."
    )
    print(_render_table(error_table, "Par Spread Reconciliation"))
    print(commentary)
