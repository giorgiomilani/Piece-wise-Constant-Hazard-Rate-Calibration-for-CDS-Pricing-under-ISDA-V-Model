"""Command line entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import typer
import yaml

from .calibration import calibrate_piecewise_hazard
from .curves import FlatDiscountCurve, build_from_zero_rates
from .plots import save_core_diagnostics
from .reporting import par_reconciliation, price_quotes
from .valuation import (
    CDSQuote,
    ISDAVParameters,
)

app = typer.Typer(help="ISDA V CDS calibration utilities")


def _load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix in {".yml", ".yaml"}:
            return yaml.safe_load(fh)
        return json.load(fh)


def _build_discount_curve(config: Dict[str, Any]):
    curve_cfg = config.get("discount_curve", {"type": "flat", "rate": 0.01})
    curve_type = curve_cfg.get("type", "flat")
    if curve_type == "flat":
        return FlatDiscountCurve(rate=float(curve_cfg.get("rate", 0.01)))
    if curve_type == "pillars":
        pillars = [(float(t), float(df)) for t, df in curve_cfg.get("pillars", [])]
        return build_from_zero_rates(pillars)
    raise typer.BadParameter(f"Unknown discount curve type: {curve_type}")


def _build_quotes(config: Dict[str, Any]):
    quotes_cfg = config.get("quotes")
    if not quotes_cfg:
        raise typer.BadParameter("quotes missing from configuration")
    return [CDSQuote(maturity=float(item["maturity"]), spread_bps=float(item["spread_bps"])) for item in quotes_cfg]


def _build_isda_params(config: Dict[str, Any]) -> ISDAVParameters:
    isda_cfg = config.get("isda_v", {})
    recovery_rate = float(config.get("recovery_rate", 0.4))
    frequency = int(config.get("frequency", 4))
    step_in_days = int(isda_cfg.get("step_in_days", 1))
    cash_settle_days = int(isda_cfg.get("cash_settle_days", 3))
    day_count = float(isda_cfg.get("day_count", 365.0))
    accrual_on_default = bool(isda_cfg.get("accrual_on_default", True))
    return ISDAVParameters(
        recovery_rate=recovery_rate,
        frequency=frequency,
        step_in_days=step_in_days,
        cash_settle_days=cash_settle_days,
        accrual_day_count=day_count,
        accrual_on_default=accrual_on_default,
    )


@app.command()
def main(
    config_path: Path,
    plot_dir: Path = typer.Option(Path("plots"), "--plot-dir", "-p", help="Directory for PNG diagnostics"),
) -> None:
    """Calibrate hazard curve, print hazard/prices, and save diagnostic plots."""

    config = _load_config(config_path)
    params = _build_isda_params(config)
    discount_curve = _build_discount_curve(config)
    quotes = _build_quotes(config)

    typer.echo("Running calibration...")
    result = calibrate_piecewise_hazard(
        quotes=quotes,
        discount_curve=discount_curve,
        params=params,
    )

    typer.echo("Calibrated hazard rates:")
    for quote, segment in zip(quotes, result.hazard_curve.segments):
        typer.echo(f"  {quote.maturity:>4.1f}y -> {segment.hazard_rate:.4%}")

    pricing_rows = price_quotes(
        hazard_curve=result.hazard_curve,
        discount_curve=discount_curve,
        quotes=quotes,
        params=params,
    )

    typer.echo("\nCDS PVs (premium first, then protection):")
    typer.echo(
        "  Mat    Premium PV    Protection PV       Net PV    Coupon PV   Accrual PV"
    )
    for row in pricing_rows:
        typer.echo(
            f"  {row.maturity:>4.1f}y  {row.premium:>11.6f}    {row.protection:>12.6f}    {row.net:>10.6f}    {row.coupon:>10.6f}   {row.accrual:>10.6f}"
        )

    typer.echo("\nValidation vs market par spreads:")
    par_rows = par_reconciliation(
        hazard_curve=result.hazard_curve,
        discount_curve=discount_curve,
        quotes=quotes,
        params=params,
    )
    typer.echo("  Mat    Market (bps)    Model (bps)    Error (bps)")
    for row in par_rows:
        typer.echo(
            f"  {row.maturity:>4.1f}y  {row.market_bps:>12.4f}    {row.model_bps:>11.4f}    {row.error_bps:>10.4f}"
        )

    plot_dir = plot_dir.expanduser()
    save_core_diagnostics(
        hazard_curve=result.hazard_curve,
        params=params,
        quotes=quotes,
        pricing_rows=pricing_rows,
        destination=plot_dir,
    )
    typer.echo(f"\nSaved diagnostic plots under {plot_dir.resolve()}")
if __name__ == "__main__":
    app()

