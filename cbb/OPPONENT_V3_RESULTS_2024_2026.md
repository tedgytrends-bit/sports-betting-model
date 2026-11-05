# CBB opponent-adjusted v3 — historical evaluation

Evaluated 2026-11-05 in [GitHub workflow 42116557191](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42116557191); artifact `cbb-opponent-v3-comparison`. All four variants graded on matching completed games in 2023–24, 2024–25 and 2025–26, fitted to only earlier seasons. All deterministic tests passed.

## Combined directional record: no minimum edge, hypothetical -110

| Variant | ATS W–L–P | ATS decided win % | ATS ROI | Totals W–L–P | Totals ROI |
|---|---|---:|---:|---|---:|
| Team-only baseline | 8171–8200–102 | 49.91% | -4.69% | 8124–8291–53 | -5.50% |
| Team + opponent adjustment | 8243–8125–102 | 50.36% | -3.83% | 8114–8302–53 | -5.62% |
| Corrected player v2 | 8253–8117–102 | 50.42% | -3.73% | 8168–8248–53 | -4.99% |
| Player + opponent adjustment v3 | 8234–8137–102 | 50.30% | -3.96% | 8205–8212–53 | -4.57% |

These records only include games with usable market lines and nonzero projected edge. Edge threshold zero is not an edge filter. Some variants omit a handful of perfectly equal projections and thus have slightly different decision totals.

## ATS margin MAE (points; lower is better)

| Season | Team baseline | Team + opp | Player v2 | Player + opp v3 |
|---|---:|---:|---:|---:|
| 2024 | 10.813 | 10.584 | 9.805 | 9.660 |
| 2025 | 11.031 | 10.690 | 9.829 | 9.650 |
| 2026 | 11.157 | 10.859 | 10.694 | 10.531 |

## Player ATS - 3.5+ point edges (hypothetical -110)

| Season | Player v2 | Player + opponent v3 |
|---|---|---|
| 2024 | 906–836 (-0.71%) | 701–658 (-1.53%) |
| 2025 | 1006–957 (-2.16%) | 784–727 (-0.94%) |
| 2026 | 1061–945–34 (+0.96%) | 838–721–29 (+2.57%) |

Threshold sample sizes differ. Do not select a profitable threshold based on hindsight. 2026 has been examined and is not a pristine untouched holdout.

## Total MAE

| Season | Player v2 | Player + opponent v3 |
|---|---:|---:|
| 2024 | 13.685 | 13.697 |
| 2025 | 13.333 | 13.269 |
| 2026 | 14.565 | 14.441 |

## Engineering decision

**Retain original two models as fixed prospective benchmarks.** Allow opponent-adjusted v3 as a **separate experimental prospectively tracked candidate**, not a replacement. ATS prediction errors improved in all three past seasons, but direction ROI did not improve overall. Totals direction was modestly better overall and total MAE improved in two of three seasons.

No results are betting recommendations or proof of an edge. Previous-year player performance is pregame information, but archived target-season roster membership and transfers may be retrospectively revised; source historical lines are not timestamp-verified and ROI uses assumed -110 prices. All future records must be frozen before actual tip-off and neither the older v2 nor market lines may be retrospectively changed.

## Diagnostic: when opponent-adjustments help

From the exact game-level v3 backtest artifact, dividing by **pregame**
number of games played (diagnostic only, not a tuned betting rule):

| Season | Either team under 5 games: v2 → v3 ATS MAE | Both teams 5+ games: v2 → v3 ATS MAE |
|---|---|---|
| 2024 | 11.787 → 11.741 | 9.251 → 9.078 |
| 2025 | 11.933 → 11.800 | 9.239 → 9.047 |
| 2026 | 15.136 → 15.124 | 9.441 → 9.235 |

The added information helps most once teams have accrued several current-
season games. In 2026 season openers (both teams at zero games), player-v3
was actually **worse** than player-v2: 15.474 versus 15.209 ATS MAE on 211
games. Do not automatically promote v3 for early-season games. Next priority
is verified current-season player rotation and availability (starter, actual
minutes, athlete ID from timestamped /games/players records), while preserving
a clean prospective comparison.

This split is descriptive and was inspected after the results; it is **not**
a prespecified or untouched holdout-based betting filter.
