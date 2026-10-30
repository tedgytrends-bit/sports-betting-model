# NFL Betting Model — Project Handoff

Last updated: 2026-10-30

This file is the continuity record for future ChatGPT conversations. Read it before changing code, running workflows, or interpreting model results. Confirm the current GitHub state because this document can become stale.

## 1. Repository and operating rules

- Repository: https://github.com/tedgytrends-bit/sports-betting-model
- Streamlit app: https://sports-betting-model-sno3lwyvn2fzg9cyrfaqs3.streamlit.app/
- Primary monitor: Bovada Projection Monitor.
- The user prefers the assistant to inspect the repository and carry work forward proactively. Explain any action the user must take in plain, numbered steps.
- When providing code for manual edits, provide complete replacement files rather than vague partial-edit directions.
- Do not claim a workflow passed unless its actual run result is confirmed.
- Do not consume NFLMeta/EndzoneAPI credits unless the user explicitly authorizes it.
- Do not make changes to frozen projections or the live model as part of experimental research unless explicitly agreed.

## 2. Betting philosophy and evaluation standards

The model's goal is to find mispriced markets, not simply predict winners. Compare the market's implied probability/line with the model's fair probability/line and require a meaningful edge.

- Be independent and willing to push back. Do not change a conclusion merely because the user challenges it.
- Confidence scale is 1–10. An 8.0+ is generally eligible to be called an official play, subject to discussion and market price.
- No action for action's sake. A pass is a valid result.
- Validate chronologically and prospectively. Avoid leakage, hindsight, and claims of edge unsupported by out-of-sample evidence.
- Evaluate ATS and totals separately, including edge buckets such as 3.5+, 4.5+, and 5.5+.
- Preserve frozen projection snapshots as immutable baselines. Current/latest projections are a separate outlook and must never silently replace frozen projections.
- Track the model's hypothetical game picks separately from the user's actual betting ledger.

## 3. User betting ledger conventions

- 2026 season is separate from historical seasons.
- Standard unit = $10.
- For DraftKings Predictions, use actual dollars risked after fees/taxes as recorded risk, not nominal trade amount.
- Units risked = actual risk ÷ $10.
- Unit profit = net profit ÷ $10.
- Keep teasers, parlays, and boosted bets separate unless the user explicitly says otherwise.
- User's actual bets ledger is separate from model-generated hypothetical plays.

## 4. Model status and known validation results

The model has undergone chronological/backtesting and prospective-audit work. Prior audits covered 1,006 games with no warnings, but did not establish a dependable betting edge:
- ATS: approximately -4.64% ROI at a fixed 3.5-point threshold, worse than the market benchmark in that audit.
- Totals: approximately +0.13% overall in that audit, too small/unstable to establish a reliable edge.
- Treat these as prior audit results, not current live performance. Re-run the relevant audit before making current performance claims.

The model should continue to be evaluated prospectively. Do not relax thresholds or change evaluation rules to make results look better.

## 5. Injury work: live model versus separate research

### Existing live-model injury integration

PR #26 was merged (commit `efec4540dacd1ac546a7bdb25ed84704305e49b2`), adding `injury_model.py`.
- Loads nflverse injury reports for seasons 2021–2026.
- Historical report rows are filtered to pre-kickoff timestamps to prevent leakage.
- Deduplicates per player/team/game week.
- Uses latest saved snapshot for upcoming games when available.
- Derives position-group features (QB, OL, skill, defense), status and practice participation.
- Ridge model learns relationships rather than relying on fixed hand-written point penalties.
- This experimental feature has not yet been proven to improve out-of-sample accuracy.
- Frozen projections remain unchanged.

### NFLMeta data and constraints

The user created a free NFLMeta account and stored `NFLMETA_API_KEY` in GitHub Actions secrets.
- Free plan: 5,000 monthly requests, 25,000 monthly row allowance, 20 requests/minute, max first 1,000 rows per individual query.
- Free plan is not for commercial use; revisit licensing before any commercial use.
- Broad season query exceeded the 1,000-row result window; use week-scoped queries and pagination.
- API rate limit required throttling (3.5 seconds between requests) and retry after 429.
- Never use credits without explicit user permission.

Uploaded 2026 backfill export contained:
- 2,394 player-week injury records.
- 6,763 practice-day records.
- Weeks 1–8 populated at export time.
- Practice codes: DNP 1,899; LP 2,146; FP 2,298; missing 420.
- Weekly injury designations: Out 475; Questionable 427; Doubtful 30.
- 2,840 practice-day rows were marked historical backfill. These cannot be used as pregame features.
- Global API metadata reported 2,385 while week totals summed to 2,394; preserve all records and investigate, do not silently discard the difference.
- `game_status` values such as Inactive/Out are postgame outcomes and must never be predictors.

