# Historical ATS follow-up — November 17, 2026

Source: `research/reports/automated_score_model_predictions.csv`, all 1,050 rows. Computed independently from its `predicted_home_margin`, `spread_line`, `actual_home_margin`, and `actual_ats_cover_margin`. These are **Efficiency score model** backtests, NOT a historical test of the current player-aware Injury model. The source notes historical sportsbook quote timestamps are unverified. Historical seasons are not strictly a fresh untouched holdout for tuning.

## Market anchoring (mean absolute margin error, points)

| Season | N | Market (alpha=0) | 25% model | 50% model | Raw model |
|---|---:|---:|---:|---:|---:|
| 2022 partial | 45 | 9.92 | 9.84 | 9.80 | 10.32 |
| 2023 | 285 | 9.98 | 10.04 | 10.17 | 10.55 |
| 2024 | 285 | 9.70 | 9.79 | 10.00 | 10.58 |
| 2025 | 285 | 9.67 | 9.72 | 9.87 | 10.40 |
| 2026 through W10 | 150 | 9.57 | 9.66 | 9.78 | 10.17 |
| ALL | 1050 | 9.76 | 9.82 | 9.97 | 10.45 |

## ATS threshold sensitivity (flat -110 theoretical ROI)

| Season | All games | Edge >= 3.5 | Edge >= 5 |
|---|---|---|---|
| 2022 partial | 23-20-2 (+2.0%) | 13-7-2 (+21.9%) | 8-6-2 (+8.0%) |
| 2023 | 133-138-14 (-6.0%) | 54-55-6 (-5.1%) | 30-30-4 (-4.3%) |
| 2024 | 133-148-4 (-9.5%) | 60-66-2 (-8.9%) | 31-31 (-4.5%) |
| 2025 | 146-138-1 (-1.9%) | 62-65 (-6.8%) | 36-40 (-9.6%) |
| 2026 through W10 | 68-76-6 (-9.5%) | 25-28-2 (-9.6%) | 12-20 (-28.4%) |
| ALL | 503-520-27 (-6.0%) | 214-221-12 (-5.9%) | 117-127-6 (-8.3%) |

## Decision
- No evidence that increasing ATS edge thresholds fixes the historical Efficiency score model. Its raw margin estimates underperform market in 4 of 5 year cohorts and overall; 2022 is only 45 games.
- Market blending improves **margin MAE**, not ATS pick direction for any strictly positive fixed alpha.
- Prospective Injury ATS underdog 9-20-1 and edge >=5 2-7 deserve deeper causal investigation, but cannot be explained from the historical Efficiency dataset alone.
- Next test must compare identical games and timestamps for the current Injury model with and without QB/player injury features, and a market-relative conditional adjustment. Preserve existing published Week 8-10 grades.
- Totals model unchanged.

No production changes or claims of validated profitable model improvements.
