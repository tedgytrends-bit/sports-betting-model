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

### Latest test and code status

The user confirmed that GitHub Actions **Test efficiency feature integrity** passed after the test-fixture correction. The successful run was #38 (run ID `41101442766`), on commit `0020ecd9f6a05a508ce69f0a2651fa0709cce073`; it ran unittest discovery and compileall. That run predates the newest changes below, so those changes still require validation.

New commits on 2026-10-30:
- `01b1d4ed780c87203ff2fd708d38bfa818ec6dd8` — make `build_game_point_in_time_features()` tolerate schedule rows with missing season/week keys; such rows receive no matching records rather than crashing.
- `c3d3c7722ba97d8ec0cf6a1ade8589815a62054c` — add tests for DST conversion, incomplete schedule rows, and independent per-team/per-data-type coverage.

**Next action:** rerun **Test efficiency feature integrity** against current `main` and inspect the result. Do not claim these newest changes passed until confirmed.

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

1. Run **Test efficiency feature integrity** on current `main` to validate the newest robustness changes.
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


## 10. Corrected NFLMeta timing semantics (2026-10-30)

A review of the raw export showed that the earlier game-level audit misinterpreted timestamps:
- Injury CSV `source_observed_at` is an export/source capture timestamp. It is **not** a verified official injury-report publication timestamp. It must not be used to reject weekly report records as unavailable pregame, nor to assert they were pregame.
- Injury `source_url` points to NFL.com league injury pages or team official weekly injury-report pages. This establishes source provenance / weekly report presence, but does not establish historical publication time.
- Therefore report coverage must be reported as weekly export presence, with publication timing explicitly marked unknown unless a trustworthy publication/delivery timestamp is added.
- Normalize Rams aliases (`LAR` / `LA`) before team matching. In the uploaded export, both teams have weekly injury records for all 108 completed games in Weeks 1–8; this is presence, not pregame publication verification.
- Practice export includes `first_observed_at` and `first_delivered_at`. Use `first_delivered_at` for conservative data-availability checks. Keep `first_observed_at` as separate provenance. Exclude `historical_backfill=true` and missing delivery timestamps.
- Prior statement that 43 games had pregame practice coverage was generated using `first_observed_at`; it is superseded and must be recalculated using `first_delivered_at`. Do not repeat the 43 count as verified until rebuilt.
- `coverage_status` and `coverage_basis` describe practice-day report completeness: 3,039 complete and 884 partial delivered rows; 2,840 historical backfill rows have no delivery metadata. Completeness is not the same as pregame availability.
- Postgame `game_status`, scores, and outcomes remain labels only, never predictors.

Latest correction commits:
- `021a40f7641e52bf16c5424bf52adcf8dd0b689b` — separate weekly injury report presence from publication timing; use practice `first_delivered_at` for pregame eligibility.
- `1d5b02500664702ca6f919af6834359e69299db4` — align tests with weekly-report-presence semantics.

**Next action:** validate the current tests, rebuild the CSV coverage audit using `first_delivered_at`, and only then update the sample-size figures. Injury report publication timing remains unknown in this export.


### Recalculated practice coverage using `first_delivered_at` (2026-10-30)

The independent per-game audit was rebuilt from the uploaded NFLMeta ZIP and the full uploaded nflverse schedule, using exact Eastern-time kickoffs converted to UTC:
- 108 completed regular-season games in Weeks 1–8.
- Both teams have weekly injury-report records in the export for 108/108 games. This is weekly export presence only; official publication time remains unknown.
- Both teams have at least one non-backfill practice record with `first_delivered_at < kickoff` for 43/108 games.
- Weekly both-team practice-delivery coverage: W1 0/16, W2 0/16, W3 0/16, W4 0/16, W5 14/15, W6 14/14, W7 14/14, W8 1/1.
- The result is 43, coincidentally the same as the prior first-observed calculation, but this new count is independently verified using the intended delivery timestamp.
- CSVs exported separately: `game_level_delivery_audit.csv` and `weekly_delivery_coverage.csv`. This remains a coverage audit, not a performance/edge analysis.
