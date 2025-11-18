"""Matplotlib helpers for CDS diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .hazard import PiecewiseHazardRateCurve
from .reporting import ParErrorRow, PricingRow
from .valuation import ISDAVParameters


def save_core_diagnostics(
    hazard_curve: PiecewiseHazardRateCurve,
    params: ISDAVParameters,
    quotes: Sequence,
    pricing_rows: Sequence[PricingRow],
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if not quotes:
        return
    plot_hazard_curve(hazard_curve, destination / "hazard_curve.png")
    plot_probabilities(hazard_curve, params, quotes[-1].maturity, destination / "survival_default.png")
    plot_pv_contributions(pricing_rows, destination / "pv_contributions.png")


def plot_hazard_curve(hazard_curve: PiecewiseHazardRateCurve, destination: Path) -> None:
    x: list[float] = []
    y: list[float] = []
    for segment in hazard_curve.segments:
        x.extend([segment.start, segment.end])
        y.extend([segment.hazard_rate, segment.hazard_rate])
    if not x:
        return
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


def plot_probabilities(
    hazard_curve: PiecewiseHazardRateCurve,
    params: ISDAVParameters,
    maturity: float,
    destination: Path,
) -> None:
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


def plot_pv_contributions(pricing_rows: Sequence[PricingRow], destination: Path) -> None:
    rows = list(pricing_rows)
    if not rows:
        return
    maturities = [row.maturity for row in rows]
    premium = [row.premium for row in rows]
    protection = [row.protection for row in rows]
    net = [row.net for row in rows]
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


def plot_premium_decomposition(pricing_rows: Sequence[PricingRow], destination: Path) -> None:
    rows = list(pricing_rows)
    if not rows:
        return
    maturities = [row.maturity for row in rows]
    coupon = np.array([row.coupon for row in rows], dtype=float)
    accrual = np.array([row.accrual for row in rows], dtype=float)
    x = np.arange(len(maturities))
    plt.figure(figsize=(7, 4))
    plt.bar(x, coupon, label="Coupon PV")
    plt.bar(x, accrual, bottom=coupon, label="Accrual PV")
    plt.xticks(x, [f"{m:.0f}y" for m in maturities])
    plt.ylabel("Present value")
    plt.title("Premium Leg Decomposition")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(destination)
    plt.close()


def plot_par_errors(rows: Sequence[ParErrorRow], destination: Path) -> None:
    data = list(rows)
    if not data:
        return
    maturities = [row.maturity for row in data]
    errors = [row.error_bps for row in data]
    x = np.arange(len(data))
    plt.figure(figsize=(7, 4))
    plt.bar(x, errors, color="tab:red")
    plt.axhline(0.0, color="black", linewidth=1)
    plt.xticks(x, [f"{m:.0f}y" for m in maturities])
    plt.ylabel("Error (bps)")
    plt.title("Par Spread Errors (Model - Market)")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(destination)
    plt.close()


def plot_sensitivity_curve(rows: Iterable[Mapping[str, float]], destination: Path) -> None:
    data = list(rows)
    if not data:
        return
    bumps = [row["bump_bps"] for row in data]
    delta_par = [row["delta_five_year_bps"] for row in data]
    delta_pv = [row["delta_net_pv"] for row in data]
    fig, ax1 = plt.subplots(figsize=(7, 4))
    ax1.plot(bumps, delta_par, marker="o", color="tab:blue", label="Δ 5Y par (bps)")
    ax1.set_xlabel("Parallel spread bump (bps)")
    ax1.set_ylabel("Δ 5Y par (bps)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.grid(True, axis="x", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(bumps, delta_pv, marker="s", color="tab:orange", label="Δ net PV")
    ax2.set_ylabel("Δ net PV", color="tab:orange")
    ax2.tick_params(axis="y", labelcolor="tab:orange")

    lines, labels = [], []
    for ax in (ax1, ax2):
        line, label = ax.get_legend_handles_labels()
        lines.extend(line)
        labels.extend(label)
    fig.legend(lines, labels, loc="upper left", bbox_to_anchor=(0.1, 0.95))
    plt.title("Parallel Spread Sensitivity")
    fig.tight_layout()
    plt.savefig(destination)
    plt.close(fig)
