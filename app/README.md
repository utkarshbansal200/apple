# Mumbai Monsoon Risk Calculator — Streamlit

Monte Carlo decision-support tool for construction schedule and cost contingency under historical Mumbai rainfall sequences. The existing eight-tab Streamlit interface, activity workflow, charts and output tables are retained.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Run tests and reproduce the benchmark:

```bash
python -m pytest -q
python -m py_compile app.py engine.py rainfall_model.py run_benchmark.py
python run_benchmark.py
```

## Production methodology

`rainfall_model.py` is the production simulation. Each replicate samples a historical calendar-year start from the selected complete daily rainfall record using NumPy's PCG64 generator. It replays observed daily rainfall values in calendar alignment; subsequent project years move through the historical year sequence with wraparound. Historical rainfall is empirically resampled, not fitted to a parametric rainfall distribution.

For activity `i`, assumed sensitivity is `min(1, delay_M / (0.35 * duration))`. On each active day, assumed stoppage probability is `min(1, rainfall_mm / 64.5 * sensitivity * scenario_multiplier)`. A Bernoulli draw determines a lost day. Successor starts are propagated from simulated predecessor finishes and project completion is calculated through the activity network. Production durations must be positive whole calendar days, matching the daily rainfall time step.

`delay_M` determines activity sensitivity. `cost_M` determines marginal activity cost per lost day (`cost_M / delay_M` where delay_M is positive). Project-level additional cost is simulated project delay times the configured daily project cost rate. P50/P80/P90 are percentiles of the simulated outcome distribution.

## Data and assumptions

The default dataset is a processed daily CSV covering 2015–2025. A custom upload replaces it for production after strict validation. Upload exactly `date,rainfall_mm` with ISO dates and every date in complete calendar years; June–September-only data is rejected. The app reports the active source, observation count, coverage, annual totals, monthly distribution, missing observations and validation status.

Rainfall observations are historical inputs. No supervised construction-delay model has been trained. The rainfall-conditioned stoppage equation, sensitivity scaling, 64.5 mm/day reference threshold, 0.35 sensitivity constant, activity marginal costs and recovery assumptions are not estimated from construction outcome labels. Percentiles describe simulated outcomes under these assumptions, not validated predictive accuracy.

Mild/severe multipliers can be derived in the Rainfall tab from the selected record: historical June–September seasonal-total 20th and 90th percentiles divided by the median, then applied as scalar multipliers to daily stoppage probabilities. They are not direct replays of actual percentile rainfall years. Until the user derives and applies them, the interface defaults are 0.60 (mild), 1.00 (typical) and 1.50 (severe). The existing scalar-scaling method is retained.

Original IMD source provenance, grid extraction and unit conversion have not been independently authenticated from the processed CSV alone. The processed file's structure and values can be validated, but its original source chain cannot be proven from the CSV itself.

## Interface compatibility

The original `engine.py` PERT implementation remains for legacy regression tests only. Correlation rho, legacy/precise sampler choice, and O/P delay/cost inputs do not affect the production rainfall simulation. They are retained for interface/history compatibility and are labelled accordingly. `delay_M` and `cost_M` are the active production activity inputs.


## Update: three-point (PERT) cross-check and web version
- Validation tab now has a **Three-point (PERT) hand cross-check** (course brief, Topic 5): hand PERT means (O+4M+P)/6 versus the O/M/P simulation engine, per activity and for the project. It checks the three-point engine only; the production result is the rainfall-driven model.
- `test_pert_crosscheck.py` adds 2 tests (39 total).
- `web/monsoon_risk_calculator.html` is a no-install browser version of the production model (open it in any browser). It uses a different random generator from NumPy, so results agree statistically, not digit for digit.
