# Week 10 — Sunday, November 15, 2026 pregame operational handoff

**All model and user-market snapshots are immutable; original Week 8, Week 9 and Thursday Week 10 are untouched.** No NFLMeta/EndzoneAPI paid credits were used.

## Market prices received from user

User supplied three Bovada screenshots at **6:56 a.m. CT Sunday November 15**, 13 remaining matchups. All ATS prices and Over/Under prices preserved in `data/public_snapshots/nfl_week10_bovada_sunday_2026-11-15T1256Z.csv` and appended without overwriting older rows to `data/bovada_lines.csv`. Screenshot time is **approximate phone time, not the sportsbook's quote issue time**.

New England at Detroit: DET -2.5; total 51. BUF@NYJ: BUF -7.5; total 51. CAR@NO: NO -1; total 49. HOU@CLE: HOU -4; total 41. JAX@TEN: JAX -11; total 46. KC@ATL: KC -3.5; total 47.5. MIA@IND: IND -4.5; total 37.5. MIN@GB: GB -2.5; total 42. LA@ARI: LA -10; total 38. SEA@LV: SEA -6.5; total 40.5. SF@DAL: SF -3.5; total 55.5. PIT@CIN: CIN -3.5; total 49. LAC@BAL: BAL -4.5; total 39. Complete sides/prices in CSV.

## Official NFL Week 10 final injury designations

Reference NFL.com final injury report last updated Nov 14, 2026, 4:48 p.m. Eastern:
https://amp.nfl.com/news/nfl-week-10-injury-report-2026-season

Saved `data/public_snapshots/nfl_week10_sunday_official_injury_designations_2026-11-15.csv`: **169 named designations across all 26 Sunday/Monday teams** (80 OUT, 84 QUESTIONABLE, 5 DOUBTFUL), organized by game and team. OUT means OUT. DOUBTFUL/QUESTIONABLE are not game-day inactives.

Reconciled **164 of 169** named people with historical nflverse player GSIS records in `data/injury_snapshots/injuries_2026_week_10_20261115T130438Z.csv`; five could not be safely matched and were NOT assigned fake identities (HOU Braden Smith and Jake Hummel; LA Kamren Curl; ARI Zach Carter; PIT Pat Freiermuth). Twelve explicit status changes, including KC Kenneth Walker III, HOU David Montgomery, CAR Brady Christensen/Jonathon Brooks/Mike Jackson, were newly OUT versus earlier nflverse.

Watch important final OUTs: GB RB Josh Jacobs and EDGE Micah Parsons; SEA QB Sam Darnold; MIN QB Kyler Murray; KC RB Kenneth Walker III. **Most quarterbacks are still only schedule-provisional**. ARI Carson Beck and SEA Drew Lock verified from contemporaneous primary team reports, BAL Jacoby Brissett coach-expected. Do not treat identified QB value/rookie EPA as calibrated betting edges.

## First Sunday model release before kickoff

Scripts/workflow:
- `scripts/publish_week10_sunday_pregame.py`
- `.github/workflows/publish-week10-sunday-pregame.yml` **Actions #43717045343 SUCCESS**.
- **Immutable published 2026-11-15T13:04:38Z** (7:04 a.m. Central), 13 matchups, both Baseline and Injury, 26 rows `data/public_snapshots/nfl_week10_sunday_pregame_2026-11-15.csv` with 13 screenshot line/total values and four actual side odds included in each row; manifest in corresponding .json; matched-versus-unmatched injury audit in `data/public_snapshots/nfl_week10_sunday_injury_overlay_audit_2026-11-15.csv`.

13 refreshed Injury scores (away–home; total):
NE@DET 17.2–26.3 (43.5); BUF@NYJ 25.8–21.2 (47.0); CAR@NO 21.5–24.8 (46.3); HOU@CLE 18.8–23.2 (42.1); JAX@TEN 24.6–22.9 (47.5); KC@ATL 21.2–21.8 (43.0); MIA@IND 21.6–22.3 (43.8); MIN@GB 19.6–20.7 (40.3); LA@ARI 21.7–19.3 (41.1); SEA@LV 22.2–22.9 (45.1); SF@DAL 24.1–20.0 (44.2); PIT@CIN 22.9–24.4 (47.3); LAC@BAL 16.9–23.3 (40.2).

