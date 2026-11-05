# Opponent-adjusted efficiency: v3 research experiment

This adds a third, **experimental** feature family to Tedgy Trends CBB:
chronological schedule-strength-adjusted team offense, defense, pace and net rating.
The model is NOT automatically promoted to the 2026–27 prospective shadow record.

## Feature construction

At the beginning of **each calendar date**, fit each team's adjusted offensive
and defensive efficiencies using prior days' final scores and team possessions.
Shrink each rating toward league-average efficiency (100 points/100 possessions)
with six virtual neutral games. Iteratively remove opponents' known offensive and
defensive strengths from prior observations; adjust pace for known opponent
tempo; record each team's prior-opponent net-strength. Apply current-day
results **only after** ALL of that date's scheduled games have received
their frozen pregame features. Reset completely at each season boundary.

Every calculated feature is derived only from game results observable before
that date; never reuse season-end adjusted rankings on earlier games.

## Comparison

All four models are evaluated on identical games and available historical
market lines, with models fitted only on seasons strictly **before** the test
season (2024, 2025, 2026).

1. Original team-only baseline
2. Team baseline + chronological opponent adjustments
3. Existing corrected player-v2 baseline
4. Corrected player-v2 + chronological opponent adjustments

Separate spread and total regressions. Report error in predicted home margin,
total, and independent ATS/total direction win-loss-push and hypothetical
-110 ROI at edges 0 / 2.5 / 3.5 / 4.5 / 5.5. The 0 threshold is ALL
directional leans, not a bet filter. Missing/zero market edges are excluded.

Compare 2024/2025 development seasons with 2026 without tuning the model
on 2026 ROI. The historical roster and odds point-in-time limitations still
apply. Do not claim profitable market performance based on these backtests.

Workflow: **CBB Opponent-Adjusted V3 Comparison**
