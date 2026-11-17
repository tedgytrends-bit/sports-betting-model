# QB replacement evidence review and promotion gate — November 17, 2026

Research-only audit of already archived experiments. **No new QB model execution** and no new API requests. Source files:

- `data/player_injury_backtests/qb_point_impact_validation_20261110T152632Z.json`
- `data/player_injury_backtests/qb_actual_replacement_validation_20261110T152644Z.json`
- `docs/week10_margin_lookback_qb_evidence_20261110.md`
- `data/public_results/nfl_2026_graded_games.csv`

## Evidence

- 68 eligible QB1-OUT team-games from the historical player audit, with 47 in the 2024–2026 holdout and 21 in the 2021–2023 development period. The eligibility procedure requires same-team replacement history, a minimum of 3 prior games and passer/rusher participation evidence; it does not prove full-game QB snap coverage or contemporaneous official injury-report publication.
- Estimated QB absence impact vs observed team-score residual: development Pearson r=+0.159 (n=21), holdout r=−0.089 (n=47); 95% bootstrap holdout CI [−0.366, +0.187]. The expected directional relationship is negative, but neither the weak holdout correlation nor its uncertainty validates a reliable point-value estimate.
- Actual replacement QB valuation: development r=+0.220 (n=21), holdout r=−0.115 (n=47). Actual primary QB is identified retrospectively by target-game dropbacks; this is a **validation label**, not a permissible pregame predictor.
- In 68 eligible QB1-OUT cases, mean actual-minus-baseline team points was −2.769 versus +0.407 for 2,004 descriptive controls, an **unadjusted difference of −3.176 points**. This is confounded, nonrandom, and cannot be adopted as a QB absence penalty.
- Week 9 same-vintage Sunday/Monday QB overlay sensitivity (14 games): non-QB Injury ATS 5–8–1, QB-overlay 3–10–1. The two directional flips NYG–PHI and BUF–MIN were losses. Only 2/14 games had both starters independently verified in that audit. Requiring both verified starters would have retrospectively produced 4–9–1; **not an approved policy**.
- Public 2026 Weeks 8–10 Baseline vs Injury is a different comparison: 43 games, Baseline 17–25–1 vs Injury 16–26–1, model margin MAE 11.426 vs 11.336. This does **not** isolate QB from non-QB injuries.

## Decision

**Do not promote a new QB replacement coefficient, automatic source-only gate, or 3-point injury-adjustment threshold.** In particular, the −3.176 point unadjusted control difference is not causal and should never be used as a model correction.

## Required next controlled test

1. Build a timestamped game-by-team QB roster/starter eligibility table from archived pre-kickoff sources. Mark reserve/IR, uncertain starter, and zero/insufficient QB history explicitly. Missing coverage is unknown, not zero.
2. Re-run the *same trained model* on identical games, varying only (a) QB replacement adjustment off/on, and (b) non-QB player adjustment off/on, with pregame sources and odds frozen.
3. Compare paired per-game margin MAE, bias, ATS flips, and confidence intervals. Report by confirmed/provisional starter and replacement sample size, without cherry-picking only favorable adjustments.
4. Evaluate on chronological held-out seasons with untouched future games. Existing 2024–2026 data and 2026 W8–10 have already been examined, so avoid claiming fresh independent holdout.
5. Keep the live Injury model and all published scores/records unchanged until the above supports a replacement.

No NFLMeta/EndzoneAPI credits used.