This is **pre-inactives** for all games, with actual official *final injury designations*. It never rewrites the Thursday model archive or its historic site record. Thursday first-public 28-row file remains `data/public_snapshots/nfl_week10_initial_projections_2026-11-12.csv`; first QB source correction stays `data/public_snapshots/nfl_week10_qb_corrected_2026-11-12.csv`; Friday/Thursday game results not retroactively rescored.

## Separately frozen NE–DET exact game-day inactives

Primary team reports:
- https://www.patriots.com/news/week-10-inactives-patriots-vs-lions
- https://www.detroitlions.com/news/inactives-lions-vs-patriots-stbrown-vaki-cisco
- https://www.patriots.com/news/inactives-analysis-patriots-wr-a-j-brown-rb-rhamondre-stevenson-officially-active-for-sunday-s-game-vs-lions-in-munich

`data/public_snapshots/nfl_week10_ne_det_official_inactives_2026-11-15.csv`: 12 listed game-day inactive names (six per team), eight **explicitly confirmed ACTIVE** names including A.J. Brown, Rhamondre Stevenson, Amon-Ra St. Brown, and Sione Vaki. Source checked ~7:13 a.m. CST, after official inactive lists were published. Seven of the 20 individuals (mainly healthy scratches and one active) could not be matched to nflverse **injury report history**; the source list is still separately displayed and never fabricated within the model.

`scripts/publish_week10_ne_det_inactives.py`, `.github/workflows/publish-week10-ne-det-inactives.yml`, **Actions #43718261794 SUCCESS**. Publishes **one NE@DET injury-only subsequent score row** at **2026-11-15T13:18:33Z = 7:18 a.m. CST** before 8:30 a.m. kickoff, `data/public_snapshots/nfl_week10_ne_det_inactives_adjusted_2026-11-15.csv` and .json; updated input snapshot `data/injury_snapshots/injuries_2026_week_10_20261115T131833Z.csv` (other Sunday game scores NOT regenerated). **NE 20.0–DET 27.2, projected total 47.2** versus earlier Sunday 7:04 release **NE 17.2–DET 26.3, total 43.5**. Spread now model DET -7.16, vs Bovada DET -2.5. This difference is unusually large, not a validated ATS advantage. NE/DET QB identities still schedule-provisional in this particular model metadata.

## Public website routing / UX

- https://tedgytrends-bit.github.io/sports-betting-model/ and shareable https://tedgytrends-bit.github.io/sports-betting-model/week10.html (has large social thumbnail metadata).
- Static `docs/index.html` and `docs/week10.html` now read latest appended Bovada prices, full 13-game 7:04 Sunday saved scores, 169 OUT/DOUBTFUL/QUESTIONABLE statuses, and separate NE-DET official game-day active/inactive list. NE-DET Injury display uses **7:18 version**, not 7:04; Baseline remains from 7:04. All 12 other remaining matchups show Sunday 7:04 models. TNF retains Nov12 first-public pregame snapshot. Each newer score carries its own original UTC archived time, source links, and exact quote comparison.
- Streamlit `pages/Week_10_Projection_Board.py` was updated identically to show 13 revised games, the 7:18 NE Injury only, and official injury/NE game-day statuses. Old Week 9 static `docs/week09.html` and archived Week 8/9 results untouched.
- Static site GitHub Actions Pages and smoke tests have passed after Sunday changes. A targeted smoke-test upgrade (`smoke-test-public-site.yml`) checks all Sunday output file counts, time safety, source mention and original immutable records.

**Next:** Sunday 90-min-to-kickoff game-day inactive lists for normal noon CT/afternoon/night games should be checked individually and posted with exact source times if asked to update. NEVER label questionable as inactive. Any subsequent new official scores should have fresh pregame UTC timestamps and independent named files; do not overwrite original Sunday 7:04 and 7:18 NE snapshots. User can provide further Bovada quotes. No paid API credits without express permission.


## November 15, 9:07 a.m. CT — critical Malik Willis IR / Kyle McCord fix and full QB audit

**Priority: MODEL INPUT INTEGRITY, not an apparent betting edge.**

User observed Dolphins projected QB was Malik Willis despite officially being on **injured reserve since November 10**. This was a genuine source failure: the nflverse completed-game/next-schedule QB field retained Willis, while the standard *final Week 10 practice injury report* omits players already on longer-term injured reserve. The existing `reject_known_inactive_qb` was fail-closed only for players *already entered in the curated watchlist*; Miami had not been included in that watchlist.

