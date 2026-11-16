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
- Practice `first_delivered_at` is the conservative availability timestamp and must be strictly before kickoff for pregame eligibility. Keep `first_observed_at` as separate provenance; it does not replace delivery time.
- Retrospectively backfilled practice rows are excluded even if they contain a plausible practice date.
- Missing delivery timestamps mean unknown/unverified, not eligible and not zero.
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
- The 43-game practice-coverage figure has since been independently rebuilt using `first_delivered_at` and exact kickoff conversion; see the completed audit below. Do not describe it as injury-report coverage.
- `coverage_status` and `coverage_basis` describe practice-day report completeness: 3,039 complete and 884 partial delivered rows; 2,840 historical backfill rows have no delivery metadata. Completeness is not the same as pregame availability.
- Postgame `game_status`, scores, and outcomes remain labels only, never predictors.

Latest correction commits:
- `021a40f7641e52bf16c5424bf52adcf8dd0b689b` — separate weekly injury report presence from publication timing; use practice `first_delivered_at` for pregame eligibility.
- `1d5b02500664702ca6f919af6834359e69299db4` — align tests with weekly-report-presence semantics.

**Completed:** the CSV coverage audit was rebuilt using `first_delivered_at` and exact Eastern-time kickoffs converted to UTC. It found 43/108 completed games with both teams having at least one non-backfill practice record delivered before kickoff. Weekly coverage: W1 0/16, W2 0/16, W3 0/16, W4 0/16, W5 14/15, W6 14/14, W7 14/14, W8 1/1. This is practice-delivery coverage only. Injury-report publication timing remains unknown in this export.


### Recalculated practice coverage using `first_delivered_at` (2026-10-30)

The independent per-game audit was rebuilt from the uploaded NFLMeta ZIP and the full uploaded nflverse schedule, using exact Eastern-time kickoffs converted to UTC:
- 108 completed regular-season games in Weeks 1–8.
- Both teams have weekly injury-report records in the export for 108/108 games. This is weekly export presence only; official publication time remains unknown.
- Both teams have at least one non-backfill practice record with `first_delivered_at < kickoff` for 43/108 games.
- Weekly both-team practice-delivery coverage: W1 0/16, W2 0/16, W3 0/16, W4 0/16, W5 14/15, W6 14/14, W7 14/14, W8 1/1.
- The result is 43, coincidentally the same as the prior first-observed calculation, but this new count is independently verified using the intended delivery timestamp.
- CSVs exported separately: `game_level_delivery_audit.csv` and `weekly_delivery_coverage.csv`. This remains a coverage audit, not a performance/edge analysis.


### Prospective snapshot-difference audit (2026-10-30)

- Added `scripts/audit_injury_snapshots.py` in commit `6d41f2c`; comparison logic extracted for unit testing in `9db6415`.
- Updated `.github/workflows/capture-injury-snapshots.yml` in commit `7e4451f` to run the audit after each scheduled injury-feed capture and commit both snapshot and audit CSVs when changed.
- Audit outputs: `data/injury_snapshot_audits/snapshot_changes.csv` and `snapshot_change_summary.csv`.
- The audit compares adjacent snapshots within the same season/week/team. It records feed-membership changes and changes to player identity/position, injury fields, report status, and practice fields. It records hours until that team's earliest scheduled kickoff using Eastern-time schedule conversion.
- Capture timestamps mean the repository observed that version of the feed; they do not establish the NFL's original publication time. A player absent from a later feed snapshot is only a feed-membership change, not confirmed official report removal.
- The first snapshot in a sequence has no earlier baseline and therefore does not generate an initial-state event. Interpret change counts as observed transitions between archived versions, not a complete history of all injury developments.
- This audit is descriptive research only. Do not feed it into the live model or frozen projections until data integrity, coverage, and out-of-sample value are separately validated.
- Added `tests/test_injury_snapshot_audit.py` in commits `521ee8d` and `280e9d4`, covering player practice-status transitions, feed membership additions/removals, unchanged records, and Eastern daylight/standard-time kickoff conversion. Tests use `unittest` so the existing `python -m unittest discover -s tests -v` workflow discovers them.
- The workflow was updated but has not yet completed a post-change scheduled run in this handoff. Verify the next scheduled run and inspect the generated CSVs before relying on the output.


## 11. November 10, 2026 Week 9 completion and subsequent margin experiment

**This section is newer than the October 30 status above. Preserve the old sections only as historical context.**

