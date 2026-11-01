# Testing and execution report

## Executed checks

| Check | Result |
|---|---|
| Full pytest suite | **39 passed** (37 original + 2 PERT cross-check tests in test_pert_crosscheck.py) |
| Python compilation (`app.py`, `engine.py`, `rainfall_model.py`, `run_benchmark.py`) | **Passed** |
| Full three-scenario benchmark (`run_benchmark.py`, 10,000 draws per scenario) | **Completed** |
| Streamlit launch | Headless load via streamlit.testing AppTest: all 8 tabs rendered, no exceptions. Real browser launch still to be confirmed by the team on its own machine. |

The suite retains the original 25 passing tests and adds 12 tests. New coverage includes integer-duration zero-rainage consistency, fractional-duration rejection, selected custom rainfall diagnostics and source label, rejection of June–September-only data, legacy-control irrelevance, successor schedule shifting and repeatability using the sample project benchmark inputs.

## Important interpretation

Passing tests establish code behaviour for the tested cases, not the scientific validity of the rainfall-to-construction-disruption assumptions. No supervised construction-delay model has been trained. Monte Carlo percentiles are simulated outcome percentiles, not validated predictive accuracy. Original IMD source provenance has not been independently authenticated from the processed CSV alone.

## Benchmark execution

The benchmark ran with 10,000 iterations per scenario, seed 42, planned start 2027-02-01 and baseline CPM duration 402 days. Scenario multipliers were 0.60 / 1.00 / 1.50. Full statistics are in `results/simulation_summary.json`; typical draw-level results are in `results/typical_10000_draws.csv`; activity summaries are in `results/activity_contributions.csv`; rainfall diagnostics are in `results/rainfall_diagnostics.json`.

The user-supplied separate CSV was compared with the bundled rainfall CSV: both contain 4,018 rows, the same two columns, and identical parsed values. The bundled file remains the default source. The Streamlit upload workflow now stores the uploaded dataset and source name in session state so that the custom dataset becomes the production source and diagnostics follow that selected dataset.
