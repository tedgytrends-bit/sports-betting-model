# NFL prospective ATS audit — November 17, 2026

Research-only. No official predictions, frozen forecasts, historical outcomes or website records changed.

## Inputs and controls
- Source: `data/public_results/nfl_2026_graded_games.csv`, 43 FINAL published Injury rows, Weeks 8–10.
- Frozen market: `home_favored_spread`, with positive number meaning home favored.
- Independent directional grade: sign(projected home margin - market home margin) versus sign(actual home margin - market home margin).
- Flat -110 theoretical ROI; not actual betting ROI.
- Reproduction: `python research/audit_nfl_ats_prospective.py`.

## Verified findings
- Overall: 16–26–1 ATS, −26.6% theoretical ROI.
- Underdog selections: 9–20–1 (30 games); favorite selections: 7–6 (13 games).
- Absolute projected ATS edge buckets:
  - [0,1.5): 5–5, 10 games, −4.5% ROI.
  - [1.5,3): 4–8, 12 games, −36.4% ROI.
  - [3,5): 5–6–1, 12 games, −12.1% ROI.
  - [5,infinity): 2–7, 9 games, −57.6% ROI.
- Mean absolute home-margin error under market anchoring (market + alpha × [model-market]):
  - alpha 0 (market): 9.97 points
  - alpha .25: 10.24
  - alpha .50: 10.54
  - alpha .75: 10.89
  - alpha 1 (unadjusted model): 11.34

## Interpretation and next gates
1. Model is disproportionately choosing underdogs and its larger edge calls have been unreliable. This is a **hypothesis**, not causal proof of an underdog bias.
2. Positive uniform shrinkage toward market changes projected margin and MAE, **but not pick direction**. It cannot by itself fix ATS win rate. Evaluate shrinkage only as a calibration/threshold intervention, not a claimed ATS directional improvement.
3. To improve directions, test conditional market blending with independently estimated adjustments, QB reliability uncertainty and home/away/team-strength feature ablations; do not train these on Weeks 8–10 and report those same games as out-of-sample.
4. Run season-forward historical training and evaluation (e.g. train through 2023, validate 2024, test 2025; then freeze before examining 2026). Compare ATS direction, MAE, Brier/calibration if probabilities are available, and bucketed ROI on identical available games and archived pregame market quotes.
5. No replacement or public promotion until a candidate beats the existing Injury model on held-out data and survives data-source, kickoff timestamp, player role, and injury availability checks.
6. Keep totals unchanged pending a separate stability audit. Original prospective totals and retrospectively derived tiebreaker remain separately labeled.

**Status:** Preliminary diagnostics computed directly from GitHub CSV; research script committed but not yet run by GitHub Actions. No production deployment requested or performed.
