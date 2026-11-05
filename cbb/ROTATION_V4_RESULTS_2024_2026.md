# CBB player-rotation v4 — historical evaluation (research-only)

**Run:** [CBB Rotation V4 Historical Comparison 42123435013](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42123435013), 2026-11-05. Full fourteen-file CSV artifact `cbb-rotation-v4-comparison`. All tests, historical ingestion and four-model out-of-sample evaluations succeeded.

## Actual historical game-player coverage

- 2023–24: **12,486 / 12,486** team-game boxes present (100%).
- 2024–25: **12,584 / 12,584** (100%).
- 2025–26: **12,600 / 12,600** (100%).

This refers to a /games/players **record being present** for every completed team-game. Individual player boxes can still be flagged incomplete. In test games 2024–26, average recent pregame box completeness was approximately 96%; the model explicitly treats missing/incomplete boxes as unknown, not player absences.

## All directional leans (0-point threshold, hypothetical uniform -110 odds)

| Variant | ATS W–L–P | ATS decided win rate | ATS ROI | Total W–L–P | Total ROI |
|---|---|---:|---:|---|---:|
| Player v2 | 8,253–8,117–102 | 50.42% | -3.73% | 8,168–8,248–53 | -4.99% |
| Player+opponent v3 | 8,234–8,137–102 | 50.30% | -3.96% | 8,205–8,212–53 | -4.57% |
| Player+rotation v4 | 8,309–8,059–102 | 50.76% | -3.07% | 8,226–8,191–53 | -4.33% |
| Player+opponent+rotation v4 | 8,301–8,070–102 | 50.71% | -3.18% | 8,285–8,132–53 | -3.64% |

Totals and ATS are independent predictions. The v4 variants improve model directional results but do **not** demonstrate positive overall betting ROI or beat market MAE.

## ATS absolute point error (lower is better)

| Model | 2023–24 | 2024–25 | 2025–26 |
|---|---:|---:|---:|
| Player v2 | 9.805 | 9.829 | 10.694 |
| Player+opponent v3 | 9.660 | 9.650 | 10.531 |
| Player+rotation v4 | 9.748 | 9.791 | 10.249 |
| Player+opponent+rotation v4 | **9.598** | **9.603** | **10.083** |

## Key validity concern: improvement is not necessarily a rotation effect

The expanded models' **2025–26 season-opening** ATS MAE improved (player v3
15.474 → all-v4 13.921 on 211 games), but **no current-season player rotation
information exists before those games**. Those opener differences result from
refitting the regressions with a larger feature set and changed coefficients,
**not from observing player participation**. Do not interpret the entire
historical MAE gain as a demonstrated absence or injury-model advantage.

When **both teams had at least 5 previous games**, the net improvement from
adding rotation to v3 was **very modest**, despite the complete historical
game-player source:
- 2023–24: ATS MAE **9.078 → 9.053**.
- 2024–25: ATS MAE **9.047 → 9.011**.
- 2025–26: ATS MAE **9.235 → 9.215**.

Indicators for previously important missing players occurred in approximately
26–27% of games, but these do not prove injury status. Players can miss minutes
for many reasons; this is not an actual injury report.

## ATS at 3.5+ point model-market edge (-110 assumption)

- 2025–26 player+rotation v4: **1,075–916–33**, +3.03% ROI on 2,024 selections.
- 2025–26 player+opponent+rotation v4: **790–680–30**, +2.55% ROI on 1,500.
- The same v4 models returned negative 3.5+ ROI in both 2023–24 and 2024–25.
- Different models/thresholds select different sample sizes. Historical
  edge-threshold selection or a single winning season is insufficient to
  establish an investable advantage.

## Decision

**Retain baseline, v2, and v3 as frozen prospective benchmarks**. The v4
variants may be added as *optional, new-capture-only* experimental shadow
forecasts after source-cost and quality checks. All preexisting immutable
frozen files must remain unchanged, and only genuine subsequent pregame
capture records can count as prospective v4 selections.

Additional work needed before using rotation to claim injury effects:
documented availability reports with as-of timestamps, verified starting
roles, better separation of foul trouble/bench decisions from absences,
and model-validation criteria agreed before new holdout data arrives.