- Week 9 completed research grade: **official injury ATS 3–11–1, totals 9–6**, on all 15 games. Verified at `data/week09_review/week09_full_findings.md`; audit workflow **42839963082** passed. No public frozen records were rewritten.
- Week 9 official injury margin MAE **11.49**, market margin MAE **8.63**, totals MAE **11.01** vs market **10.17**. Eight strong ATS edges lost and one pushed. These are diagnostics, not proofs of a new edge.
- The baseline and research models were historically evaluated on **1,021 common archived games** (late 2022 through 2026 W8). Baseline mean absolute predicted winning margin **2.99**, mean market spread magnitude **5.06**, realized mean absolute margin **11.14** (outcomes are noisy). Baseline margin MAE **10.40** vs market **9.77**; **844/1,021** baseline ATS selections were underdogs, grading **408–416–20**. At 5+ margin edges baseline ATS was **116–119–6**. The exact stratification and caveats are documented in `docs/week09_margin_diagnostic_20261110.md`.
- **Structural fact:** With identical inputs/training and alpha, separate home/away Ridge models subtracted are mathematically identical to direct-margin Ridge. This was empirically confirmed across all 1,021 historical folds; maximum absolute prediction discrepancy was **1.47×10⁻¹⁴**. Therefore converting to a direct-margin target alone would do nothing.
- **New live-excluded experiment:** Added `scripts/run_margin_feature_scale_shadow.py` and `.github/workflows/standardized-margin-shadow.yml`. The workflow **42846338257** completed successfully and saved `data/week09_review/standardized_margin_shadow_20261110.json` plus .csv. It uses public nflverse input only, no NFLMeta/EndzoneAPI credits. It tests unscaled two-score Ridge, unscaled direct-margin Ridge identity, and train-only StandardScaler + Ridge(alpha=10) with exactly the same chronological folds. No results after 2026 W8 were included.
- Margin MAE raw → standardized: **2023 10.5522→10.3881, 2024 10.5840→10.3369, 2025 10.3975→10.1637, 2026 W1-8 9.6795→9.7912**. The latest 2026 season W1-8 **worsened**, and market MAE was better in all years. At 3.5+ ATS edge, 2025 raw **62–65** vs standardized **58–43**, but 2026 raw **23–19–2** vs standardized **26–22**. Different number of selections. **Decision: standardization is NOT approved for promotion.** 2025/26 were already studied before; this is not newly sealed validation.
- **Latest player injury backtest:** Workflow **42839963098** passed with **1,036 common games**, 2026 Week 9 included in chronological rerun. Baseline margin MAE **10.413**, injury **10.425**; totals MAE **10.588** vs **10.583**. At 3.5+ ATS simulated ROI using recorded historical odds: **−5.43% vs −4.13%**. No injury promotion.
- **QB validation:** `data/player_injury_backtests/qb_point_impact_validation_20261110T152632Z.json` verifies 68 QB1-OUT team-games; its 47-case 2024–2026 holdout has estimated QB absence magnitude vs observed team scoring residual Pearson r ≈ **−0.089** (95% bootstrap interval spans zero). `qb_actual_replacement_validation_20261110T152644Z.json` also shows weak heldout association (r ≈ −0.115). These are not robust estimates of point value. Week 9 QB overlay reversed ATS sides on NYG–PHI and BUF–MIN; at least one QB identification was source-unverified in 12/14 Sunday/Monday games. Do not adjust live coefficients based on those games alone.
- **Next priority:** Validate Week 10 starter names / QB replacements against timestamped pregame sources, then compare verified-replacement-only shadow outputs and historical margin/ATS error **without rewriting Week 8–9 official records**. Make changes only after consistent chronological and prospective evidence. Preserve the two public views (Baseline and Injury), keep Combined and Efficiency for separate research, and keep totals separate.

**Canonical research links:** `docs/week09_margin_diagnostic_20261110.md`, `data/week09_review/week09_full_findings.md`, `data/week09_review/standardized_margin_shadow_20261110.json`. The published site code and production model coefficients were not modified by this research.


## 12. November 10, 2026 — subsequent six-versus-ten lookback test and QB provenance audit

Latest detailed writeup: `docs/week10_margin_lookback_qb_evidence_20261110.md`.

- **Workflow integrity repaired:** the prior `Test efficiency feature integrity` run #42847190835 failed only because pytest was absent; updated `.github/workflows/test-feature-integrity.yml` to install pytest and run the QB suite. Run **#42851029681 passed**.
- **Lookback experiment succeeded:** `scripts/run_lookback_margin_shadow.py` and `.github/workflows/lookback-margin-shadow.yml` run **#42851364512 passed**, producing `data/week09_review/lookback_margin_shadow_20261110.csv` and `.json`. All 1,021 game predictions were matched across both horizon configurations, with every 2026 outcome after W8 excluded.
- Raw 6-game vs raw 10-game margin MAE: **2023 10.6444 vs 10.5522; 2024 10.6325 vs 10.5840; 2025 10.2710 vs 10.3975; 2026 W1-8 9.8166 vs 9.6795.** Standardized 6-game vs standardized 10-game also favored 10 in three of four periods. Early 2026 W1–4 weakly favored 6, later W5–8 favored 10. **Neither six-game candidate is promoted**. The existing ten-game lookback remains unchanged.
- Week 9 QB source sensitivity on same 14 Sunday/Monday games: **2/14 fully verified**, **12/14 with at least one unverified starter**. Non-QB injury model ATS **5–8–1**; published QB-overlay model **3–10–1**; retrospective only-apply-overlay-if-both-starters-verified policy **4–9–1**. Of the two QB-induced losing flips, NYG–PHI had both verified starters, BUF–MIN had one provisional. **Starter verification alone does not solve QB point-impact calibration.** No source gate was implemented in production.
- 2026 W1–8 7+ point market favorites (28 games) had average realized favorite-relative margin **5.07**, versus market **8.66**, unscaled baseline **4.84**, and standardized baseline **7.07**. This explains why 2026 scaled margins worsened, but it does not prove a persistent underdog edge.
- All new work is research-only; no published Week 8/9 scores, odds, records, model coefficients, Week 10 official forecasts, or totals projections were changed; no NFLMeta/EndzoneAPI credits were used.
- **Next research focus:** pregame QB starter provenance and replacement calibration, not further lookback grid-searching. If testing new models, pre-register and preserve future prospective games as new truly unseen evidence.


