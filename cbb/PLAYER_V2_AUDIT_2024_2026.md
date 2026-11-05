# CBB corrected player v2 research results (2024–26)

Run: [CBB Player V2 Roster-Corrected Backtest](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42111283067), 2026-11-05. Full CSV artifact `cbb-player-v2-comparison` (artifact 13453802118). All unit tests and data-ingestion steps passed.

## Key correction

CBBD identifies basketball seasons by ending calendar year. The previous v1 accidentally excluded many players whose `startSeason` equaled the target season, including legitimate incoming transfers and freshmen. Correct guard: `startSeason <= S <= endSeason`. Validation against CBBD current-season game participation confirmed the interpretation.

The corrected features now actually include transfer and freshman signals. Across 2025–26 roster source: 1,370 prior-year transfers matched, including 842 name-verified portal records, plus 151 high-ranking freshmen. Earlier v1 showed zero of both.

## Spread prediction MAE: lower is better

| Season | Team baseline | Corrected player v2 | Change |
|---|---:|---:|---:|
| 2023–24 | 10.813 | 9.805 | -9.3% |
| 2024–25 | 11.031 | 9.829 | -10.9% |
| 2025–26 | 11.157 | 10.694 | -4.1% |

## ATS performance for >= 3.5 point model edge (-110 assumed)

| Season | Team baseline | Corrected player v2 |
|---|---|---|
| 2023–24 | 1,377–1,371 (−4.34%) | 906–836 (−0.71%) |
| 2024–25 | 1,461–1,450 (−4.18%) | 1,006–957 (−2.16%) |
| 2025–26 | 1,571–1,468–58 (−1.29%) | 1,061–945–34 (+0.96%) |

The corrected player model is still weaker than market lines in absolute margin accuracy (2025–26 market error approximately 9.027 versus model error 10.694). The one positive ROI sample is modest and **does not establish a reliable tradable edge**.

## Totals

| Season | Team baseline MAE | Player v2 MAE | Player v2 total ROI at >=3.5 |
|---|---:|---:|---:|
| 2023–24 | 13.864 | 13.685 | −3.58% |
| 2024–25 | 13.535 | 13.333 | −7.17% |
| 2025–26 | 14.420 | 14.565 | −4.54% |

Totals improvements are mixed. Keep ATS and totals calibration separate; do not automatically use player-v2 for totals.

## Roster coverage and risk

The data source returns 1,544 roster objects including non-D1 teams, so the all-roster median is misleading; measure coverage specifically among tested teams. Matched prior-year player records across 2022–26: 3,660 / 3,436 / 3,574 / 3,705 / 2,811. Lower 2026 coverage should not be equated with actual talent loss.

Historical rosters are retrospective and can be revised, so these results are **not rigorously pregame point-in-time verified**. The 2026 backtest is not a pristine holdout after iterating on season alignment, even though the alignment fix was justified by source schema rather than profit.

Current objective: 2026–27 forward-only, timestamped, first-observed pretip snapshots on the isolated cbb-prospective branch. Publish results only when frozen records can be graded without later data edits.
