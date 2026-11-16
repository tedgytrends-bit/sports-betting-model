# Tedgy Trends public NFL Results — automatic game-day grading

**Implemented November 16, 2026.** The previously stale Week8-only results tab was replaced with a live, cumulative, source-verified record on BOTH:
- [GitHub Pages](https://tedgytrends-bit.github.io/sports-betting-model/?view=results)
- [Week10 shareable URL](https://tedgytrends-bit.github.io/sports-betting-model/week10.html?view=results)
- [Streamlit model results](https://sports-betting-model-sno3lwyvn2fzg9cyrfaqs3.streamlit.app/results)

## Public source of truth

- `data/public_results/nfl_2026_graded_games.csv`: **one model/game row, exactly two model rows per match**. Includes saved market, predicted scores, observed score if FINAL, ATS and totals directional grades, model snapshot path/time, and source link for final score.
- `data/public_results/nfl_2026_results_summary.csv`: weekly ATS/totals/flat-standardized ROI per model plus properly scoped cumulative PUBLIC_PUBLISHED results.
- `data/public_results/nfl_2026_verified_final_scores.csv`: explicit ESPN public scoreboard FINALs, first-verified score pinned to avoid silent future overwrites.
- `data/public_results/nfl_2026_results_metadata.json`: source scope, update time, completion counts, grading/preservation policy.
- **Existing Week8 original audit** remains in `data/four_model_week08/week08_four_model_comparison.csv`. Its scores are rounded and an injury total marked `No bet` is carried as an ungraded no-lean, not a loss. No Week8 results rewritten.
- **Week9 official audited Injury** stays `data/week09_review/week09_full_ats_totals_grade.csv`: 15 final matchups. The Week9 Baseline numbers are retrospective research and **excluded from public Baseline cumulative record**, but shown as separately labeled weekly comparator.
- **Week10** uses most recently timestamped published Baseline/Injury forecast before EACH kickoff and latest archived user Bovada quote before kickoff. Preserves older archived forecasts rather than overwriting them. The source-corrected Miami Injury forecast (McCord rookie first start) remains labeled **QB uncalibrated**; directional grades are **not actual bets** or a confidence-rated recommendation.

## Automatic workflow

`scripts/refresh_public_nfl_results.py` and `.github/workflows/update-public-nfl-results.yml`.

- GitHub Actions **scheduled twice after Thursday, Sunday and Monday game nights**, on UTC Fri/Mon/Tue at **05:40 and 07:40 UTC**, covering US Central DST/CST and overtime or delayed scoreboard finals. An optional Sunday afternoon check at 23:45 UTC captures already completed early games.
- A run **only grades games explicitly marked FINAL by ESPN's public scoreboard**. If the source has not published a final, the game stays `PENDING`; no score is inferred from the spread or a partial live score.
- For future weeks, a new `data/public_snapshots/nfl_weekNN_*.csv` released with valid `published_at_utc`, `publication_status`, game ID, exact pregame kickoff, Baseline/Injury scores and an archived Bovada line is discovered automatically. No editing the Results site by hand after each game day.
- On all runs, model publication and Bovada quote timestamps are validated to precede kickoff; team identity matches checked. Previously graded final scores, market, result or model-vintage **cannot be retroactively altered**. A conflict aborts grading and requires an explicit audit.
- **No-op repeat verified:** GitHub Actions [run #43885206215](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/43885206215) reported `NO_CHANGE`, 42 games already final and 1 pending, with **no commit**. Initial [successful backfill and grading run #43882463446](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/43882463446).
- New rows are committed only when a newly completed game or new public forecast arrives. GitHub Pages and Streamlit then load the same source files, avoiding separate manual bookkeeping.
- No NFLMeta, EndzoneAPI or paid third-party API credits used for grading.
- GitHub Pages results are in `docs/public-results.js` (read-only display) and both `docs/index.html` and `docs/week10.html`; Streamlit in `pages/Results.py`. Website smoke test `tests/public-results-dom-smoke.cjs` executes the full model cards, weekly summaries, week/day filters and expected pending/finals using real CSV inputs. `tests/test_public_nfl_results.py` tests grading math, immutable records, Week8/9 archived grades, ESPN FINAL handling and Week10 pregame score selection.

## Backfill status as of Monday November 16, 2026, ~8:07 a.m. Central

**42 of 43 known publicly tracked games FINAL; Week10 Monday LAC@BAL still PENDING.** Model figures below are *directional-model ATS and totals grades* against user-provided Bovada lines, not actual money risked.

| Week | Baseline ATS | Baseline Totals | Injury ATS | Injury Totals | Completed |
|---|---|---|---|---|---|
| Week8 | 9–5 | 7–7 | 7–7 | 5–8 (one no lean) | 14/14 |
| Week9 | 5–9–1 *research only* | 8–7 *research only* | 3–11–1 | 9–6 | 15/15 |
| Week10 through Sun Nov15 | 3–10 | 7–6 | 6–7 | 9–4 | 13/14 |

**Cumulative PUBLIC_PUBLISHED:** Baseline ATS **12–15**, totals **14–13** (Week8 and Week10 only). Injury ATS **16–25–1**, totals **23–18** (one zero-edge no lean) across Weeks8–10. The Week10 totals may change after MNF and the website will pick that up automatically.

Illustrative flat -110 ROI on model directional leans is a hypothetical benchmark only, not a verified sportsbook return or user's personal wager ledger.

## Results UI

Main site has top navigation **Model Results**. New direct `?view=results` deep link opens it. Four cumulative performance cards, per-week rows and game-by-game score/line/ATS and total grades appear, with filters for **week and game day**. Last update time and partial Week10 count are explicit. Do not replace the full 14-game Week8 historical reference with a 12-game subset.

**Maintenance:** Ensure publicly released future forecasts use the established timestamped CSV schema with both Baseline and Injury rows and Bovada prices saved pregame. Scheduled runs do not and should not create new predictions; they grade published ones after final scores. If the scoreboard provider is inaccessible, workflow fails without fabricating grades; older public results remain displayed.
