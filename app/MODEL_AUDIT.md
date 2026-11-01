# Production model technical audit

## Scope and model identity

The Streamlit app has eight tabs and retains its existing project/activity workflow, charts and result sections. `rainfall_model.py` is the production path used by the main simulation and scenario runs. `engine.py` contains the historical PERT engine for compatibility/regression testing; it is not the production rainfall simulation.

## Production data and stochastic workflow

1. Validate a daily CSV with exactly `date,rainfall_mm`, nonnegative finite rainfall, unique dates, contiguous daily coverage and complete calendar years.
2. Select the currently active source: bundled processed rainfall CSV or a validated uploaded replacement. Rainfall diagnostics are calculated from this selected dataframe and include its source label.
3. For each replicate, PCG64 samples a starting historical year. Actual observed daily values are replayed by month/day; later simulated project years use subsequent historical years with wraparound. Feb 29 maps to Feb 28 when the selected historical year is non-leap.
4. Each activity has assumed sensitivity `min(1, delay_M / (0.35 * duration))`.
5. On each active calendar day, assumed stop probability is `min(1, rainfall_mm / 64.5 * sensitivity * scenario_multiplier)`. A Bernoulli draw produces zero or one lost day. Lost days extend the activity finish and successors dynamically inherit the delayed predecessor finish.
6. CPM completion is the maximum simulated terminal finish. Additional delay is simulated completion less baseline CPM completion.
7. Activity additional cost equals lost activity days times `cost_M / delay_M` when `delay_M > 0`; project-level additional cost equals project additional delay times the configured daily rate.
8. P50/P80/P90 are empirical quantiles across the simulated replicates.

Production durations are enforced as positive whole calendar days. This removes the previous inconsistency in which baseline CPM retained fractional durations but daily rainfall simulation rounded them upward.

## Historical calibration versus construction assumptions

**Empirical rainfall component:** daily rainfall observations are resampled in historical year blocks. This retains observed rainfall values, seasonal structure and within-year wet/dry sequences. PCG64 controls random selection and Bernoulli draws. Fixed seed and identical inputs give reproducible outputs within the same implementation/environment.

**Assumed construction component:** the 64.5 mm/day scaling reference, 0.35 sensitivity constant, delay_M-to-sensitivity mapping, Bernoulli stoppage response, cost_M marginal-cost mapping and absence of explicit recovery/catch-up dynamics are assumptions. There is no labelled construction-delay dataset and no supervised model has been trained. These relationships are not empirically calibrated against project outcomes.

## Scenario method

When the user invokes the Rainfall-tab derivation action, mild and severe multipliers use the historical June–September seasonal-total 20th and 90th percentiles divided by the median seasonal total. The resulting scalar multiplies daily stop probability. This is not equivalent to selecting and replaying the actual historical 20th/90th percentile rainfall year and does not preserve that percentile year's daily event sequence. If the user has not derived/applied multipliers, interface defaults are 0.60, 1.00 and 1.50 for mild, typical and severe. The scalar-scaling methodology is retained; no unannounced scenario-method change has been made.

## Legacy controls

`rho` and the legacy/precise sampler are not read by the production rainfall model. Delay O/P and cost O/P remain legacy/reference fields; production activity sensitivity uses delay_M and activity marginal cost uses cost_M. The UI labels these as non-operative for production. The legacy PERT engine is protected by its own regression tests but its validation is not evidence for rainfall disruption validity.

## Data provenance and limits

The supplied processed CSV can be checked for schema, completeness, dates and numeric validity. Original IMD binary-grid provenance, grid-cell extraction and unit conversion have not been independently authenticated from the processed CSV alone. Historical rainfall bootstrap is not a weather forecast. Simulated percentiles describe the output distribution conditional on the historical sample and stated assumptions; they are not validated predictive accuracy or confidence bounds. Site-specific stoppage probabilities and costs require observed construction records for calibration.