### QB source timing/provenance follow-up (Nov 10, 2026)

- Added `research/audit_qb_starter_source_metadata.py` with unit tests and research-only GitHub Action. Report at `data/week09_review/qb_source_metadata_audit_2026_week09.json`, plus `docs/week10_margin_lookback_qb_evidence_20261110.md`.
- Archived Week 9 starter confirmations had **8** entries; **one source** was 1,146 hours (47.75 days) old, for ATL Michael Penix Jr. against Cincinnati in Week 9, referencing an article dated Sept 21, 2026. This is *not* sufficient proof of a November starter. Seven entries have recent-looking metadata but still require article-content confirmation.
- The metadata audit checks game/team membership, HTTPS link presence, exact DST-aware kickoff and publication timestamps. It **does not read article content** and never labels these entries source-verified on that basis alone.
- The `capture_qb_aware_injury.py` dated-override check currently rejects same-day sources by comparing with midnight game date, rather than kickoff. The new research audit uses actual kickoff time, but **production capture and QB coefficient logic were not changed**.
- Next task: verify Week 10 starters from contemporaneous primary sources and design a source-freshness gate for future QB captures without rewriting the published records. The verification source itself must be game-specific, not an old generic starting-QB article.

## 13. November 10, 2026 — Week 10 starter evidence and capture safety

Detailed status: `docs/week10_qb_reliability_20261110.md` (read before making any QB model changes).

- Confirmed an actual **input-quality bug** in Week 10 pregame research: the first QB-aware Injury shadow capture used **Tyler Huntley** for BAL@LAC Monday Nov 16 although Baltimore had placed Huntley on injured reserve Nov 5. The Ravens officially stated on Nov 9 that head coach Jesse Minter expects **Jacoby Brissett** to start against the Chargers. The generic upcoming nflverse schedule QB fields are provisional and may be stale or incompatible with IR.
- Added `research/validate_qb_starter_confirmations.py` to require a **game-specific content review attestation**, publication/review timestamp before actual kickoff, supported confirmation kind and review note before elevating a manually provided starter to `verified_pregame`. URLs + timestamp alone are insufficient. Older Week 9 confirmations without new attestation fields do not silently become verified.
- Added optional **coach-expected-but-unverified** QB records in `qb_epa_model.py` and `injury_model.project_qb_aware_injury()`, preserving existing callers with defaults. Input `data/qb_starters/2026_week10_expected.csv` contains Brissett (GSIS `00-0033119`), source `baltimoreravens.com` Nov 9. He remains `coach_expected_pregame_unverified`, not confirmed. **Do not promote conditional starters to verified.**
- Added `data/qb_starters/2026_week10_watchlist.csv`: Baltimore Lamar Jackson and Tyler Huntley IR, Brissett coach expected, Arizona Minshew uncertain with Beck conditional, Thursday NYG J.J. McCarthy hip limited, WAS Jayden Daniels full estimated practice. The research capture now **fails closed if an IR/OUT watchlist QB is selected by provisional schedule data**, and flags `release_ready=false` unless all starters have explicit reviewed confirmation. Arizona remains unresolved; Minshew is still provisional.
- Added `verified_only_projected_home/away/total` diagnostic columns to the Week 10 research preview. If either starter is not verified, they use the **preserved non-QB Injury base scores** rather than a potentially misleading QB shift. Existing candidate scores and the official public model remain unchanged.
- **Research capture run #42884832007 SUCCEEDED**, 33 targeted tests passed, all 14 Week 10 games projected, known IR blocker verified no wrongly selected IR QB. 27 schedule-provisional + 1 coach-expected, 0 verified. `release_ready=false`. **No Week 10 official projection was frozen/published based on this test.**
- Baltimore's research QB home-margin adjustment changed from about **-2.37 (wrong IR Huntley)** to **-3.68 (coach-expected Brissett)**. This is an input correction, not proof that a -3.68 estimate is calibrated. Arizona still requires final team information and the current Minshew-based research score must not be advertised as reliable.
- The old Week 9-only QB shadow workflow was disabled for automatic pushes, preventing repeated failures after Week 9 completed. The current Week 10 research capture defaults to Week 10, cancels superseded runs, and keeps artifacts for deliberate review.
- **Do not change/overwrite** public Week 8–9 frozen predictions, prospective ATS/totals records or official model coefficients. Next: verify Week 10 starters and source timestamps as team injury/inactive reports arrive; record prospective candidate performance against contemporaneous Bovada prices before considering any QB point-value/calibration promotion.



