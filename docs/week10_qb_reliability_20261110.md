# Week 10 QB input reliability — November 10, 2026

**Research only; nothing published or retrospectively regraded.** The official Week 8+ prospective ledger and the public Baseline/Injury scorecards remain unchanged.

## What triggered this work

A successful Week 10 experimental QB-aware Injury capture (14 upcoming games) displayed **Tyler Huntley** as the Ravens starter on November 16 even though Baltimore placed Huntley and Lamar Jackson on injured reserve on November 5. Baltimore's coach subsequently stated on November 9 that he expected **Jacoby Brissett** to start against the Chargers. The same model listed **Gardner Minshew** as the Cardinals' starter against the Rams, while Arizona's coach said Minshew was under arm/elbow evaluation and Carson Beck would be in line if he could not play. That **does not yet establish who will start for Arizona**.

Primary sources:
- [Ravens officially place Lamar Jackson and Tyler Huntley on IR, Nov 5](https://www.baltimoreravens.com/news/lamar-jackson-tyler-huntley-injured-reserve-austin-reed-adisa-isaac-jake-moody)
- [Ravens head coach expects Brissett on Monday vs Chargers, Nov 9](https://www.baltimoreravens.com/news/kyle-hamilton-injury-update-jacoby-brissett-starting-against-chargers-monday-night-minter-lamar-jackson-injury-conversations-private)
- [Cardinals: Minshew injured, Beck in line if unavailable, Nov 9](https://www.azcardinals.com/news/quarterback-in-flux-after-gardner-minshew-banged-up-arm-injury-carson-beck)
- [Giants J.J. McCarthy hip limited, Nov 9](https://www.giants.com/news/giants-vs-commanders-week-10-injury-report-qb-j-j-mccarthy-rb-cam-skattebo-limited)
- [Commanders Jayden Daniels full participation on estimated injury report, Nov 9](https://www.commanders.com/news/commanders-vs-giants-week-10-injury-report-2026)

## Changes implemented

1. Added `research/validate_qb_starter_confirmations.py`: a row must carry a game-specific content-review attestation, a relevant type of coach/team starter statement, a review note, and plausible source publication/review timestamps **before kickoff** to be passed through as `verified_pregame`. A URL and a timestamp alone are explicitly insufficient. This validates metadata and the review assertion; software cannot independently prove what an article says.
2. Hardened `scripts/capture_qb_aware_injury.py` to exclude invalid/old/manual-unreviewed overrides, record row-level audit artifacts, expose verified-count and `release_ready`, and archive a separate `verified_only_projected_home/away/total` sensitivity. The published-candidate score columns themselves are untouched; sensitivity reverts to the **original non-QB scores** when either QB is unverified. The official public site is not changed.
3. Added an optional backward-compatible `expected` source to `qb_epa_model.py` and `expected_starters` to `injury_model.project_qb_aware_injury`. An expected QB explicitly announced by a coach can supersede an outdated generic schedule QB while retaining status `coach_expected_pregame_unverified` and never being miscounted as verified.
4. Staged `data/qb_starters/2026_week10_expected.csv` with Baltimore's **Jacoby Brissett (GSIS 00-0033119)** and the November 9 primary team statement. The article says he is *expected* to start, so the status remains `COACH_EXPECTED_NOT_FINAL`. No confirmed/verified Week 10 starter CSV has been created.
5. Added `data/qb_starters/2026_week10_watchlist.csv` to explicitly identify conditional/uncertain Week 10 QBs and both Baltimore IR quarterbacks; `reject_known_inactive_qb()` blocks a research candidate when it selects a named IR/OUT/inactive QB from that watchlist.
6. Added regression tests for source freshness and manual review, fallback to non-QB scores, expected-starter priority over provisional schedules, and known-IR blocking. Week 10 research workflow defaults to Week 10, runs these tests, preserves versioned artifacts and cancels superseded jobs. The obsolete Week 9-only QB shadow has been changed to manual dispatch instead of automatically failing on each shared QB module push.

## Initial research capture comparison

The first Week 10 research job (run [#42883298148](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42883298148)) completed all **14** games, with **28/28 schedule-provisional/unverified QB identities**. It incorrectly used Huntley for Baltimore. The next research job after adding the coach-expected source (run [#42884324874](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42884324874)) completed successfully and used **Brissett**, with **27 provisional** and **1 coach-expected-unverified**, still **zero independently verified Week 10 starters**. `release_ready=false`.

Baltimore's research model QB margin adjustment changed from approximately **-2.37** points on the Huntley assumption to **-3.68** points on the coach-expected Brissett assumption. Neither value is established as calibrated. The model's projected total for that game remained approximately 42.69 because the QB layer is margin-only. This illustrates input sensitivity, **not a betting recommendation**.

**Critical:** This run is still preliminary, from changing pregame QB source evidence. It does not establish a reliable model price or a validated QB penalty, and there is no reason to rewrite Week 9 or freeze the Week 10 website based on it.

## Known uncertainties

- Arizona's Week 10 quarterback remains uncertain: an injury report says Minshew is being evaluated and Beck is a conditional replacement. Do **not** automatically set Beck as confirmed or rely on a stale provisional Minshew starter.
- Giants' J.J. McCarthy is reported limited with hip injury; Washington's Jayden Daniels had full estimated practice participation. Neither fact is itself a game-specific final starter confirmation.
- High-impact unverified QB margin shifts, notably Baltimore and New York and Minnesota, require source review before any deliberate release.
- QB replacement EPA-to-points is still uncalibrated. Correcting source identities does **not** prove the 5-point cap or margin shift.

## Recommended Week 10 gate

- Maintain original Baseline and non-QB Injury versions as the control.
- Confirm exact starter identities as new authoritative reports arrive, with game-specific source notes and actual source-review timestamps. Do not infer availability from depth-chart rank or a generic profile.
- Require current real sportsbook lines, timestamps, and identifiable prices before treating any edge as executable. Do not issue official recommendations when important QB statuses remain unresolved.
- Freeze an immutable **Week 10** forecast before each kickoff and evaluate candidates prospectively; never overwrite Week 8–9 prospective records.

## Completed end-to-end confirmation

The final Week 10 workflow [#42884832007](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42884832007) **succeeded on November 10**: all **33 targeted tests passed**, all **14 matchups were projected as a research-only candidate**, the watchlist check ran and did not select a known IR/OUT QB, and versioned forecast/QB-detail files were uploaded as a private-to-workflow downloadable GitHub Actions artifact (30-day retention).

- Starter provenance: **27 schedule-provisional, 1 coach-expected-unverified (Jacoby Brissett), 0 confirmed**.
- The source verification gate reports `release_ready=false` and `both_starters_verified_games=0`; none of these preliminary QB-adjusted projections are cleared for public publication.
- Baltimore's starter is Brissett, not IR Tyler Huntley, in the latest research run.
- Arizona still shows Minshew as an *unverified schedule provisional* while the actual starter remains unresolved. Treat its QB-adjusted projection as unfit for official freeze until team update.
- The recorded `verified_only_*` sensitivity restores the original non-QB Injury scores when either QB is unverified. It does not overwrite the candidate or any frozen public forecast.

**Result:** The automation now flags its own uncertainty instead of treating a passing job as proof of valid starting-QB inputs. This is an input-quality improvement, not evidence of ATS profitability.
