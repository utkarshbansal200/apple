# Benchmark simulation results

**Benchmark setup:** 12-activity sample project; planned start 2027-02-01; baseline CPM duration 402 calendar days; baseline activity cost ₹858 lakh; 10,000 Monte Carlo draws per scenario; PCG64; seed 42. Scenario multipliers: mild 0.60, typical 1.00, severe 1.50. The benchmark uses the bundled 2015–2025 processed daily rainfall series.

| Scenario | Mean additional delay (days) | P50 delay | P80 delay | P90 delay | Mean additional cost (₹ lakh) | P50 cost | P80 cost | P90 cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mild | 14.05 | 14 | 17 | 19 | 18.84 | 18.77 | 22.90 | 25.39 |
| Typical | 22.37 | 23 | 26 | 28 | 29.93 | 30.67 | 35.14 | 37.62 |
| Severe | 30.71 | 32 | 36 | 38 | 41.01 | 42.55 | 47.87 | 50.52 |

These are conditional simulated outcomes under the selected historical rainfall record and assumed stoppage/cost relationships. They are not observed project outcomes, validated forecasts or evidence of predictive accuracy.

Detailed files:

- `results/simulation_summary.json` — complete scenario statistics and per-activity mean contributions.
- `results/typical_10000_draws.csv` — 10,000 typical-scenario draw-level delay, cost and sampled historical start year.
- `results/activity_contributions.csv` — activity-level average lost days, additional cost and rainfall exposure.
- `results/rainfall_diagnostics.json` — active benchmark rainfall dataset diagnostics.