## 14. November 12, 2026 — Week 10 first-public site and Bovada board

**Full canonical implementation report:** `docs/week10_publication_and_qb_corrections_20261112.md`.

- **All 14 Week10 Bovada screenshot quotes** from Thursday Nov12 7:20–7:21am CT, including both ATS prices and total prices, appended to `data/bovada_lines.csv` and captured immutably at `data/public_snapshots/nfl_week10_bovada_initial_2026-11-12.csv`. Times are approximate mobile screenshot times, not sportsbook issue timestamps. Saturday/Sunday updates must append snapshots without rewriting the Thursday archive.
- New guarded `scripts/publish_week10_initial.py` with action `publish-week10-initial.yml` completed **run #43227603908 successfully**. Published **28 row / 14 games ×2 public models** file `data/public_snapshots/nfl_week10_initial_projections_2026-11-12.csv` and manifest at **2026-11-12T13:29:01Z** BEFORE Thursday kickoff. Existing Baseline coefficients/10-game feature lookback unchanged; Injury QB EPA component still uncalibrated. 27/28 QB names in release were schedule-provisional, one BAL Brissett coach-expected-unverified. This was a valid first-public projection vintage, but **not a verified final QB and inactives grade**.
- Static public site `docs/index.html` now displays WEEK 10, all 14 in kickoff order, a **Baseline/Injury view switch**, projected scores, ATS and totals leans, sportsbook lines and source screenshot timestamps. Site URL: https://tedgytrends-bit.github.io/sports-betting-model/ . Archived exact original Week9 site as `docs/week09.html` at https://tedgytrends-bit.github.io/sports-betting-model/week09.html . Streamlit defaults to `pages/Week_10_Projection_Board.py`, old Week9 archived in app. Site smoke tests and GitHub Pages deploy passed.
- Corrected public Results: `data/public_snapshots/nfl_week09_results_summary_2026-11-10.csv` displays audited **official Week9 Injury 3–11–1 ATS / 9–6 totals** over all 15; **Baseline Week9 5–9–1 ATS / 8–7 totals is retrospective research only**, never conflate with official. Week8 all 14 retained.
- Two **confirmed Sunday starter-data bugs** uncovered after first release: Cardinals **Carson Beck** (GSIS 00-0041561) vs Rams, **Gardner Minshew IR and out**; Seahawks **Drew Lock** (GSIS 00-0035704) vs Raiders, **Sam Darnold out**. Official team sources reviewed before Sunday; attestation file `data/qb_starters/2026_week10_confirmed.csv`, status updates `2026_week10_watchlist.csv`. Cited team sources in detailed report.
- Separate `scripts/capture_week10_qb_corrections.py` plus action `capture-week10-qb-corrections.yml` **run #43231259929 SUCCESS**, saved `data/public_snapshots/nfl_week10_qb_corrected_2026-11-12.csv` (2 injury research-preview rows) and JSON manifest at **2026-11-12T13:51:47Z**, preserving original first-public scores and market unchanged. Corrected **LA@ARI: LA 21.0, ARI 19.1, total 40.1** and **SEA@LV: SEA 23.3, LV 21.4, total 44.7**. The website and Streamlit display those two clearly labeled revised Injury previews; Baseline and all other initial rows remain frozen. Carson Beck has **0** prior NFL game dropbacks so his +1.75-point QB research adjustment is ***not calibrated***; do not regard the enlarged ARI +9.5 ATS gap as evidence of EV.
- **Thursday WAS@NYG** user Bovada NYG -2 total41, initial Injury **WAS 23.2 NYG 24.9 total48.1** → WAS+2 gap only 0.3 pts, Over41 gap7.1. Baseline WAS21.2 NYG24.9 total46.1. NWS predicts **80% chance Thursday-night rain, winds 10–13mph gusts up to 23mph** at East Rutherford; no explicit weather feature in scoring model. **Do not auto-recommend Over based solely on its 7.1-point numeric gap.** Recheck kickoff radar and inactives, with both Daniels/McCarthy active status not yet locked early Thursday.
- **Next deliverable:** after user supplies Saturday-night/Sunday-morning Bovada screenshots, append odds and make an independently timestamped **pre-Sunday final** projection *before* kickoffs using actual injury inactives and confirmed starters; do NOT rewrite TNF or Thursday initial predictions or prior Weeks8–9. Avoid paid NFLMeta/EndzoneAPI credits unless user authorizes them.


## 15. November 15, 2026 — Sunday user Bovada refresh, final injury statuses and NE–DET inactives

**Canonical detailed handoff:** `docs/week10_sunday_pregame_20261115.md`.

