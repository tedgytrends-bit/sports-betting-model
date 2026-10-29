# Sports Model — NFL Projections

A Streamlit dashboard and experimental NFL score-projection project. The goal is to build a transparent, repeatable data pipeline and evaluate projections on games not used to fit the model.

**Current code version:** v0.8.0

## Important status

This is not a validated betting model. Historical backtests are exploratory and do not establish a repeatable betting edge. Do not use backtest results as a guarantee of future performance or proof of profitability.

The public projection board includes the experimental play-by-play efficiency model with fallback behavior where required. Its prospective forecasts are captured separately by a daily GitHub Actions workflow and graded on the Prospective Results Audit page. Optional bookmaker-specific odds snapshots are a separate data stream.

## What is included

- `app.py`: Streamlit dashboard for projections, model comparison, data-quality checks, and historical backtesting.
- `model.py`: Data loading, feature engineering, projections, and chronological evaluation.
- `scripts/capture_efficiency_projections.py`: Daily frozen upcoming-game forecasts from the play-by-play efficiency model.
- `.github/workflows/capture-prospective-efficiency-projections.yml`: Scheduled capture of efficiency projections.
- `scripts/capture_sportsbook_odds.py`: Manual, single-game EndzoneAPI bookmaker-odds capture.
- `.github/workflows/capture-sportsbook-odds.yml`: Manually triggered odds capture; this is not continuous six-hour polling.
- `scripts/estimate_endzone_odds_cost.py` and `.github/workflows/estimate-endzone-odds-cost.yml`: Estimate provider costs using `estimate_only=True`; this workflow should not consume query credits.
- `research/prospective_results_audit.py`: Separate grading for baseline snapshots and efficiency-model forecasts, plus the EndzoneAPI actual-price research audit.
- `requirements.txt`: Python dependencies.

## Reproducible backtest exports

The historical totals export includes provenance fields and a separate JSON run manifest. Each run records:

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
- Public schedule-feed lines are not verified executable sportsbook prices.
- The injury feed is not a complete historical archive of every report revision, so injury features are not yet validated as point-in-time historical inputs.

## Data integrity rules

- Use only information available before kickoff.
- Fit preprocessing using training data only.
- Preserve timestamped predictions and the market line and odds available at publication.
- Track no-bet games and report pushes separately.
- Keep historical backtests separate from prospective results.
- Verify feature availability and plausible value ranges before interpreting metrics.
- Keep opening/closing/latest sportsbook snapshots distinguishable and do not count multiple captures of the same game/book as separate bets.
- Treat prospective actual-price records as hypothetical model evaluations, not evidence of a durable edge.

## Recommended next steps

1. Continue point-in-time prospective collection with frozen projections and timestamped sportsbook quotes.
2. Grade completed games only after final scores are available, then inspect unmatched scores and missing prices.
3. Compare models on identical chronological test games.
4. Audit red-zone and turnover feature calculations before relying on them.
5. Add injury data to predictive features only when historical, point-in-time availability can be established.
6. Test changes one at a time on out-of-sample data; do not tune thresholds to maximize the historical record.
7. Do not claim profitability without adequate out-of-sample and prospective evidence.

## Version 0.8.0 — Prospective efficiency-model tracking

- Adds a daily workflow to generate timestamped play-by-play efficiency-model projections for upcoming games.
- Saves forecasts and available schedule-feed lines as immutable CSV snapshots under `data/prospective_ats_tracking/`.
- Grades the earliest clearly pre-scheduled-date forecast separately for ATS and totals, with W-L-P, assumed -110 units/ROI, and cumulative edge thresholds.
- Keeps the simple recent-scoring baseline archive separate from the efficiency-model archive.

Captures on the scheduled UTC date are excluded from the primary schedule-feed record because exact kickoff timing is unavailable. This is a conservative timing rule, not proof that all earlier captures had executable prices. Do not infer a betting edge from projections alone.

## Optional EndzoneAPI sportsbook odds capture

- `.github/workflows/capture-sportsbook-odds.yml` supports manual, single-game EndzoneAPI captures.
- Use the existing repository Actions secret named `ENDZONE_API_KEY`; never commit the key or paste it into chat.
- Run the workflow only for a game whose odds you specifically want to preserve. The request may consume provider credits; it is not scheduled polling or a season-wide capture.
- Captures preserve bookmaker, opening/closing/latest values, provider snapshot timestamps, and local capture timestamps.
- The prospective audit matches a frozen model projection captured no later than the provider odds timestamp, checks the provider timestamp against kickoff and capture time, and grades only eligible latest snapshots at the recorded American price.
- The cost-estimate workflow uses `estimate_only=True` and should not consume query credits. It exits with an error if the required secret is unavailable.
- This project uses EndzoneAPI for the optional odds capture workflow; do not confuse it with The Odds API.