Primary team evidence:
- [Miami placed Malik Willis on IR Nov 10](https://www.miamidolphins.com/news/dolphins-make-roster-moves-x8063)
- [Miami official Nov 14 game preview states Kyle McCord starts at Indianapolis Nov15](https://www.miamidolphins.com/news/game-preview-miami-dolphins-at-indianapolis-colts)
- [Head coach Hafley explicitly discusses McCord as new starter on Nov11](https://www.miamidolphins.com/news/transcript-hc-jeff-hafley-press-conference-november-11)

Added to `data/qb_starters/2026_week10_confirmed.csv`: MIA **Kyle McCord**, player GSIS **00-0040014** cross-checked against a 2026 nflverse-linked player registry, exact primary Dolphins source, article publication Nov14 9:30am ET and actual review timestamp Nov15 9:04am CT. Added both Willis `IR_REPORTED` (hard-blocked) and McCord team-confirmed to `data/qb_starters/2026_week10_watchlist.csv`.

**Model rerun succeeded before kickoff**, workflow [#43728053483](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/43728053483), publication **2026-11-15T15:07:30Z** (9:07:30am CT), `data/public_snapshots/nfl_week10_mia_ind_mccord_corrected_2026-11-15.csv` + JSON manifest. Recomputed actual QB-aware Injury model under corrected QB ID rather than merely relabeling the UI:

| MIA @ IND | MIA | IND | Total | QB name |
|---|---:|---:|---:|---|
| Original 07:04 Sunday snapshot — **wrong** | 21.6 | 22.3 | 43.8 | Malik Willis (IR) |
| Subsequent 09:07 source-corrected preview | 22.9 | 20.9 | 43.8 | Kyle McCord (Miami confirmed) |

This apparent **model Miami outright win** is *not a reliable betting edge*: McCord has **zero NFL regular-season dropbacks**, model `confidence=insufficient_data`, and a non-calibrated EPA-to-points fallback. Book line user screenshot Colts -4.5, total 37.5. The site explicitly labels Miami's **Injury ATS "PASS — uncalibrated rookie QB"** and totals as research only rather than a confident recommendation. Do **NOT** promote the 6.5-point ATS discrepancy to the user's bet ledger.

A **26-player independent starting-QB identity crosscheck** `data/public_snapshots/nfl_week10_qb_identity_crosscheck_2026-11-15.csv` compared all 26 Sunday/Monday model QB names with a separately updated contemporary [Nov15 independent depth chart index](https://lineupfield.com/starting-quarterbacks/), adjusted where authoritative team-reported starter superseded stale depth chart (Seattle Lock). Original model **25/26 match**, exception Miami. Corrected model **26/26 agree with independent roster reference**. Evidence levels: **5** direct team-specific starter announcements (MIA McCord, ARI Beck, SEA Lock, CLE Watson, MIN Cousins), **1** coach-expected (BAL Brissett), **20** independently secondary-depth-chart-corroborated *but not primary-source verified or confirmed active*. This crosscheck does NOT prove the remaining 20 starters are final game-day actives, and is not equivalent to an authoritative full inactive list.

Static `docs/index.html` and `docs/week10.html` now REQUIRE the Miami corrector and 26-team crosscheck, show the new one-game score version and QB names, and flag rookie QB valuation as **PASS** rather than misleading high-confidence ATS. Streamlit `pages/Week_10_Projection_Board.py` similarly gates on these files and preserves earlier wrong Sunday version (for transparent error tracking) and every other game's history. Unit tests `tests/test_qb_expected_starters.py` explicitly assert the old Willis version is caught by IR guard and McCord/GSIS/source is correct; website smoke tests assert a 26/26 check, one archived error, hard-blocked IR, and rookie ATS PASS. GitHub Pages deployment and CI passed.

**Structural gap still outstanding:** nflverse *practice injury reports* omit players already on injured reserve, whether QBs or non-QBs. The team-level Injury model's final-report count adjustment is NOT a full injured-roster/IR availability model. Add an independent current roster status and team transaction roster gate to the publication pipeline before declaring future weeks final; no claim of a complete future solution has been made. In the meantime, do not call incomplete pregame model source statuses fully verified, and fail closed if official IR/OUT vs selected QB conflicts.

The official first Sunday 07:04 and Thursday Nov12 records remain immutable, and the one-game 09:07 correction is a separately tracked later vintage.