- User's Sunday 6:56 a.m. CT Bovada screenshots cover all **13 remaining games**; saved line, total, both price pairs to immutable `data/public_snapshots/nfl_week10_bovada_sunday_2026-11-15T1256Z.csv`; also appended to `data/bovada_lines.csv`. Original Thursday screenshot `nfl_week10_bovada_initial_2026-11-12.csv` preserved.
- Official NFL.com Nov14 4:48p ET report `data/public_snapshots/nfl_week10_sunday_official_injury_designations_2026-11-15.csv`: **169 named OUT/QUESTIONABLE/DOUBTFUL cases for all 26 Sunday+Monday teams**. Precisely 164 matched to historical GSIS source, five UNMATCHED rather than guessed. At least 12 meaningful statuses shifted to OUT versus the previous public nflverse snapshot (e.g. KC RB Kenneth Walker III). `scripts/publish_week10_sunday_pregame.py` overlays explicit status fields on a new historical input snapshot; no paid APIs.
- 13 games × Baseline/Injury = **26 new pregame score rows at Sunday 7:04 a.m. CT** `data/public_snapshots/nfl_week10_sunday_pregame_2026-11-15.csv` and matching manifest; workflow **#43717045343 succeeded**. Thu initial first-public 28 rows, original Week8 and Week9 published scores/grades untouched. Full user odds carried on score rows; QB labels still provisional except Cardinals Carson Beck, Seahawks Drew Lock, and coach-expected Ravens Jacoby Brissett.
- **Patriots @ Lions at 8:30 a.m. CT**: subsequently received both teams' exact game-day inactives and explicit active sources, recorded 12 inactive and 8 actively confirmed in `data/public_snapshots/nfl_week10_ne_det_official_inactives_2026-11-15.csv`. NE A.J. Brown/Rhamondre Stevenson and DET Amon-Ra St. Brown/Sione Vaki are confirmed ACTIVE. Separate **7:18 a.m. CT** Injury-only score from `scripts/publish_week10_ne_det_inactives.py` via **#43718261794 SUCCESS**, stored `data/public_snapshots/nfl_week10_ne_det_inactives_adjusted_2026-11-15.csv`: **NE 20.0, DET 27.2, total 47.2**; prior 7:04a **NE 17.2, DET 26.3 total43.5**. This is not an automatic betting recommendation; ATS edge vs DET -2.5 unusually large.
- Both static URLs https://tedgytrends-bit.github.io/sports-betting-model/ and shareable thumbnail https://tedgytrends-bit.github.io/sports-betting-model/week10.html show **latest Sunday scores, Bovada prices, final NFL injury designations**; NE–DET also official day-of game inactive list and more recent 7:18 Injury score. Streamlit `pages/Week_10_Projection_Board.py` updated accordingly; release formats/chronology validated in source and CI.
- **CRUCIAL:** DO NOT retroactively change first-public Thu 14-game projections, its 13-game Sun 7:04 version, or the 7:18 NE version. All newer views should be overlays that cite independent frozen version timestamps. Questionable/doubtful ≠ game-day OUT. Other 12 matchups await exact later game-day inactive lists; do not imply these are known at 7:18 a.m. CT.


## 16. November 15, 2026 — critical Miami QB invalid IR and roster gate

- **Priority correction**: user correctly identified that Sunday Week 10 initial Injury model still projected **Malik Willis at MIA@IND**, even though the Dolphins placed him on IR **Nov10**. Official Miami Nov14 game preview explicitly announces **Kyle McCord** as the Nov15 starting QB; GSIS **00-0040014**, zero NFL regular-season dropbacks. Miami IR Willis added to `data/qb_starters/2026_week10_watchlist.csv`, McCord official team attestation added to `data/qb_starters/2026_week10_confirmed.csv`.
- **Actual one-game reforecast succeeded**: workflow **#43728053483**; immutable correction `data/public_snapshots/nfl_week10_mia_ind_mccord_corrected_2026-11-15.csv` at **2026-11-15T15:07:30Z** before kickoff. Prior incorrectly Willis-based **MIA 21.6 IND22.3 total43.8**; correct-name McCord-based **MIA22.9 IND20.9 total43.8**. This is **NOT trustworthy betting value** because the replacement QB EPA estimate has zero NFL dropbacks and is marked `insufficient_data`. **PASS** for MIA ATS/totals wagering, despite apparent ATS gap. Do not pretend the original erroneous prediction was valid or silently rewrite its timestamped record.
- **QB universe review**: `data/public_snapshots/nfl_week10_qb_identity_crosscheck_2026-11-15.csv` checks all 26 Sunday/Monday starters against contemporary roster/depth-chart reference: before fix 25/26, after fix 26/26 match; only 5 have individually corroborating primary team-specific starter announcements, one BAL Brissett coach-expected, 20 secondary-index-corroborated unconfirmed. NFLverse current Week10 roster status also has all **26 corrected projected QBs `ACT`** for exact team/GSIS. This is eligibility, NOT proof of actual day-of starter.
- **Critical systematic blind spot**: current NFL game *practice injury reports* omit some existing IR/reserve players. Separate free NFLverse `roster_2026.csv` research job **#43729580593** saved `data/week10_review/week10_roster_reserve_secondary_audit_20261115.json`: in latest Week10 status, 258 `RES` roster player rows across 26 teams, 236 not named OUT in the week's final practice report. This does **NOT** mean 236 injured relevant starters; reserve covers multiple statuses and historical roles. MIA Willis and Zach Sieler and De'Von Achane are among roster RES; McCord is ACT.
- **Reusable prevention**: new `research/validate_live_qb_roster.py` gates selected QB name+GSIS+team+current-week `ACT` against latest NFLverse season roster (no paid credits); refuses RES, missing/stale, wrong identity. `tests/test_qb_live_roster.py` plus Week10 regression for original Willis error. `scripts/capture_qb_aware_injury.py` now runs roster gate, and sets `release_ready=false` when current-week roster unavailable/stale, fails hard when current roster explicitly contradicts expected QB. Still requires game-specific starter verification before official release. Site Week10 homepage, shareable `docs/week10.html`, and Streamlit show source-corrected MIAMI and **uncalibrated/PASS**, not a confident pick. GitHub Pages and smoke tests passed.
- **Source & code details**: `docs/week10_sunday_pregame_20261115.md` end sections contain URLs, model effects, 26-QB and full roster audit. Future work: timestamped role-aware reserve/IR feature model with honest historical evaluation; no immediate coefficient or historical model update based on these diagnostics. Keep all 2026 W8–W10 published archives immutable.


