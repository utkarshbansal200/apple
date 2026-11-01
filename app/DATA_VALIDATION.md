# Rainfall data validation

**Input:** `data/Mumbai_IMD_Rainfall_2015_2025_19N_72.75E.csv` (verbatim copy of supplied file; SHA-256 available via operating system).

The file contains exactly two columns, `date` (YYYY-MM-DD) and `rainfall_mm` (mm/day inferred from column naming, not independently authenticated). The CSV has **4,018 daily records**, inclusive 2015-01-01 to 2025-12-31, including February 29 in 2016, 2020 and 2024. Checks executed: timestamp parsing, numeric parsing, negative/nonfinite/sentinel detection, exact daily continuity, duplicate timestamps, complete calendar years, annual totals, seasonal totals, heavy rain counts. **0 null dates**, **0 null rainfall values**, **0 duplicates**, **0 negative entries**, **0 missing calendar days**. Maximum single-day reading **273.4122 mm**. No rainfall records were altered, dropped or synthesized. For complete annual and monthly statistics see `results/rainfall_diagnostics.json`.

Annual totals (mm):

| Year | mm |
|--|--:|
|2015|1756.8084|
|2016|2774.8988|
|2017|2807.1008|
|2018|2087.3397|
|2019|3333.0569|
|2020|3563.2597|
|2021|3072.1529|
|2022|2552.5139|
|2023|2740.4905|
|2024|2968.5199|
|2025|3182.7549|

**Provenance caveat:** A CSV filename alone cannot establish that the values were extracted correctly from the official IMD gridded daily rainfall binary product or that 19.0°N,72.75°E is the correct grid cell centre and exact local resolution. Raw IMD binaries, source URL, checksum, and extraction script were not provided. No independent raw-file cross-check was possible. Acceptance is **conditional on the user's identification of this dataset as IMD**, not confirmation of an authoritative source. If full source authentication is mandatory, withhold scientific use until the original source file is verified.

The uploaded `MonteCarlo_Input_Dataset (1).xlsx`, `Validation_Comparison (1).xlsx` and `validation_report.pdf` do **not** provide independent historical daily rain observations; they document construction assumptions and legacy simulation validation. They were not included in rainfall fitting.

**Preprocessing:** Strict reading and validation; sort by date; no interpolation or normalization; use complete historical years, empirical year resampling. For calendar alignment only, a synthetic future leap date Feb 29 is mapped to Feb 28 when the selected historical year is non-leap. Source file is unchanged.
