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
    par_spread,
    premium_leg_breakdown,
    protection_leg_pv,
    pv01,
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
    notional = float(config.get("notional", 1.0))
    if notional <= 0:
        raise typer.BadParameter("notional must be positive")
    discount_curve = _build_discount_curve(config)
    quotes = _build_quotes(config)

    typer.echo("Input parameters:")
    typer.echo(f"  Notional: {notional:,.2f}")
    typer.echo(f"  Recovery rate: {params.recovery_rate:.2%}")
    typer.echo(f"  Coupon frequency: {params.frequency}x per year")
    typer.echo(f"  Step-in / cash-settle (days): {params.step_in_days} / {params.cash_settle_days}")
    curve_cfg = config.get("discount_curve", {})
    curve_type = curve_cfg.get("type", "flat")
    if curve_type == "flat":
        typer.echo(f"  Discount curve: flat, rate={float(curve_cfg.get('rate', 0.0)):.4%}")
    elif curve_type == "pillars":
        typer.echo(f"  Discount curve: pillars ({len(curve_cfg.get('pillars', []))} nodes)")
    else:
        typer.echo(f"  Discount curve: {curve_type}")
    typer.echo(f"  Quotes loaded: {len(quotes)} maturities")

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
        notional=notional,
    )

    typer.echo("\nCDS PVs per unit notional:")
    typer.echo("  Mat    Premium       Protection        Net        PV01/bp")
    for row in pricing_rows:
        typer.echo(
            f"  {row['maturity']:>4.1f}y  {row['premium']:>10.6f}    {row['protection']:>10.6f}    {row['net']:>10.6f}"
            f"    {row['pv01']:>10.6f}"
        )

    if notional != 1.0:
        typer.echo(f"\nScaled PVs for notional {notional:,.2f}:")
        typer.echo("  Mat    Premium       Protection        Net        PV01/bp")
        for row in pricing_rows:
            typer.echo(
                f"  {row['maturity']:>4.1f}y  {row['premium_notional']:>10.2f}    {row['protection_notional']:>10.2f}"
                f"    {row['net_notional']:>10.2f}    {row['pv01_notional']:>10.2f}"
            )

    last = pricing_rows[-1]
    typer.echo("\nValuation summary at input spread (per unit notional):")
    typer.echo(f"  Premium leg PV:        {last['premium']:,.6f}")
    typer.echo(f"  PV01 (1bp annuity):    {last['pv01']:,.6f}")
    typer.echo(f"  Protection leg PV:     {last['protection']:,.6f}")
    typer.echo(f"  Net PV:                {last['net']:,.6f}")

    if notional != 1.0:
        typer.echo("\nScaled summary:")
        typer.echo(f"  Premium leg PV:        {last['premium_notional']:,.2f}")
        typer.echo(f"  PV01 (1bp annuity):    {last['pv01_notional']:,.2f}")
        typer.echo(f"  Protection leg PV:     {last['protection_notional']:,.2f}")
        typer.echo(f"  Net PV:                {last['net_notional']:,.2f}")

    typer.echo("\nLast maturity premium breakdown:")
    typer.echo(f"  Coupons:             {last['coupon']:,.6f}")
    typer.echo(f"  Accrual on default:  {last['accrual']:,.6f}")

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


def _price_quotes(
    hazard_curve,
    discount_curve,
    quotes,
    params,
    notional: float,
):
    rows: List[Dict[str, float]] = []
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
        unit_pv01 = pv01(
            hazard_curve=hazard_curve,
            discount_curve=discount_curve,
            maturity=quote.maturity,
            params=params,
        )
        rows.append(
            {
                "maturity": quote.maturity,
                "premium": breakdown.total,
                "protection": protection,
                "net": protection - breakdown.total,
                "coupon": breakdown.coupon_pv,
                "accrual": breakdown.accrual_on_default_pv,
                "pv01": unit_pv01,
                "premium_notional": breakdown.total * notional,
                "protection_notional": protection * notional,
                "net_notional": (protection - breakdown.total) * notional,
                "pv01_notional": unit_pv01 * notional,
            }
        )
    return rows


def _generate_plots(hazard_curve, params, quotes, pricing_rows, plot_dir: Path) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)
    _plot_hazard_curve(hazard_curve, plot_dir / "hazard_curve.png")
    _plot_probabilities(hazard_curve, params, quotes[-1].maturity, plot_dir / "survival_default.png")
    _plot_pv_contributions(pricing_rows, plot_dir / "pv_contributions.png")


def _plot_hazard_curve(hazard_curve, destination: Path) -> None:
    x: List[float] = []
    y: List[float] = []
    for segment in hazard_curve.segments:
        x.extend([segment.start, segment.end])
        y.extend([segment.hazard_rate, segment.hazard_rate])
    plt.figure(figsize=(6, 4))
    plt.plot(x, y, drawstyle="steps-post", label="Hazard rate")
    plt.xlabel("Time (years)")
    plt.ylabel("Hazard rate")
    plt.title("Piece-wise Hazard Structure")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(destination)
    plt.close()


def _plot_probabilities(hazard_curve, params, maturity: float, destination: Path) -> None:
    if maturity <= 0:
        return
    grid = np.linspace(0.0, maturity, 200)
    base = hazard_curve.survival_probability(params.step_in_years)
    surv = np.array(
        [hazard_curve.survival_probability(params.step_in_years + float(t)) for t in grid],
        dtype=float,
    )
    surv = surv / base
    default = 1.0 - surv
    plt.figure(figsize=(6, 4))
    plt.plot(grid, surv, label="Survival probability")
    plt.plot(grid, default, label="Default probability")
    plt.xlabel("Time (years)")
    plt.ylabel("Probability")
    plt.title("Conditional Survival vs Default")
    plt.ylim(0.0, 1.0)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(destination)
    plt.close()


def _plot_pv_contributions(pricing_rows: Iterable[Dict[str, float]], destination: Path) -> None:
    rows = list(pricing_rows)
    if not rows:
        return
    maturities = [row["maturity"] for row in rows]
    premium = [row["premium"] for row in rows]
    protection = [row["protection"] for row in rows]
    net = [row["net"] for row in rows]
    x = np.arange(len(maturities))
    width = 0.35
    plt.figure(figsize=(7, 4))
    plt.bar(x - width / 2, premium, width, label="Premium leg")
    plt.bar(x + width / 2, protection, width, label="Protection leg")
    plt.plot(x, net, color="black", marker="o", label="Net PV")
    plt.xticks(x, [f"{m:.0f}y" for m in maturities])
    plt.ylabel("Present value")
    plt.title("PV Contributions by Tenor")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(destination)
    plt.close()


if __name__ == "__main__":
    app()