### Important timestamp rules

- NFLverse `gametime` is Eastern Time. Convert `gameday + gametime` using `America/New_York` (including daylight-saving rules) to UTC before comparing with NFLMeta observation timestamps.
- `source_observed_at` is the capture/observation timestamp, not proof of original report publication time. Never backdate it.
- Practice `first_observed_at` is separate and must independently precede kickoff.
- Retrospectively backfilled practice rows are excluded even if they contain a plausible practice date.
- Missing timestamps mean unknown/unverified, not eligible and not zero.
- For a game-level dataset, filter each underlying record against that game's kickoff. Do not rely on weekly aggregates or just the latest timestamp for the whole week.

## 6. Separate NFLMeta research pipeline

Files:
- `nflmeta_injury_analysis.py`
- `tests/test_nflmeta_injury_analysis.py`

The module is deliberately separate from the live model. It contains:
- `load_nflmeta_exports()`
- `build_team_week_features()` for descriptive team-week summaries
- `build_game_injury_features()` legacy team-week join/timing diagnostic; do not treat this as the final leakage-safe game-level feature builder
- `build_game_point_in_time_features(schedule, injuries, practice)` — the intended game-level builder. It selects injury reports and practice records individually only when their observation timestamps are strictly before that game's kickoff, excludes historical backfills, tracks report/practice coverage separately, and does not use postgame game-status fields as predictors.
- `export_injury_research()` now exports team-week and per-game feature CSVs using the point-in-time builder.

### Current latest commits

- `e537647a31b4438c64103a685666ee9e035775a3` — add per-game point-in-time injury feature builder and use it in research export.
- `1d48b279825606ba475daf2b44be829be5f7dfcc` — add regression tests for per-record kickoff filtering.
- `2351d2b890824d601e5aeb828299259dab5c2feb` — fix malformed import line in test file.
- `b5b537c0ce10e8a197a20d2f8e5bf6074bd4e50e` — correct test fixture: retain historical-backfill flag so that the test verifies backfilled practice records are excluded.

### Immediate next step / current test status

The latest full unittest run failed one test:
`test_game_features_filter_each_record_at_exact_kickoff`
Expected `home_practice_records_pregame == 2`, got 3.

This was a test-fixture mistake, not evidence that the production filter was wrong: the fixture explicitly changed player 2's `historical_backfill` flag from True to False, making that third practice row legitimately eligible before kickoff. The latest commit removes that incorrect override, so the row remains backfilled and should be excluded.

**The suite has NOT yet been rerun after commit `b5b537c`.** The next action is to rerun the GitHub Actions workflow **Test efficiency feature integrity** and confirm the result. If it fails, inspect the exact assertion and fix the underlying issue; do not guess.

## 7. GitHub Actions workflow guidance

The user can manually run workflows from GitHub:
1. Open repository → Actions.
2. Select **Test efficiency feature integrity** in the left workflow list.
3. Click **Run workflow**.
4. Keep the default branch selected and click the green **Run workflow** button.
5. Report whether it passed; if failed, share the failing output.

The compile check used in the recent workflow:
`python -m compileall -q app.py pages model.py research tests`

The unit-test command:
`python -m unittest discover -s tests -v`

Do not ask the user to run extra workflows without a clear purpose. The workflow is a validation step; the assistant should inspect logs and repo state when possible.

## 8. Next project milestones

1. Add/verify tests for exact ET-to-UTC conversion, daylight-saving handling, missing timestamps, each side's independent coverage, historical backfill exclusion, and post-kickoff report exclusion.
2. Generate the separate game-level NFLMeta research export from the uploaded data and schedule.
3. Audit feature coverage by week, team, and game; explicitly count how many games have report and practice data verified before kickoff for both teams.
4. Join only completed-game scores/results for research outcomes. Keep postgame inactive/out fields as labels only.
5. Conduct exploratory analysis and chronological validation by feature group. Report sample sizes and uncertainty; do not infer a betting edge from small or dependent samples.
6. Keep all research findings separate from live projections until evidence supports a controlled experiment.

## 9. Handoff instructions for a new conversation

Start by:
1. Reading this file.
2. Fetching the current repository files and latest commits; do not assume this document is fully current.
3. Checking the latest GitHub Actions run and the current Streamlit deployment state if relevant.
4. Confirming the user's most recent instruction before making consequential changes.
5. Continuing from the immediate next step above.

The user should be able to say: "Continue my NFL betting model project. Read PROJECT_HANDOFF.md, verify the latest GitHub state, and pick up at the next step."
