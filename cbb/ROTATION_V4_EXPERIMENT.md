# Player-rotation v4 CBB experiment

*Research shadow only — do not promote until measured.*

This is an **optional fourth CBB research variant** that adds **past-game
player participation** to the original team, roster-adjusted v2, and
opponent-adjusted v3 models. It never modifies NFL files or historical frozen
CBB predictions.

## Verified data source

CBBD `/games/players` returns two team box-score records per game,
containing each player's athlete ID, minutes, starter flag, points, usage,
offensive rating and defensive rating. Verified against real records for
2023–24 through 2026–27. This endpoint is capped at **1,000 games/request**,
so `rotation_ingest.py` fetches by seven-day windows, de-duplicates
`gameId + teamId` and caches compressed season JSON.

The features are **strictly prior-game** features: all same-day matchups
receive frozen inputs BEFORE any same-date player data enters the state.

## What is tested

- Recent (up to five valid preceding team boxes) rotation and depth,
  top-five/top-eight player minute concentration, starter continuity,
  scoring share, usage, and average net player efficiency.
- Previous-game **missing key minutes** from players appearing at least
  twice in an earlier reference window and averaging 18+ minutes. This is
  a numerical indicator, **NOT an injury diagnosis**; benching, transfers,
  suspensions, and data problems can produce similar patterns.
- Missing or truncated player box = **unknown**, never fake an inactive
  player. We track source coverage and most recent box presence explicitly.
- Same-season opponent adjustments v3 and preserved roster features v2.

Compare v2, v3, v2+rotation and v3+rotation on identical 2024–26 games with
available market lines. Each season uses only earlier seasons to fit the
regressions, and within a season pregame features use only prior dates.
Report all directional ATS and totals, as well as 2.5/3.5/4.5/5.5 thresholds,
MAE and hypothetical -110 ROI, without retroactive threshold selection.

Historical roster snapshots and historical bookmaker lines are not
point-in-time validated, so this remains retrospective research even though
rotation is calculated chronologically.

## Commands

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q cbb/tests
python -m cbb.rotation_ingest --seasons 2022 2023 2024 2025 2026
python -m cbb.rotation_experiment
```

Workflow: **CBB Rotation V4 Historical Comparison**. Once the first run
successfully caches past player boxes, subsequent runs reuse them without
additional API usage. Workflow outputs appear in `cbb/outputs/rotation_v4`
and in archived GitHub Actions artifacts.

Do not assert present-game player availability or injuries from already
completed game boxes. Prospective v4 must use only game boxes obtained
and frozen *as of the actual run timestamp*.
