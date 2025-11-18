"""Run extended calibration examples and print detailed tables."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd
import yaml

from cds_calibration.calibration import CalibrationResult, calibrate_piecewise_hazard
from cds_calibration.cli import _build_discount_curve, _build_isda_params, _build_quotes
from cds_calibration.curves import DiscountCurve
from cds_calibration.hazard import HazardSegment, PiecewiseHazardRateCurve
from cds_calibration.valuation import (
    CDSQuote,
    ISDAVParameters,
    par_spread,
)
from cds_calibration.reporting import (
    ParErrorRow,
    PricingRow,
    par_reconciliation,
    price_quotes,
)

CONFIG_PATH = Path(__file__).with_name("sample_quotes.yaml")
ANSI_GREEN = "\033[92m"
ANSI_RED = "\033[91m"
ANSI_CYAN = "\033[96m"
ANSI_RESET = "\033[0m"
FIVE_YEAR_TENOR = 5.0


def _load_config(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _render_table(df: pd.DataFrame, title: str) -> str:
    border = "=" * len(title)
    formatted = df.to_string(index=False, float_format=lambda x: f"{x:,.6f}")
    return f"{title}\n{border}\n{formatted}\n"


def _colorize_change(value: float, fmt: str = "{:+,.6f}") -> str:
    if abs(value) < 1e-10:
        color = ANSI_CYAN
    elif value > 0:
        color = ANSI_RED
    else:
        color = ANSI_GREEN
    return f"{color}{fmt.format(value)}{ANSI_RESET}"


def _calibrate(
    quotes: Sequence[CDSQuote],
    discount_curve: DiscountCurve,
    params: ISDAVParameters,
) -> CalibrationResult:
    return calibrate_piecewise_hazard(
        quotes=quotes,
        discount_curve=discount_curve,
        params=params,
    )


def _hazard_table(segments: Iterable[HazardSegment]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Start (y)": seg.start,
                "End (y)": seg.end,
                "Hazard Rate (%)": seg.hazard_rate * 100.0,
            }
            for seg in segments
        ]
    )


def _pricing_table(rows: Sequence[PricingRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Mat (y)": row.maturity,
                "Premium PV": row.premium,
                "Protection PV": row.protection,
                "Net PV": row.net,
                "Coupon PV": row.coupon,
                "Accrual PV": row.accrual,
            }
            for row in rows
        ]
    )


def _par_table(rows: Sequence[ParErrorRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Maturity (y)": row.maturity,
                "Market (bps)": row.market_bps,
                "Model (bps)": row.model_bps,
                "Error (bps)": row.error_bps,
            }
            for row in rows
        ]
    )


def _parallel_bump(quotes: Sequence[CDSQuote], bump_bps: float) -> List[CDSQuote]:
    return [replace(quote, spread_bps=quote.spread_bps + bump_bps) for quote in quotes]


def _scale_spreads(quotes: Sequence[CDSQuote], scale: float) -> List[CDSQuote]:
    return [replace(quote, spread_bps=quote.spread_bps * scale) for quote in quotes]


def _five_year_par_spread(
    hazard_curve: PiecewiseHazardRateCurve,
    discount_curve: DiscountCurve,
    params: ISDAVParameters,
) -> float:
    return (
        par_spread(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            maturity=FIVE_YEAR_TENOR,
            params=params,
        )
        * 10_000
    )


def _scenario_sensitivity(
    base_quotes: Sequence[CDSQuote],
    discount_curve: DiscountCurve,
    params: ISDAVParameters,
    bumps: Sequence[float] = (-50, -25, -10, 0, 10, 25, 50),
) -> pd.DataFrame:
    base_result = _calibrate(base_quotes, discount_curve, params)
    base_pricing = price_quotes(
        hazard_curve=base_result.hazard_curve,
        discount_curve=discount_curve,
        quotes=base_quotes,
        params=params,
    )
    base_net_pv = sum(row.net for row in base_pricing)
    base_five_year = _five_year_par_spread(base_result.hazard_curve, discount_curve, params)

    rows: List[dict] = []
    for bump in bumps:
        bumped_quotes = _parallel_bump(base_quotes, bump)
        result = _calibrate(bumped_quotes, discount_curve, params)
        pricing = price_quotes(
            hazard_curve=result.hazard_curve,
            discount_curve=discount_curve,
            quotes=bumped_quotes,
            params=params,
        )
        net_pv = sum(row.net for row in pricing)
        five_year = _five_year_par_spread(result.hazard_curve, discount_curve, params)
        rows.append(
            {
                "Spread bump (bps)": bump,
                "5Y par (bps)": five_year,
                "Δ 5Y par (bps)": _colorize_change(five_year - base_five_year, fmt="{:+,.3f}"),
                "Total net PV": net_pv,
                "Δ net PV": _colorize_change(net_pv - base_net_pv, fmt="{:+,.6f}"),
            }
        )

    return pd.DataFrame(rows)


def run_examples(config_path: Path = CONFIG_PATH) -> None:
    config = _load_config(config_path)
    params = _build_isda_params(config)
    base_quotes = _build_quotes(config)
    discount_curve = _build_discount_curve(config)

    scenarios = [
        ("Base market quotes", base_quotes),
        ("Wider spreads (+25 bps)", _parallel_bump(base_quotes, 25.0)),
        ("Tighter spreads (50% of market)", _scale_spreads(base_quotes, 0.5)),
    ]

    for name, quotes in scenarios:
        print(f"\n=== Scenario: {name} ===\n")
        result = _calibrate(quotes, discount_curve, params)
        hazard_curve = result.hazard_curve
        pricing_rows = price_quotes(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            quotes=quotes,
            params=params,
        )
        par_rows = par_reconciliation(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            quotes=quotes,
            params=params,
        )
        print(_render_table(_hazard_table(hazard_curve.segments), "Hazard curve"))
        print(
            _render_table(
                _pricing_table(pricing_rows),
                "Premium vs protection PV",
            )
        )
        print(
            _render_table(
                _par_table(par_rows),
                "Par spread reconciliation",
            )
        )

    sensitivity = _scenario_sensitivity(base_quotes, discount_curve, params)
    print(_render_table(sensitivity, "Parallel spread sensitivity"))


def main() -> None:
    run_examples()


if __name__ == "__main__":
    main()
