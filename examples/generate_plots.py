"""Generate an extended set of CDS calibration plots."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Sequence

from cds_calibration.calibration import calibrate_piecewise_hazard
from cds_calibration.cli import (
    _build_discount_curve,
    _build_isda_params,
    _build_quotes,
    _load_config,
)
from cds_calibration.plots import (
    plot_par_errors,
    plot_sensitivity_curve,
    save_core_diagnostics,
)
from cds_calibration.reporting import par_reconciliation, price_quotes
from cds_calibration.valuation import CDSQuote, par_spread

DEFAULT_CONFIG = Path(__file__).with_name("sample_quotes.yaml")
DEFAULT_PLOT_DIR = Path("plots/extended")


def _parallel_bump(quotes: Sequence[CDSQuote], bump_bps: float) -> list[CDSQuote]:
    return [replace(quote, spread_bps=quote.spread_bps + bump_bps) for quote in quotes]


def _five_year_par(result, discount_curve, params) -> float:
    return par_spread(
        hazard_curve=result.hazard_curve,
        discount_curve=discount_curve,
        maturity=5.0,
        params=params,
    ) * 10_000.0


def _scenario_sensitivity(
    base_quotes: Sequence[CDSQuote],
    discount_curve,
    params,
    bumps: Iterable[float] = (-50, -25, -10, 0, 10, 25, 50),
):
    base_result = calibrate_piecewise_hazard(
        quotes=base_quotes,
        discount_curve=discount_curve,
        params=params,
    )
    base_pricing = price_quotes(base_result.hazard_curve, discount_curve, base_quotes, params)
    base_net = sum(row.net for row in base_pricing)
    base_five_year = _five_year_par(base_result, discount_curve, params)

    rows = []
    for bump in bumps:
        bumped_quotes = _parallel_bump(base_quotes, bump)
        result = calibrate_piecewise_hazard(
            quotes=bumped_quotes,
            discount_curve=discount_curve,
            params=params,
        )
        pricing = price_quotes(result.hazard_curve, discount_curve, bumped_quotes, params)
        net = sum(row.net for row in pricing)
        five_year = _five_year_par(result, discount_curve, params)
        rows.append(
            {
                "bump_bps": bump,
                "delta_five_year_bps": five_year - base_five_year,
                "delta_net_pv": net - base_net,
                "net_pv": net,
                "five_year_bps": five_year,
            }
        )
    return rows


def generate_plots(config_path: Path, plot_dir: Path) -> None:
    config = _load_config(config_path)
    params = _build_isda_params(config)
    quotes = _build_quotes(config)
    discount_curve = _build_discount_curve(config)

    result = calibrate_piecewise_hazard(
        quotes=quotes,
        discount_curve=discount_curve,
        params=params,
    )

    pricing_rows = price_quotes(result.hazard_curve, discount_curve, quotes, params)
    par_rows = par_reconciliation(result.hazard_curve, discount_curve, quotes, params)

    save_core_diagnostics(
        hazard_curve=result.hazard_curve,
        params=params,
        quotes=quotes,
        pricing_rows=pricing_rows,
        destination=plot_dir,
    )
    plot_par_errors(par_rows, plot_dir / "par_spread_errors.png")
    sensitivity_rows = _scenario_sensitivity(quotes, discount_curve, params)
    plot_sensitivity_curve(sensitivity_rows, plot_dir / "spread_sensitivity.png")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to YAML/JSON calibration config",
    )
    parser.add_argument(
        "--plot-dir",
        type=Path,
        default=DEFAULT_PLOT_DIR,
        help="Destination folder for all generated plots",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    generate_plots(args.config, args.plot_dir)
    print(f"Saved plots under {args.plot_dir.resolve()}")


if __name__ == "__main__":
    main()