## 17. November 16, 2026 — automated public Results after NFL game days

**Canonical implementation specification:** `docs/results_automation_20261116.md`.

- User correctly observed static site Model Results still centered on Week8 despite Week9 audit. **Fixed both static site layouts and Streamlit**. External read-only `docs/public-results.js` renders four cumulative model ATS/total cards, weekly W-L-P + theoretical -110 ROI, and every published game with score/market/grade, week and Thursday/Sunday/Monday filters. `docs/index.html` and `docs/week10.html` use the same new files, with **`?view=results` deep link**; `pages/Results.py` displays identical model data. Direct link: https://tedgytrends-bit.github.io/sports-betting-model/?view=results .
- New `scripts/refresh_public_nfl_results.py`: imports original 14 published Week8 graded games, official audited 15 Week9 game grades (injury) and Week9 Baseline research **clearly excluded from Baseline cumulative**, and dynamically discovers Week10+ exact timestamped public model score versions. For each game/model selects latest published score BEFORE kickoff and latest screenshot Bovada quote BEFORE kickoff. Week10 late corrections NE/DET official inactives and Miami McCord are **part of the appropriately identified pregame model vintages**; Miami rookie-QB adjustment remains flagged `NOT CALIBRATED`, not a verified bet.
- Score source **free ESPN public NFL scoreboard explicitly marked FINAL**, strict team/date/kickoff matching; never count partial scores. One frozen game/model grade; if a previously final game changes score, market, grading, or model vintage, script **fails closed**, requires manual audit. Missing ESPN final is displayed **PENDING**. No paid NFLMeta/EndzoneAPI credits. Version and source provenance retained per game.
- Repo auto grader `.github/workflows/update-public-nfl-results.yml` runs twice late Thu/Sun/Mon US Central game nights (UTC Fri/Mon/Tue 05:40 and 07:40, DST/CST coverage), plus a Sunday afternoon check. New weekly freeze commits also trigger grader. Re-running without new finals is idempotent; confirmed **GitHub Actions #43885206215 NO_CHANGE success, no commit**. Initial **#43882463446 SUCCESS** graded 42 completed games (14 W8,15 W9,13 W10) and one pending LAC@BAL 2026 Nov16 MNF.
- Committed machine-readable **`data/public_results/nfl_2026_graded_games.csv`** 86 model rows (43 unique games), **`nfl_2026_results_summary.csv`**, **`nfl_2026_verified_final_scores.csv`**, **`nfl_2026_results_metadata.json`**. Public GH site reads via RAW GitHub with 1-minute cache bust; no rebuild required when results CSV updates. Streamlit reads same repo files.
- Status **Nov16 morning before MNF**: Week8 Baseline ATS **9–5**, totals **7–7**, Injury ATS **7–7**, totals **5–8 +1 No lean**. Week9 Baseline research ATS **5–9–1**, totals **8–7**; Injury official ATS **3–11–1**, totals **9–6**. Week10 13/14 finals Baseline ATS **3–10**, totals **7–6**; Injury ATS **6–7**, totals **9–4**. **PUBLIC_PUBLISHED cumulative** Baseline ATS **12–15**, totals **14–13** (excludes retrospective Week9 Baseline); Injury ATS **16–25–1**, totals **23–18 +1 No lean**.
- Tests `tests/test_public_nfl_results.py` prove Week8/9 audit math, Week10 market/projection version timestamps and strict final-grade immutability. `tests/public-results-dom-smoke.cjs` renders real CSVs in a mocked DOM, checks 43 matches, cumulative summaries, research exclusion and filters. `.github/workflows/smoke-test-public-site.yml` validates both static sites, external JS syntax and Streamlit Results UI. Latest smoke test **#43885255650 SUCCESS**, Pages deploy **#43885255776 SUCCESS**; direct Results route staged. No new user action is required to grade Monday's game when it goes FINAL and scheduled workflow runs.
- **IMPORTANT:** Results are *model directional leans*, not user wager ledger, and shown ROI uses hypothetical flat -110 prices (not realized returns). For future Week11 and beyond, need capture published Baseline/Injury scores with exact `published_at_utc`, `publication_status`, `kickoff_utc`, and archived Bovada lines before kickoff; grader auto-discovers `data/public_snapshots/nfl_weekNN_*.csv` and updates after FINAL status. Does not invent or generate new forecasts.


