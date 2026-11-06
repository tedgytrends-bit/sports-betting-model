# CBB 2026–27 prospective research shadow

Workflow: **CBB 2026-27 Pregame Shadow Snapshots**

Captures at 13:05 UTC daily in November–April, with manual GitHub workflow dispatch. It only writes its prospectively observed game records to the isolated `cbb-prospective` branch. NFL production pages and the main branch are untouched by daily data writes.

## What is recorded

- `cbb/prospective/2027/snapshots/TIMESTAMP_RUNID.json`: append-only 8-day forward board, baseline, player-v2 and opponent-adjusted player-v3 spread/total/score projections (v3 only after its deployment), market as observed, roster coverage per team, model commit, capture time, and SHA-256 digests of current data sources.
- `cbb/prospective/2027/latest.json`: current projection board; UPDATED every run; not suitable for retrospective grading.
- `cbb/prospective/2027/frozen/GAME_ID.json`: earliest pretip capture **within 24 hours before tip** when at least one market line is present. Immutable, including original market prices or missing prices. Never regrade using updated lines.
- GitHub Actions artifact: the generated capture before publication, retained for independent audit.

CBBD sometimes reports an already-started game as `scheduled`. The UTC capture explicitly excludes all games at or before current time plus one minute, regardless of reported status.

### Integrity and limitations

This is a research-only shadow record, not betting advice or real betting positions. Older 2026–27 games before the first actual snapshot cannot be backfilled as prospective. If timing or odds availability prevent freeze, report that gap instead of inferring a pregame observation. Historical roster/portal backtests remain retrospective and may include historical roster revisions; new captures prove actual observed data as of capture time.

Next step is a dedicated grading audit against final scores using frozen source odds only; defer public Tedgy Trends integration until validated.


## Automatic shadow grading

The daily workflow also grades games reported **final** by CBBD, but only
when `frozen/GAME_ID.json` contains an earlier source observation that
was captured at least one minute before the recorded game tip. It independently
checks team IDs, start time and original frozen market prices. Never copy a
completed game's current line into a missing frozen record.

- `graded/YYYY-Www.json` is an incrementally maintained week-level audit.
  It records final scores, original book line/provider, ATS/total W/L/P by
  model, untracked completed games and invalidated snapshots.
- `season_results.json` summarizes every archived week at directional
  and 2.5 / 3.5 / 4.5 / 5.5 point edge thresholds. It shows season W/L/P,
  average prediction errors and hypothetical ROI with -110 odds.
- Tracking begins from the first actual capture on **2026-11-05
  21:29:14 UTC**. Earlier games are excluded, not retroactively graded.
- Completed games without a pretip freeze are persistently counted as
  untracked. The saved model predictions remain immutable.

These are **research shadow model leans**, not records of personal wagers.
Sources are imperfect; grading is only as sound as the archived pretip line
and final score source. Public website integration remains a separate step.

## Opponent-adjusted v3 prospective experiment

On and after deployment of the opponent-adjusted v3 code, new capture snapshots
contain three independent score, spread and total forecasts: **baseline**,
**player_v2**, and **player_opp_v3**. The v3 features use *only previous
calendar dates'* team scores and opponent strengths, with season resets.

Already frozen files remain untouched, including the initial 43 records
captured on 2026-11-05 before v3 was deployed. The grading code only
counts player_opp_v3 when that name appears in the original immutable
frozen record. Therefore v3 will initially have fewer genuinely tracked
prospective games; no synthetic historical v3 picks are credited.

Do not promote the v3 historical 3.5+ ATS performance to the public
record: the all-direction historical ROI was still negative and archival
rosters and odds are not proven point-in-time. This is a monitored,
research-only experiment.


## Player rotation v4 experimental shadow

Beginning **only with snapshots taken after the v4 deployment**, two more
optional models are captured:

- `player_rot_v4`: corrected player prior plus pregame rotation and
  recent key-player minute-change features.
- `player_all_v4`: corrected player prior plus opponent-adjusted team
  efficiency plus the same rotation features.

Earlier `frozen/GAME_ID.json` records stay completely unchanged. v4 is
graded ONLY where the model is present in an original pretip frozen
record. Report each model's prospective coverage separately; never generate
v4 projections retrospectively for already completed games.

The `cbb/live_rotation.py` command saves authenticated current-season
`/games/players` data in compressed Actions cache. New runs reuse older
observed games and re-query a seven-day overlap and any missed dates
since the last capture. The current-season cache is separate from
historical backtest data. If the cache vanishes it fetches observed
games from October to the current capture, not future results.

The snapshot includes SHA-256 provenance for the live and historical
player-box archives and pregame source coverage per team. Prior game
box scores are *observations*, not verified pregame injury notices;
availability indicators are approximate. This new experimental model
has negative 3-year historical ROI on all directional bets and is NOT
a verified profitable model. See
[rotation v4 audit](ROTATION_V4_RESULTS_2024_2026.md).


## Daily results and last-48-hour performance review

The automated final-score grading step now also publishes
`cbb/prospective/2027/performance_report.json` on the isolated
`cbb-prospective` data branch. This is a **derived**, refreshable
summary of the already-frozen, already-graded prospective record, not a
new backtest.

For each model (baseline, player v2, player+opponent v3, and both v4
rotation variants), it shows:

- Full-season and exact rolling **48-hour** and **seven-day** ATS/totals
  win-loss-push, number of eligible leans, hypothetical -110 ROI and
  margin/total point projection MAE.
- Separate **all directional leans (0 threshold)** and **3.5+ point
  edges**. Other pre-specified thresholds remain in `season_results.json`.
- Daily game scorecards labeled by **America/Chicago** date. The source
  journals remain grouped by ISO week in UTC.
- A last-60-games audit table with scores, original frozen book lines,
  each model's **actual captured** directional grade, original edge,
  and error.
- Paired error differences versus baseline **on identical pretip
  frozen games**. Newer models with no original frozen forecast report
  zero games rather than retrospective synthetic performance.
- Missing-frozen and invalid-record totals, and market provider mix.

A previously identified weekly rollover defect was fixed: journals for
a new Monday now enter the season results immediately, even when the
first-ever frozen observation happened on a Thursday. Regression tests
cover week boundaries, 2026/2027 year rollover, Central Time game dates,
paired samples, and excluding posttip or future observations.

This remains a **research shadow** report. A short-term winning sample
is not demonstrated profitability. All odds returns use a hypothetical
uniform -110 and may differ from accessible sportsbook prices.
