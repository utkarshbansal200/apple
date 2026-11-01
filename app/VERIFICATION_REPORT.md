# Verification report

This report is regenerated after executing the current source. It distinguishes software regression checks from empirical model validation.

## Verification scope

The test suite retains the pre-existing legacy-engine tests and rainfall-model tests, and adds checks for whole-day duration enforcement, zero-rainfall baseline consistency, custom-source diagnostics, complete-calendar-year validation, legacy-control irrelevance, successor schedule propagation and fixed-seed reproducibility.

## Claims and limits

- The software tests can establish deterministic implementation properties and arithmetic/schedule invariants for the tested cases.
- They cannot establish that the assumed rainfall-to-stoppage equation predicts actual construction disruption.
- No supervised construction-delay model has been trained; no labelled site-level outcomes were supplied.
- P50/P80/P90 are simulated distribution percentiles, not validated predictive accuracy.
- The processed rainfall CSV's original IMD provenance and extraction cannot be independently authenticated from the CSV alone.
- A Streamlit browser launch is reported only if it is actually executed in the current environment. Python compilation and pytest results are recorded from the actual run.

## Current execution record

Execution status and exact counts are appended by the correction build after pytest, compilation and benchmark execution. The benchmark is generated with the fixed benchmark seed and inputs in `run_benchmark.py`; reproducibility tests compare repeated outputs under identical inputs.

## Final correction-build execution record

- Pytest: **37 passed** (original 25 retained; 12 added).
- Python compilation: **passed** for `app.py`, `engine.py`, `rainfall_model.py` and `run_benchmark.py`.
- Full benchmark: **completed**, 10,000 draws for each of Mild, Typical and Severe; seed 42.
- Streamlit browser launch: **not executed** because the `streamlit` package is not installed in this environment. No browser success is claimed.
- User-supplied separate rainfall CSV: compared with the bundled CSV; both are 4,018 × 2 and their parsed values are identical.
- Full numerical outputs are in `results/simulation_summary.json`; concise results are in `SIMULATION_RESULTS.md`.
