# Tedgy Trends CBB production

GitHub Actions runs the code on `main` and commits reports and first-frozen picks to `cbb-prospective`. The 2026–27 production files are under `cbb/prospective/2027/`.

| Output | Contents |
|---|---|
| [PROJECTIONS.md](https://github.com/tedgytrends-bit/sports-betting-model/blob/cbb-prospective/cbb/prospective/2027/PROJECTIONS.md) | Upcoming scores, spreads, totals and leans |
| [latest.json](https://github.com/tedgytrends-bit/sports-betting-model/blob/cbb-prospective/cbb/prospective/2027/latest.json) | Model inputs' fingerprints, snapshot timestamp, five forecasts and coverage by game |
| [README.md](https://github.com/tedgytrends-bit/sports-betting-model/blob/cbb-prospective/cbb/prospective/2027/README.md) | Official first-frozen grades and hypothetical ROI |
| [Finals](https://github.com/tedgytrends-bit/sports-betting-model/tree/cbb-prospective/cbb/prospective/2027/finals) | Source-identified final scores, including games without forecasts |
| [November recovery](https://github.com/tedgytrends-bit/sports-betting-model/blob/cbb-prospective/cbb/prospective/2027/research/2026-11-22-to-24.md) | November 22 pretip forecasts paired to verified finals and archived markets |

## Capture and grading

The production workflow calls `cbb-espn-fit.yml`. It restores historical team, player and rotation training data and refreshes the current ESPN season inputs. It fits the five original models, validates the board and pushes the snapshot, first-frozen records and readable projections in one commit. Named matchups can receive scores without market lines. Each freeze requires a forecast with a market before tip. A repeated run preserves the original freeze. On capture failure, the secondary board reports the original forecast timestamp alongside newly observed ESPN markets.

The independent grading workflow runs from a fresh production checkout. It reconciles official first-frozen entries using verified finals and publishes the grade journal, cumulative records, readable report and finals inventory together. ESPN failures have bounded retries and an NCAA scoreboard mirror fallback for finals. Reconstructed performance uses archived lines when present or explicit closing quotes retrieved after the final. These research grades may overlap official games.

## Operating the model

Check the current capture timestamp and the source provider before reading the board. For a stale report, inspect the Actions job for the first failing ingestion, validation or publication step. The workflow files hold the UTC schedules. GitHub can queue scheduled work. A manual dispatch or changing the corresponding trigger file on main exercises the same entry point.

Normal runs restore the validated 2022–26 historical caches. They save derived training features, team priors and a canonical game index to the production branch, then replay all five models against the same slate before publication. A cold runner can fit from the versioned historical features and last saved team priors. Its source string identifies the prior timestamp. The checkpoint drill exercises that path with both historical caches absent and publication disabled. Current ESPN box scores supply observed minutes, scoring and starters. Archived advanced rotation observations are retained where available. New ESPN boxes can lack player usage and efficiency ratings; the existing model applies its missing-value handling.

The daily 10 AM Central briefing reads production reports. The hourly production monitor checks publication and alerts. Failure issues identify the failing run and are resolved after a later verified recovery.
