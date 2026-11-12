# Tedgy Trends NFL Week 10 — public initial board and Thursday Bovada snapshot

**Thursday November 12, 2026. One immutable initial public release before the 8:15 pm ET / 7:15 pm CT TNF kickoff.** The public board is now Week 10 and archived Week 9 separately.

## Source and release policy

- First public model file: `data/public_snapshots/nfl_week10_initial_projections_2026-11-12.csv`
- First model publication: **2026-11-12T13:29:01Z** (7:29 am CT). **28 rows = 14 games × Baseline/Injury**. Captured from public nflverse schedule, play-by-play and injury feeds using the existing 10-game Ridge model and experimental capped QB EPA adjustment. This is *initial* pregame, not final injury/inactives.
- Bovada screenshot snapshot: `data/public_snapshots/nfl_week10_bovada_initial_2026-11-12.csv`, all **14** games including both ATS side prices and total side prices. Screenshots approximately **7:20–7:21 am CT** on November 12. `data/bovada_lines.csv` append-only; upcoming Saturday/Sunday quotes must be appended, not overwrite this snapshot.
- Current site: https://tedgytrends-bit.github.io/sports-betting-model/ ; Week 9 archive https://tedgytrends-bit.github.io/sports-betting-model/week09.html . Streamlit home routes to `pages/Week_10_Projection_Board.py`, Week9 retained at `week-9-projections`.
- Publication workflow run [#43227603908](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/43227603908) passed, including 14-game crosschecks, start times, before-kickoff publication, nonmissing both public model scores and matching Bovada data.
- Website Week10 JS / Streamlit smoke test run [#43229629629](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/43229629629) passed. Week9 original board and historical results kept immutable.

**Preliminary QB caveat:** Initial first-public Injury data had 27 schedule-provisional QB entries and only BAL Jacoby Brissett labeled *coach expected but not game-day confirmed*. As of Thursday morning these source fields were not independent verification. `release_ready_final_injury=false`. This status does not invalidate the prospective timestamp, but means official final Injury treatment should wait for source validation.

## Corrected independent Sunday QB-source research preview

After freezing the original initial public record, official team reporting definitively contradicted two upcoming schedule QB fields:
- **ARI:** Arizona Cardinals officially announced on Nov10 and re-confirmed Nov11 that rookie **Carson Beck** (nflverse GSIS `00-0041561`) will make his first NFL start Sunday Nov15 against the Rams. Gardner Minshew was placed on IR (season-ending arm injury). Primary sources: https://www.azcardinals.com/news/cardinals-place-gardner-minshew-michael-wilson-on-ir and https://www.azcardinals.com/news/for-starters-carson-beck-ready-to-play-first-game-against-rams .
- **SEA:** Seahawks coach Mike Macdonald and the official Seahawks.com Nov11 article confirm **Drew Lock** (GSIS `00-0035704`) will play at the Raiders, Sam Darnold out with quad/rib injuries. Primary sources: https://www.seahawks.com/news/seahawks-plan-for-drew-lock-this-week-some-positive-injury-updates-more-from-mike-macdonald and https://www.seahawks.com/news/mike-macdonald-on-seattle-sports-710am-drew-lock-expected-to-start-again-in-week-10 .

The assistant inspected the official articles and stored exact game-specific source IDs, URLs, publication dates and actual check timestamp in `data/qb_starters/2026_week10_confirmed.csv`. `data/qb_starters/2026_week10_watchlist.csv` explicitly marks Minshew on IR and Darnold out, enforcing no wrong starter when running research.

Corrected research script `scripts/capture_week10_qb_corrections.py` and action `capture-week10-qb-corrections.yml` [run #43231259929](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/43231259929) **passed**, creating two separate independently timestamped research rows in:
- `data/public_snapshots/nfl_week10_qb_corrected_2026-11-12.csv`
- `data/public_snapshots/nfl_week10_qb_corrected_2026-11-12_manifest.json`
- Publication **2026-11-12T13:51:47Z** (7:51 am CT), before *both* Sunday Nov15 games.
- **Updated Rams@Cardinals** = LA 21.0 – ARI 19.1, total 40.1; earlier initial LA 22.2 – ARI 17.9; only changed QB-informed margin by +2.36 ARI points. QB Carson Beck has **zero historical NFL regular-season dropbacks** in model (GSIS `00-0041561`), and the model estimates a **+1.75-point QB margin component** based on shrinkage toward league prior; that value is **not calibrated** for rookies. Strong hypothetical ARI +9.5 model gap is NOT a validated edge.
- **Updated Seahawks@Raiders** = SEA 23.3 – LV 21.4, total 44.7; earlier SEA 23.9 – LV 20.8; Drew Lock has 476 prior NFL QB model dropbacks. This is a pregame research correction, not a final inactive-based release.
- Original 28-row initial first-public file and Bovada initial odds remain **unchanged**.
- Website and Streamlit code use separate optional corrective preview only for these **two Injury games**; all other model rows remain the first-public version. The corrected cards are labeled `QB-SOURCE UPDATE` and original model files remain linked. This dual view does **not** silently alter the frozen prospective record, and still requires game-day injury/inactives review.

## Thursday Nov12 WAS@NYG

- Bovada screenshot line: **NYG -2 (home price -108, WAS +2 -112), total 41 (Over -108 / Under -112)**.
- Injury: WAS 23.2 – NYG 24.9; projected total **48.1**; ATS *WAS +2* difference just **0.3 pt**; total *Over 41* difference **+7.1 pt**.
- Baseline: WAS 21.2 – NYG 24.9, total **46.1**, ATS NYG -2 margin roughly 1.7 points and Over41 difference +5.1. Neither ATS margin merits a strong recommendation.
- **Major weather confounder**: MetLife Stadium East Rutherford has Thursday evening rainfall expected; National Weather Service issued Wednesday Nov11 Thursday Night rain 80% and N wind 10–13 mph with gusts up to 23 mph (https://forecast.weather.gov/MapClick.php?FcstType=text&TextType=1&lat=40.81&lg=english&lon=-74.07&unit=0). The live Ridge scoring model has **no explicit game-level rain/wind adjustment**. Do **not** translate +7-point total projection gap into an automatic wager. Recheck actual kickoff radar/wind, QB-active lists and the latest Bovada market. Wednesday final team injury reports have both QB Daniels and McCarthy practicing fully and neither with game injury designation; that's still not the exact inactive list.
- Distinguish chronological forecasts from real execution: these are *model leans*, not guaranteed odds-positive expected value and not a pick-of-the-day recommendation.

## Week 9 grade included on public results page

Source `data/week09_review/week09_full_summary.json` and compact `data/public_snapshots/nfl_week09_results_summary_2026-11-10.csv`:
- **Official Week9 Injury** 3–11–1 ATS, 9–6 totals, all 15 games.
- **Baseline Week9 research only** 5–9–1 ATS, 8–7 totals, all 15.
- Week8 all 14 games remain the historical published record. Do not combine retrospective Baseline reconstruction with official Injury ledger.

## Before Week10 Sunday updates

1. Preserve first model file and first market screenshot archive. Append new Bovada spreads, prices and totals with screenshot capture time and repeat only changed matchups as necessary; verify all 14 games align with correct home/away sign and canonical team aliases.
2. Capture a **new complete, prospective Sunday pregame Injury and Baseline release** with exact QB starter source provenance, signed kickoff time, injury coverage and current prices, BEFORE each kickoff; retain the Thursday version and revised QB research file independently.
3. Evaluate Thursday separately once final and do not adjust its published model based on its score. Keep completed TNF on the full Week10 board.
4. Week10 results graded prospectively from the immutable pregame model and price vintage selected before the events. No retrospective rewriting or model selection after seeing results. NFLMeta and EndzoneAPI paid credits were **not** used for any of this.
