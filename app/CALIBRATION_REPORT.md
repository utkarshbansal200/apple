# Calibration and assumptions report

## Rainfall calibration

The production rainfall input is the empirical distribution of supplied historical daily observations arranged in complete calendar-year blocks. Each replicate samples a historical starting year using NumPy PCG64 and replays observed daily rainfall in calendar alignment. No Gaussian, gamma, beta or neural rainfall generator is fitted. The current bundled record covers 2015-01-01 through 2025-12-31 (4,018 daily observations), subject to the provenance limitation below. A validated custom full-calendar-year CSV replaces the bundled record for production runs.

## Construction disruption assumptions — not trained

No supervised construction-delay model has been trained, and no labelled site-level construction-delay dataset was supplied. Rainfall-conditioned Bernoulli stoppage probabilities are imposed assumptions: reference intensity 64.5 mm/day; activity sensitivity `min(1, delay_M / (0.35 * duration))`; daily stop probability `min(1, rainfall_mm / 64.5 * sensitivity * scenario_multiplier)`. `delay_M` is an input used to derive activity sensitivity, not a target learned from construction observations. `cost_M / delay_M` (when delay_M is positive) is used as the assumed marginal activity cost per lost day. Project delay cost is the configured daily project rate times simulated completion delay.

These relationships are not estimated from the rainfall record. The rainfall data calibrates the weather resampling component only; it does not calibrate the construction response function.

## Mild and severe scenarios

When the user chooses to derive scenario values in the Rainfall tab, the 20th and 90th percentiles of historical June–September seasonal totals are divided by the median seasonal total. Those ratios scale daily stoppage probabilities. They are severity multipliers, not simulations of actual 20th- and 90th-percentile rainfall years. If not derived and applied, the interface defaults are 0.60, 1.00 and 1.50. The approach is retained to preserve comparability with the current application.

## Interpretation

P50/P80/P90 are Monte Carlo percentiles of simulated additional delay and cost under the chosen rainfall history, project schedule and assumed construction response. They do not represent validated predictive accuracy, confidence intervals for real-world performance, or weather forecast skill. Calibration of construction disruption requires labelled site histories (rainfall, activity, stoppage and recovery outcomes) that are not currently available.

## Provenance limitation

The processed CSV's internal structure can be validated, but original IMD source provenance, 0.25-degree grid extraction and unit conversion have not been independently authenticated from the processed CSV alone.
