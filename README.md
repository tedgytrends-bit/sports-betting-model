# Sports Model — NFL Projections

A Streamlit dashboard and experimental NFL score-projection project. The goal is to build a transparent, repeatable data pipeline and evaluate projections on games not used to fit the model.

**Current code version:** v0.6.3

## Important status

This is not a validated betting model. Historical backtests are exploratory and do not establish a repeatable betting edge. Do not use backtest results as a guarantee of future performance or proof of profitability.

The public upcoming-game projection board currently uses a simple recent-scoring baseline. The historical efficiency model is evaluated separately.

## What is included

- app.py: Streamlit dashboard for projections, model comparison, data-quality checks, and historical backtesting.
- model.py: Data loading, feature engineering, projections, and chronological evaluation.
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
