# Week 9 aftermath — historical margin-calibration diagnosis (2026-11-10)

**Status:** Research diagnostic completed; feature-scaling experiment separately running. No published picks, frozen forecasts, official results, live coefficients, or totals were changed.

## What has actually completed

- The final 15-game Week 9 official injury model research audit was saved as `data/week09_review/week09_full_findings.md`: ATS **3–11–1**, totals **9–6**.
- The historical archived four-model evaluation and prior margin-scaling holdout already existed. The prior experiment did **not** support multiplying all margins by a constant.
- A new historical stratification of the archived `data/four_model_historical/four_model_all_game_predictions_20261105T200307Z.csv` was evaluated on **1,021 common completed games** (2022 Week 16–2026 Week 8). All reported ATS records below are **schedule-feed simulations**, not verified executable Bovada quotes.
- The latest 1,036-game player-injury chronological rerun did not beat the same-game Baseline's margin MAE: **10.425 vs 10.413**. At 3.5+ point ATS thresholds, the injury shadow improved price-based ROI from **−5.43% to −4.13%**, but neither qualified as a successful replacement. It should remain experimental.

## A structural correction to the original hypothesis

`model.py` currently fits `Ridge(alpha=10)` to home score and away score on **identical feature matrices** within each weekly fold. Subtracting those two predictions is algebraically the same as fitting `Ridge(alpha=10)` to `home_score-away_score` with that same feature matrix (up to floating-point error). Therefore merely switching to a direct-margin Ridge target with unchanged features and alpha **cannot** repair margin compression.

What needs testing instead is the **feature representation and regularization**. The current score pipeline imputes numeric features and fits an **unstandardized** Ridge model. EPA, success rate, turnover rate, rest days, and other variables can have quite different scales. Fixed Ridge penalization on unstandardized features is not scale-invariant. This is a plausible mechanism, not yet an experimentally proven cause.

## Archived Baseline findings

| Statistic | Baseline |
|---|---:|
| Historical games scored | 1,021 |
| Mean absolute predicted margin | 2.99 points |
| Mean absolute archived market spread | 5.06 points |
| Mean absolute realized margin (noisy outcomes) | 11.14 points |
| Baseline margin MAE | 10.40 points |
| Archived market margin MAE | 9.77 points |
| All directional ATS | 495–499–27 |
| Underdog ATS selections | 408–416–20 |
| Favorite ATS selections | 87–83–7 |
| Edges of 5+ ATS points | 116–119–6 |

Baseline chose **844/1,021 (82.7%)** against the sportsbook favorite. This does **not** mean the model picked the underdog to win outright in 82.7% of games. Against the market's winner, the Baseline predicted the opposite outright winner in **264/1,021 (25.9%)** games.

For archived market spreads of **7+ points** (263 games), the model's mean absolute projected margin was **4.46** versus a mean market magnitude of **9.59**. It still predicted the market-favored team to win outright in 246/263 games. The compression and underdog ATS skew often arise *without* an outright underdog prediction.

**Important:** The realized margin's mean absolute value of 11.14 should **not** be the calibration target. Final scores contain noise; taking their absolute values inflates their expectation even for an unbiased conditional-mean forecast. Compare out-of-sample MAE/RMSE and conditional error by market size and year, not only average absolute magnitude.

### ATS by predicted edge bucket

| Absolute baseline edge | W–L–P | Win rate excluding pushes |
|---|---:|---:|
| <1 point | 82–93–8 | 46.9% |
| 1 to <2.5 | 116–125–7 | 48.1% |
| 2.5 to <3.5 | 85–69–0 | 55.2% |
| 3.5 to <5 | 96–93–6 | 50.8% |
| 5+ | 116–119–6 | 49.4% |

Edge size is **not** monotonically predictive of winning. Do not choose a threshold by ranking these explored bins after the fact.

## Next controlled experiment — fixed before seeing results

Implemented in `scripts/run_margin_feature_scale_shadow.py`, via `.github/workflows/standardized-margin-shadow.yml`:

1. Rebuild the unchanged pregame efficiency features from public nflverse schedule/PBP and the existing `model.py` pipeline, with all 2026 results after Week 8 excluded from evaluation.
2. For identical weekly walk-forward folds, evaluate the current two-score **unscaled Ridge(alpha=10)**, direct-margin **unscaled Ridge(alpha=10)** (must reproduce same predictions), and direct-margin **StandardScaler + Ridge(alpha=10)**. Fit imputation and scaling only on prior training data.
3. Compare with the recorded historical spread as a **benchmark only**, never as a model feature.
4. Report 2023/24 development and separately 2025 and 2026 Weeks 1–8, using margin MAE/RMSE, favorite-size strata, raw directional ATS and fixed 3.5/5 point edge bins.
5. Reject any promotion without stable improvements across years and a *new prospective validation* period. Because these years have already been reviewed in prior experiments, this study is **exploratory**, not independent proof of value.

The workflow accesses only **public nflverse data**; no NFLMeta or EndzoneAPI credits are used.

## Continuing priorities after experiment

- Validate the QB overlay using verified starters and observed replacements; the Week 9 QB adjustment reversed two ATS winners to losers, but two examples are insufficient to establish a defective mechanism.
- Audit the strongest spread mismatches for feed/starter/line-vintage errors **before** changing coefficients.
- Keep totals separate: Week 9 totals ATS-style grading success does not by itself prove durable point-estimate advantage.

**Public-record guardrail:** The official prospective record begins with 2026 Week 8. No historical or Week 9 grades are to be reclassified because a retrospective shadow candidate fits better.
