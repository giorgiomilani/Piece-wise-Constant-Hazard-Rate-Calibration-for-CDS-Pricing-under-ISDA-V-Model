# Piece-wise Constant Hazard Rate Calibration for CDS Pricing

This repository provides a minimal yet production-oriented Python implementation of the ISDA V full fair value model described in **Burgess (2022)**. The code base focuses on calibrating a piece-wise constant hazard-rate term structure to quoted Credit Default Swap (CDS) spreads and then valuing contracts via the ISDA standard premium and protection legs.

## Features

- 📦 **Modern Python package** with a `src/` layout, `pyproject.toml`, and Typer-powered CLI.
- 📈 **Piece-wise hazard-curve calibration** that sequentially solves for default intensities matching market spreads.
- 🏛️ **ISDA premium and protection leg valuation** routines built on deterministic discount curves.
- 🧮 **Full ISDA V cash-flow conventions** including configurable step-in/cash-settle offsets and accrual-on-default support.
- 🖥️ **Console workflow** driven by Typer that prints hazard rates first and then CDS prices so valuation outputs stay consistent.
- 📊 **Automatic diagnostic plots** covering hazard steps, survival/default probabilities, and PV contributions for each tenor.
- ✅ **Pytest** smoke test guarding the calibration pipeline.
- 🧪 **Example configuration** demonstrating how to replicate the Burgess (2022) scenarios.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Once installed, the `cds-calibrate` console script becomes available everywhere inside the virtual environment.

## CLI Usage

The Typer CLI keeps the repo "production ready" by letting you run the same calibration logic in a repeatable way. All inputs are provided via a structured config file (YAML or JSON).

```bash
cds-calibrate --help
```

The main command expects a single argument: the path to the configuration file. Example:

```bash
cds-calibrate examples/sample_quotes.yaml
```

The CLI performs four steps:

1. **Load config** – parse the YAML/JSON and build the flat or pillar-based discount curve plus the CDS quotes to match.
2. **Calibrate** – sequentially solve for the piece-wise hazard rates that make the model par spreads equal to the quoted spreads.
3. **Publish outputs** – print the calibrated hazard rates **first** and then the CDS prices (premium leg PV, protection leg PV, and the resulting net price) for each tenor.
4. **Plot diagnostics** – save PNGs so you can visually inspect hazard levels, conditional survival/default probabilities, and PV contributions.

This makes it simple to plug in alternative data sources: just swap out the configuration file and re-run the same command.

### Configuration schema

The shipped configuration (`examples/sample_quotes.yaml`) shows the minimal fields:

```yaml
recovery_rate: 0.4          # Contractual recovery used in both calibration and valuation
frequency: 4                # Coupon payments per year (quarterly)
isda_v:
  step_in_days: 1           # T+1 step-in (valuation to protection start)
  cash_settle_days: 3       # ISDA standard cash-settle lag after coupons/defaults
  day_count: 365            # Day-count basis controlling calendar -> year conversion
  accrual_on_default: true  # Include accrual-on-default in premium leg PV
discount_curve:             # Discount curve builder instructions
  type: flat                # "flat" for a single continuously compounded zero rate
  rate: 0.015
quotes:                     # Market par spreads to match
  - maturity: 1             # CDS tenor in years
    spread_bps: 120         # Spread quoted in basis points
  - maturity: 3
    spread_bps: 145
  - maturity: 5
    spread_bps: 170
  - maturity: 7
    spread_bps: 210
```

Advanced curves can be specified by setting `discount_curve.type: pillars` and supplying `pillars: [[tenor_years, zero_rate], ...]`. The CLI also accepts JSON files with the same keys, making it easy to integrate with other systems. Pass `--plot-dir <folder>` (defaults to `plots/`) to control where the PNG diagnostics land.

The `isda_v` block activates the additional conventions Burgess (2022) calls for:

- `step_in_days` – difference between valuation date and protection start (defaults to T+1).
- `cash_settle_days` – lag applied to coupon/default payments (defaults to 3 business days).
- `day_count` – denominator that turns calendar-day inputs into year fractions.
- `accrual_on_default` – toggles the premium-leg accrual that is paid when default happens mid-period.

These settings flow through to both calibration and valuation so the quoted spreads you provide are matched under the full ISDA V conventions rather than the simplistic "flat" CDS model.

### Premium leg decomposition

Burgess (2022) writes the premium leg as two additive components:

- **Coupons**: \( PV_{\text{coupon}} = S \sum_i \alpha_i D(T_i + \Delta) Q(T_i) \)
- **Accrual-on-default**: \( PV_{\text{AoD}} = S \sum_i \int_{T_{i-1}}^{T_i} (t - T_{i-1}) D(t + \Delta) \, d(1 - Q(t)) \)

where `S` is the running spread, `α_i` the accrual fractions, `Δ` the step-in plus cash-settle lag, and `Q(t)` the survival curve generated by the calibrated hazard rates. The helper `premium_leg_breakdown(...)` in `cds_calibration.valuation` evaluates these expressions directly by integrating the default-density term \(d(1-Q(t)) = \lambda(t)Q(t) dt\) with a sufficiently fine grid inside each coupon period. The CLI surfaces both contributions so you can check how much of the premium PV comes from accrued interest versus regular coupons.

## Project Structure

```
.
├── pyproject.toml         # Packaging metadata, dependencies, entry points
├── examples/              # YAML/JSON config samples for the CLI
├── src/cds_calibration/   # Core library code (see below for details)
└── tests/                 # Pytest regression tests
```

### Library modules

- `src/cds_calibration/curves.py` – deterministic discount-curve helpers, including a `FlatDiscountCurve` and builder utilities for custom zero-rate pillars.
- `src/cds_calibration/hazard.py` – piece-wise constant hazard-curve representation plus helper functions for survival probabilities and segment manipulation.
- `src/cds_calibration/valuation.py` – ISDA V premium- and protection-leg PV engines, plus helper dataclasses such as `CDSQuote` and the par-spread calculator.
- `src/cds_calibration/calibration.py` – sequential solver that matches hazard rates to market spreads using the valuation layer.
- `src/cds_calibration/cli.py` – Typer entry point that wires configs to calibration/valuation routines and produces human-readable diagnostics.

### Supporting assets

- `examples/sample_quotes.yaml` – starter dataset described above that can be modified or replaced with proprietary quotes.
- `tests/test_calibration.py` – ensures the calibration routine reproduces the sample par spreads under the shipped config.

Together, these components give you a small but fully structured codebase: configs and CLI for orchestration, modular Python packages for valuation logic, and automated tests for confidence.

## References

- Burgess, A. (2022). *Full Fair Value CDS Pricing under the ISDA Standard Model*. Internal research note.
- ISDA. (2020). *Standard Model for CDS Pricing*. International Swaps and Derivatives Association.

## License

MIT License. See `LICENSE` if provided.

