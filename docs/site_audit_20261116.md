# Tedgy Trends — full public-site audit and UX repair (November 16, 2026)

Scope: GitHub Pages public home `docs/index.html`, shareable Week 10 `docs/week10.html`, preserved Week 9 archive `docs/week09.html`, Results presentation `docs/public-results.js`, automated GitHub Pages deployment and actual browser workflows. No adjustments to model coefficients, frozen score snapshots, official outcome scores, or paid NFLMeta/EndzoneAPI usage.

## What was confusing

1. **Week 9 as top navigation:** The public root and shareable Week10 URLs had an old top-level `Week 9` link that competed with Results and current projections. The archived Week9 page also offered an obsolete Week8-only Results tab.
2. **Overloaded projections header:** The page opened with several sentences about initial vs final snapshots and four KPI cards, while still displaying `Initial · Nov 12` after Sunday pregame updates. The status strip gave long technical data-source narratives.
3. **Too much per-game injury text:** Long official practice designation lists expanded inside every projection card by default, overpowering projected score, market, and ATS/totals information. Official confirmed game-day inactives were visually subordinated to the earlier practice report label.
4. **Finished games looked pregame forever:** Game cards showed original predicted scores but did not visually distinguish confirmed final scores from them. The Results page had the verified scores in a separate view, requiring guesswork about which games had finished.
5. **Too much methodology above the fold:** Research source files and historical qualifications were laid out in a long block rather than available as optional detail.
6. **Hardcoded Week 10:** The previous homepage's builder only accepted Week10's 14-game CSV structure, so publishing Week11 forecasts would not advance the root page even though the Results grader already dynamically discovered future weeks.
7. **Risk of stale browser scripts and remote files:** Results had previously broken due to cached JavaScript paired with different HTML. Pages now loads the versioned Results script and bundles results CSVs with each deploy instead of relying solely on a separate RAW GitHub host.

## Implemented public information architecture

**Three top navigation links:** `Projections`, `Results`, and `About`. No historical week in the main navigation.

**Projections:** current published week headline, short introductory line, three compact KPIs (matchups, >=3-point ATS gaps, >=3-point totals gaps), Injury and Baseline model switch, optional search/edge/sort controls, actual projected away/home scores, model and Bovada totals/spreads, directional leans, game details. For completed games, a separate FINAL strip now displays the independently verified actual score and Injury directional grades; original projected scores remain unchanged. Practice injury report lists are collapsed behind a summary with OUT/questionable counts; confirmed game-day inactives appear above lower-confidence designations. Rookie quarterback research/uncalibrated PASS is preserved. A small expandable `Previous weeks and archived projections` block retains Week9 and Week8 history.

**Results:** two overall **Injury ATS** and **Injury totals** record cards, week-by-week records, and responsive game-by-game cards with a week/game-day filter. No public Baseline research performance card. The special Week8 retrospective Baseline direction for IND@JAX remains disclosed behind record-methodology details and a small per-game note. Derived complete-direction totals record **24–18** is distinct from original Injury published directional totals **23–18 plus one exact-market no-pick**; never equate them in audit copy.

**About:** four short summaries of Baseline, Injury, market differences, and tracked results. Original model files, timing cautions, retrospective research and documented limitations retained inside one expandable `Sources, original snapshots and limitations` disclosure. Short up-front disclaimer: archived sportsbook snapshots and model leans are not betting advice.

**Week9 archive:** separate `docs/week09.html` retains all 15 previously published frozen game scores. It now says `Week 9 archive`, no longer claims to be current, and its Projections / Results / About navigation routes to the current site, avoiding the old Week8-only Results section. Clicking the site logo returns to current projections. The dedicated Week10 shareable page remains accessible and frozen to its correct weekly datasets.

**URL and error behavior:** `?view=results` and `?view=method` are shareable direct-view routes; tab changes update browser URL. Raw diagnostic errors are no longer printed below the public footer; validation failures still render specific visible error notices in the relevant sections.

## Automatic future-week transition

Home `docs/index.html` uses **real, published prospective rows** from `data/public_results/nfl_2026_graded_games.csv` once a Week11+ cohort is available. Each game must have BOTH original Baseline/Injury source entries, matching team and kickoff IDs, finite score and Bovada numbers, and real archive timestamps earlier than kickoff. No independent claim of confirmed injuries/starting QB is made from those data fields. The latest published week becomes the main board without rewriting Week10; users can browse historical Week11+ data using `?week=NN`, and `week10.html` and `week09.html` remain valid. Results-derived completed scores are attached by exact game ID. The grader/publisher must still publish that new week's real frozen model snapshots and user Bovada prices first; this website creates no forecasts or sportsbook odds itself.

The future-week builder also has a simplified, truthful generic game-detail drawer using the published archived Baseline/Injury score pair and bookmaker spread/total, rather than incorrectly linking every future game to Week10's QB and injury documentation.

## Verification and limitations

- Public Pages static smoke `.github/workflows/smoke-test-public-site.yml` checks Week10 frozen score integrity, public results cohort, correct nav and active site JS, source links, social preview metadata and Streamlit pages.
- Real headless Chromium `tests/results_browser_smoke.cjs` under `.github/workflows/smoke-results-browser.yml` tests at 390px mobile and 1365px desktop for both home and Week10 links: no JavaScript exceptions or horizontal overflow; correct ATS/totals overall cards; 14 game cards; score state; model toggles; team search; actual matchup drawer; About navigation; preserved evidence sources and Week9 archive. Week9 archive independently tested with 15 original games and correct return navigation. Additional synthetic Week11 *test-only* fixture exercises future-week dynamic branch without creating a real forecast, bet or game result.
- Pages `.github/workflows/deploy-tedgy-trends.yml` deploys the HTML/JS plus validated `data/public_results` CSV snapshots on every relevant results update.
- Known limitation: **Week11 cannot appear before legitimate pregame Baseline+Injury publication and archived Bovada lines.** No forecast is invented merely because another NFL week has started. A truly live sportsbook or injury data stream is not part of this site.
- Preserve the original published ATS/totals archive, Week8–10 frozen projection files and source provenance. Do not turn the retrospective Week8 model tie-break into a falsely described prospective Injury pick.
