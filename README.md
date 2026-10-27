# Sports Model — NFL Projections

A Streamlit dashboard and experimental NFL score-projection project. The goal is to build a transparent, repeatable data pipeline and evaluate projections on games not used to fit the model.

**Current code version:** v0.8.0

## Important status

This is not a validated betting model. Historical backtests are exploratory and do not establish a repeatable betting edge. Do not use backtest results as a guarantee of future performance or proof of profitability.

The public projection board includes the experimental play-by-play efficiency model with fallback behavior where required. The efficiency model's prospective forecasts are captured separately by a daily GitHub Actions workflow and graded on the Prospective Results Audit page.

## What is included

- app.py: Streamlit dashboard for projections, model comparison, data-quality checks, and historical backtesting.
- model.py: Data loading, feature engineering, projections, and chronological evaluation.
- scripts/capture_efficiency_projections.py: Daily frozen upcoming-game forecasts from the play-by-play efficiency model.
- scripts/capture_sportsbook_odds.py: Optional bookmaker-specific spreads/totals capture from The Odds API v4.
- .github/workflows/capture-sportsbook-odds.yml: Six-hour odds capture workflow; safely skips when no API key is configured.
- research/prospective_results_audit.py: Separate grading for baseline snapshots and efficiency-model forecasts.
- .github/workflows/capture-prospective-efficiency-projections.yml: Daily scheduled capture of efficiency projections.
- requirements.txt: Python dependencies.

## Version 0.6.3 — Reproducible backtest exports

This version adds provenance fields to the downloadable historical totals CSV and a separate JSON run manifest. Each run records:

- Model version, UTC timestamp, and run ID.
- Requested and loaded play-by-play seasons.
- Model lookback and minimum training-game requirement.
- Feature columns and row counts at key processing stages.
- A SHA-256 fingerprint of the exported game-ID sequence.

The manifest helps explain differences between dataset, prediction, comparison, and totals-export row counts.

## Important limitations

- The public projection baseline does not automatically account for injuries, weather, rest, or live sportsbook odds.
- Manual injury and weather adjustments are exploratory, not validated predictive values.
- Historical market lines may not match the exact sportsbook line and price available when a bet could have been placed.
- Historical thresholds selected after reviewing results are subject to selection bias.
- Better score predictions do not automatically imply profitable betting.

## Data integrity rules

- Use only information available before kickoff.
- Fit preprocessing using training data only.
- Preserve timestamped predictions and the market line and odds available at publication.
- Track no-bet games and report pushes separately.
- Keep historical backtests separate from prospective results.
- Verify feature availability and plausible value ranges before interpreting metrics.

## Recommended next steps

1. Verify the data pipeline and feature audit, especially red-zone and turnover calculations.
2. Compare models on identical chronological test games.
3. Add injury data only when historical, point-in-time availability can be established.
4. Test changes one at a time on out-of-sample data.
5. Freeze prospective predictions, timestamps, lines, and odds before kickoff.
6. Do not claim profitability without adequate out-of-sample and prospective evidence.


## Version 0.8.0 — Prospective efficiency-model tracking

- Adds a daily workflow to generate timestamped play-by-play efficiency-model projections for upcoming games.
- Saves forecasts and available schedule-feed lines as immutable CSV snapshots under `data/prospective_ats_tracking/`.
- Grades the earliest clearly pre-scheduled-date forecast separately for ATS and totals, with W-L-P, assumed -110 units/ROI, and cumulative edge thresholds.
- Keeps the simple recent-scoring baseline archive separate from the efficiency-model archive.

Prospective results remain experimental. Public schedule-feed lines are not verified executable sportsbook prices, and captures on the scheduled UTC date are excluded from primary results because exact kickoff timing is unavailable. Do not infer a betting edge from projections alone.

## Optional sportsbook odds capture

The repository now includes an optional collector for The Odds API v4. To enable it, add an API key as a GitHub Actions repository secret named `ODDS_API_KEY` (Repository → Settings → Secrets and variables → Actions → New repository secret). The `Capture sportsbook odds snapshots` workflow runs every six hours and can also be started manually. Without the secret, the workflow skips capture without failing. It stores one row per event, bookmaker, market, and outcome, including American odds prices, the bookmaker/market update timestamp when supplied, and the local capture timestamp. These third-party feed snapshots still do not guarantee account-specific availability or successful execution.

The collector requests US-region `spreads,totals` only. Check the provider's current plan, NFL access, historical-data entitlement, and quota before purchasing or enabling it; provider plan details can change. The collector does not require the API key to be committed to the repository.

