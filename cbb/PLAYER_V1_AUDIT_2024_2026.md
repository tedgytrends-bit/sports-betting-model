# CBB player-adjusted v1: historical result audit

**Executed:** 2026-11-05. GitHub Actions [CBB Player V1 Historical Comparison, run 42109237461](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42109237461). Detailed eight-file artifact: cbb-player-v1-comparison, artifact 13453331076. All unit tests, ingestion, feature generation and backtest steps passed.

## Implementation

Player-v1 extends team-only CBB Ridge spread/total models with roster-level priors based on **previous-season** individual minutes, offensive/defensive efficiency, usage, points and PORPAG; retaining/transfer production; freshman recruiting stars; verified portal matches; and player coverage. Roster membership filter restricts to players with known startSeason <= season-1 and endSeason >= season. Priors fade with current-season games.

Historical rosters are *retrospective*, not timestamped preseason availability reports. These results **are not a true point-in-time verified player backtest**, and cannot establish live profitability. Market odds use a hypothetical uniform -110 and are mixed-source.

## Model average absolute error (all completed games)

| Season | ATS baseline | ATS player-v1 | ATS error reduction | Total baseline | Total player-v1 |
|---|---:|---:|---:|---:|---:|
| 2024 (2023–24) | 10.813 | 10.165 | 5.99% | 13.864 | 13.651 |
| 2025 (2024–25) | 11.031 | 10.209 | 7.45% | 13.535 | 13.385 |
| 2026 (2025–26) | 11.157 | 10.919 | 2.13% | 14.420 | 14.405 |

Market ATS errors remain lower: 8.873, 8.756, and 9.027 on the line-covered subset. Thus the model does not match the market in raw point projection accuracy.

## Hypothetical ATS ROI (3.5 point edge; -110)

| Season | Baseline W-L-P / ROI | Player-v1 W-L-P / ROI |
|---|---|---|
| 2024 | 1,377–1,371–0 / -4.34% | 1,116–1,101–0 / -3.90% |
| 2025 | 1,461–1,450–0 / -4.18% | 1,253–1,247–0 / -4.32% |
| 2026 | 1,571–1,468–58 / -1.29% | 1,322–1,263–55 / -2.32% |

Hypothetical total ROI at 3.5 edge: 2024 -6.75% baseline vs -2.90% player; 2025 -7.86% vs -7.05%; 2026 -5.82% vs -4.64%.

No consistent positive return has been established. Profitability should not be claimed. Do not choose a threshold based solely on hindsight.

## Where adjustment helps (games where both opponents have zero prior games)

| Season | Games | ATS baseline MAE | Player-v1 MAE | Total baseline MAE | Player-v1 MAE |
|---|---:|---:|---:|---:|---:|
| 2024 | 215 | 15.887 | 13.394 | 17.813 | 14.638 |
| 2025 | 214 | 17.582 | 12.831 | 18.754 | 15.425 |
| 2026 | 211 | 17.591 | 16.378 | 19.934 | 19.161 |

For any game where at least one opponent has played fewer than five games, ATS MAE:
2024 14.122 -> 12.505; 2025 15.060 -> 12.607; 2026 15.002 -> 14.895.

The 2026 first-five-games benefit nearly disappears due to weaker player coverage. In 2026 early games where either team had **zero matched previous-season players**, baseline ATS MAE was 17.699 vs player-v1 18.034 (worse). This makes data completeness an urgent issue.

## Historical roster coverage

CBBD roster requests currently each returned 1,544 team records, including lower divisions. The count of teams with >=3 matched *previous-season* players:

- 2022: 396 / 1,544; 2,782 matched players total
- 2023: 420 / 1,544; 2,582 matched players total
- 2024: 425 / 1,544; 2,570 matched players total
- 2025: 396 / 1,544; 2,500 matched players total
- 2026: 257 / 1,544; 1,441 matched players total

These are across the entire provider roster universe, not just the D1 games tested. Differences can reflect missing coverage, ID aliasing, roster membership timelines, and off-season source revisions. Don't treat absent matches as absent players.

## Decision and next implementation priorities

Keep the **team baseline** as the reference. Keep **player-v1** as an experimental shadow model. Do not replace the published NFL model, launch CBB picks as "winning," or publish prospective CBB picks without new-time snapshots.

1. Audit roster date ranges and season alignment; validate match coverage against several real schools and reduce ID mismatches (no fuzzy names without additional checks).
2. Add source-quality/coverage gating: when player data is inadequate, do not force an adjustment. Decide thresholds on development years only; judge final performance prospectively.
3. Capture authenticated 2026–27 roster and transfer **timestamped snapshots** before games, and snapshot predictions with book lines to start a genuine prospective record.
4. Add current-season player availability and active rotations from dated game-by-game player box scores and actual injury reports when reliable, plus strength of prior team competition.
5. Continue independent spread and total calibrations and monitor prediction MAE, ROI and sample size. No hindsight threshold selection.