## 18. November 16 — simplify Results to Injury-only overall and explain exact-market game

- User screenshot revealed confusing Results section: four cards labeled Baseline/Injury without **Overall Record** context, and an awkward Week8 Injury totals `23–18 · 1 no lean` caption. User wants Baseline off this public Results page and a real outcome for every final game.
- **Changes deployed to static site** `docs/index.html`, `docs/week10.html`, `docs/public-results.js`; **Streamlit** `pages/Results.py`: public page heading **Overall model record**, **two** prominent mobile-friendly cards **OVERALL INJURY MODEL · ATS RECORD** and **OVERALL INJURY MODEL · TOTALS RECORD**, all weekly records and every game filtered to Injury only; Baseline retained in backend research and existing projection view but **not in Results cards, weekly table or game list**. The site had already been correctly updating automated results in `data/public_results`. No regrade or production forecast changes were made.
- **Zero-edge/No bet historical truth**: original 2026 Week8 `IND@JAX` Injury projected total **46.0**, exact Bovada market **46.0**, saved `injury_total_pick=No edge`, `injury_total_result=No bet`. Game ended IND7 @ JAX42 = **49 total**, so **actual market Over 46 won**. The per-game result now shows **No pregame pick · Market Over won**, plus final 49 total and actual Over outcome; no retroactive model Win is fabricated. Cumulative official total record remains **23–18**, with one completed game correctly excluded from directional W/L but presented with a real score and actual market result. The card displays a small note about one exact-market no-pick; no cumbersome `· 1 no lean` in the record itself.
- **As of Mon Nov16 before MNF**: public Injury ATS **16–25–1**, Injury totals **23–18**, 42 completed/1 pending (MNF), W8/W9/W10 all visible with dates/filters. No published frozen archival model, line, or score changed; no paid injury/odds APIs.
- Website redeploy **GitHub Pages #43891923812 SUCCESS**; latest complete static+Streamlit+DOM **smoke test #43892348942 SUCCESS** after replacing obsolete assertions with exact two-card Injury-only/IND@JAX market outcome expectations. Direct results link: https://tedgytrends-bit.github.io/sports-betting-model/?view=results . Site Results-only change; baseline may still be present on user-requested projection/model research pages.


## 19. November 16 — complete directional Injury totals policy and true push settlement

- User requested a visible directional pick/result for **every game** on public Results, preferring the "Injury" brand and crediting the Week8 IND@JAX model a win. An independently pre-existing published **Baseline total 46.9** versus Bovada **46** supports **Over 46** as a fallback only under a **retrospectively adopted Nov16 rule**. The original published Injury projected **46** (no original selection). The game really finished **IND7, JAX42, total49**; Over46 therefore **WON**, but this is *not* a genuinely prospectively selected Injury pick. Retrospective provenance **MUST remain labeled** and original unmodified Injury total remains `23–18 +1 No lean`.
- New separate derived full-directional series `data/public_results/nfl_2026_full_directional_games.csv`, `nfl_2026_full_directional_summary.csv`, `nfl_2026_full_directional_policy.json`: **24–18 Injury-derived totals through Sun Week10**, one explicit `POSTHOC_POLICY_USING_PREEXISTING_PREGAME_BASELINE` fallback for Week8 IND@JAX; official ATS **16–25–1**. `scripts/build_full_directional_results.py` automatically runs after immutable source grading in `.github/workflows/update-public-nfl-results.yml`. It assigns no other retrospective direction without independent pregame evidence, and never rewrites originals.
- User follow-up clarified **a Push occurs ONLY if the actual final total equals the market/selected total**, e.g., a 46-point game against Over/Under46. Merely having a model projection of 46 and market at 46 is NOT a push. Week8 actual49 means Over46 Win. `grade()` in derived generator implements this correctly; `tests/test_full_directional_results.py` asserts both Over49=Win and Over46=Push.
- Static `docs/public-results.js` and `docs/index.html`, `docs/week10.html` now display **24–18** in Overall Injury Totals and **Over46 — Win** for IND@JAX with visible *retrospective tiebreaker* explanation; Streamlit `pages/Results.py` now consumes the same derived series and shows identical labeled grade. Browser regression `tests/public-results-dom-smoke.cjs` and `.github/workflows/smoke-test-public-site.yml` now load/validate BOTH frozen original grades and separate derived totals to prevent silent revision. Smoke run **#43900190090 PASSED**.
- This revised derived record should not be described as the original fully prospective verified Injury performance; independent original-grade record still preserved for research and credibility. Future game exact-market ties only receive a prospectively defined fallback when a pregame source exists. No paid NFLMeta/EndzoneAPI credits.


## 20. November 16, 2026 — rebuild botched Results UI, fix mobile cache and self-host results

