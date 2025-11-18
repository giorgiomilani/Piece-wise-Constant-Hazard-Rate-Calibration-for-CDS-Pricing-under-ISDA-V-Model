# Piece-wise Constant Hazard Rate Calibration for CDS Pricing

This repository provides a minimal yet production-oriented Python implementation of the ISDA V full fair value model described in **Burgess (2022)**. The code base focuses on calibrating a piece-wise constant hazard-rate term structure to quoted Credit Default Swap (CDS) spreads and then valuing contracts via the ISDA standard premium and protection legs.


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
3. **Publish outputs** – print the calibrated hazard rates **first** and then the CDS prices (premium leg PV, PV01/annuity, protection leg PV, and the resulting net price) for each tenor.
4. **Plot diagnostics** – save PNGs so you can visually inspect hazard levels, conditional survival/default probabilities, and PV contributions.

This makes it simple to plug in alternative data sources: just swap out the configuration file and re-run the same command.

### Configuration schema

The shipped configuration (`examples/sample_quotes.yaml`) shows the minimal fields:

```yaml
recovery_rate: 0.4          # Contractual recovery used in both calibration and valuation
frequency: 4                # Coupon payments per year (quarterly)
notional: 10_000_000        # Optional notional for scaled PVs (defaults to 1)
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

If you want a richer starting point, `examples/advanced_curve_quotes.yaml` demonstrates:

- A continuously compounded piece-wise linear discount curve bootstrapped from zero-rate pillars spanning the 3-month to 30-year points.
- Thirteen CDS quotes (0.5y through 30y) so you can stress-test the calibration routine on a long credit curve.
- Explicit notional, metadata, and stress-scenario placeholders so the config mirrors typical trading spreadsheets.
- Additional (commented) knobs showing where you could plug in custom business-day or accrual settings if you extend the schema locally.

Run it the same way as the minimal file:

```bash
cds-calibrate examples/advanced_curve_quotes.yaml
```

After calibration the CLI prints per-unit PVs plus PV01 (premium-leg annuity per basis point). If a `notional` is supplied in the config you will also see the same figures scaled to that size, matching the PV01 + accrued adjustment view traders typically use.

The `isda_v` block activates the additional conventions Burgess (2022) calls for:

- `step_in_days` – difference between valuation date and protection start (defaults to T+1).
- `cash_settle_days` – lag applied to coupon/default payments (defaults to 3 business days).
- `day_count` – denominator that turns calendar-day inputs into year fractions.
- `accrual_on_default` – toggles the premium-leg accrual that is paid when default happens mid-period.

These settings flow through to both calibration and valuation so the quoted spreads you provide are matched under the full ISDA V conventions rather than the simplistic "flat" CDS model.


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


## References

- Burgess, A. (2022). *Credit Derivative Theory & Practice - A Credit Primer & Review of the Impact of ISDA Standardization on Credit Default Swap Pricing & Credit Model Calibration.*
- ISDA. (2020). *Standard Model for CDS Pricing*.

## License

MIT License. See `LICENSE` if provided.