- User reported Results tab completely botched after removing explanatory notice. **Likely root cause:** previous HTML removed `id="results-notice"` but existing Safari browser could retain cached old `public-results.js`, whose renderer attempted to write to the missing element, leaving Results unrendered. Old site also displayed a 7-column horizontally scrolling results table on mobile with excessive repeated narrative.
- **Rebuilt the actual public UI** in both `docs/index.html` and `docs/week10.html`: clean heading, two overall Injury ATS and totals cards, narrow week-by-week rows, and stacked game result cards with matchup, score, Bovada line, ATS pick/result and totals pick/result; week/day filters; default latest Week10 with all-week option. No redundant giant notice, no public Baseline research cards, no mobile horizontal-scrolling 7-column table. The Week8 retrospective Over 46 tie-break details are in a small expandable **Record methodology** disclosure and small per-game provenance note; original prospective historical Injury no-pick still unchanged.
- **Browser cache fix**: HTML now uses `<script src="./public-results.js?v=20261116-mobile-results-v3"></script>` on BOTH routes, so old mobile cached JS cannot mismatch new DOM. `loadCSV` for results first reads same-origin `./data/public_results/*.csv` from deployed Pages, falling back to GitHub RAW if needed. `.github/workflows/deploy-tedgy-trends.yml` now bundles 4 public results CSVs plus metadata with the docs Pages build and triggers deployment on `data/public_results/**` changes after every game-day grade. No paid APIs or model changes.
- `tests/public-results-dom-smoke.cjs` updated for responsive game-card DOM. **NEW actual Chromium mobile and desktop end-to-end browser test** in `tests/results_browser_smoke.cjs` and `.github/workflows/smoke-results-browser.yml`. Real Playwright job **#43905086941 SUCCESS** tested all 4 combinations (iPhone 390px and desktop 1365px, both main and Week10 URLs), verified no JS errors, no horizontal overflow (390px viewport = 390px document), correct cards **Injury ATS 16–25–1 / Totals 24–18**, 14 current Week10 cards, complete Week8/9 filtering, Week8 Over46 win with disclosed provenance, and all 43 games via All weeks. Screenshots attached to GitHub Actions job.
- Public Pages deployment for last HTML/JS change **#43904438609 SUCCESS**. Future changes to DOM and JS should both bump version query to avoid cached JS bug. Results statuses continue to be generated by existing scheduled source-audited grader, not browser invented. Direct link: https://tedgytrends-bit.github.io/sports-betting-model/?view=results .


## 21. November 16, 2026 — complete public-site UX audit and future-week routing

- Canonical site review & all decisions: `docs/site_audit_20261116.md` (read first before changing site again). User requested concise, seamless, professional public flow and asked why Week9 appears in top navigation.
- **Public navigation changed to Projections / Results / About.** Removed top-level Week9 from both `docs/index.html` and shareable `docs/week10.html`; past weeks are tucked under expandable Previous weeks and archived projections. Preserved `docs/week09.html` as a frozen 15-game historical projection board, now clearly labeled archive, and replaced its stale Results / Method tabs with real links to current Results and About. Historical source files, original records, Twitter card/OG thumbnail unchanged.
- **Projections simplified**: one-line header, 3 KPI cards (games, >=3-point spread/total gaps), active Injury/Baseline switch, accurate label for latest pregame snapshot, short status strip, search and filters, results-aware cards. Final scores and official Injury ATS/total grades appear separately from forecast, preserving original prediction and timestamps. Long practice injury reports are collapsed; confirmed actives/inactives priority fixed; per-game detail no longer pretends Giants/Commanders injury source applies to every matchup.
- **Results kept user-approved Injury-only** ATS 16–25–1 / adjusted totals 24–18 through W10 Sunday; week/day filters, grouped game records and full score, with small explicitly retrospective IND@JAX Baseline Over tiebreaker note rather than huge banner. No data grades changed in this UX audit, original 23–18 plus 1 no-pick remains immutable.
- **About shortened** to four clear blocks plus expandable detailed historical source and methodology disclosure; no raw debug log dumping at footer. Links `?view=results` and `?view=method` now open correct tabs directly and nav changes URL.
- **Future-week auto-switch** in homepage: after real published Week11+ results-grader rows exist with both model sources, pre-kickoff timestamps, valid scores, Bovada lines, automatically show newest week. Historical Week11+ can be accessed at `?week=11` after published; special `week10.html` and `week09.html` are preserved. Generic future-week game drawer has no Week10-specific injury assumptions and clearly labels uncertain QB data. Site does not fabricate Week11 projections or query paid APIs. Do NOT change `docs/week10.html` to generic as it is a public archive.
- New broad real browser e2e test `tests/results_browser_smoke.cjs` checks every active tab, model toggle, search, week/day filters, matchup drawer, mobile horizontal overflow, historic Week9 archive and future-week with synthetic testing-only score sources; workflow `.github/workflows/smoke-results-browser.yml`. Static smoke `43911492912` was SUCCESS on previous revision. Pages deploy for latest HTML `43911493028` was SUCCESS. The complete 390px iPhone + 1365px desktop browser test **#43912173657 SUCCEEDED** on both main and Week10 shareable pages, plus preserved Week9 archive and synthetic future Week11 model-pair transition (no real Week11 forecast created). Latest HTML Pages deployment **#43912477214 SUCCEEDED**.
