# NFL Week 10 preparation — lookback length and QB-source research (November 10, 2026)

**Research-only. No production projection code, existing frozen boards, public records, or totals were changed.**

## 1. Controlled historical feature lookback experiment

Code: `scripts/run_lookback_margin_shadow.py`. Automated job: `.github/workflows/lookback-margin-shadow.yml` [run #42851364512](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42851364512), **successful**. Outputs: `data/week09_review/lookback_margin_shadow_20261110.csv` and `.json`.

Design: identical 1,021 chronological historical evaluation games (late 2022 through Week 8 of 2026); matched training-game IDs and test-game IDs; train-only median imputation; compare exactly `lookback_games=6` versus `10`, each with original unscaled Ridge(alpha=10) and standardized Ridge(alpha=10). All post-Week-8 2026 outcomes excluded. Historical market is used for evaluation only, not predictor input. Historical 2025 and 2026 have been examined repeatedly; this study is exploratory and *not* new independent holdout evidence.

| Period | 6-game raw MAE | 10-game raw MAE | 6-game standardized MAE | 10-game standardized MAE | Market MAE |
|---|---:|---:|---:|---:|---:|
| 2023 (285) | 10.6444 | **10.5522** | 10.5338 | **10.3881** | 9.9842 |
| 2024 (285) | 10.6325 | **10.5840** | 10.4785 | **10.3369** | 9.7035 |
| 2025 (285) | **10.2710** | 10.3975 | **10.0933** | 10.1637 | 9.6702 |
| 2026 Weeks 1–8 (121) | 9.8166 | **9.6795** | 9.8978 | **9.7912** | 9.5702 |

The six-game lookback did not consistently improve margin accuracy. For 2026 Weeks 1–4, raw 6-game MAE was 9.6421 versus raw 10-game 9.6893 (64 games); Weeks 5–8 raw 6-game worsened to 10.0125 versus 10-game 9.6685 (57 games). These splits are too small to use for a new automatic window-switch rule.

At a fixed 3.5-point ATS threshold on archived nflverse schedule-feed lines:

| Period | Raw 6-game W–L–P | Raw 10-game W–L–P | Standardized 6-game W–L–P | Standardized 10-game W–L–P |
|---|---:|---:|---:|---:|
| 2025 | 69–61–0 | 62–65–0 | 64–49–0 | 58–43–0 |
| 2026 W1–8 | 23–20–1 | 23–19–2 | 24–22–3 | 26–22–0 |

These policies make different numbers of bets. Do not choose on in-sample/previously inspected ROI. A fixed −110 return assumption is an illustrative simulation, not a verified executable Bovada quote.

### Finding about 2026 favorites

On 28 games with market favorite spread magnitude >=7 points (Weeks 1–8, 2026), the mean **market-favorite-relative** final margin was about **5.07**, the average market spread was **8.66**, the historical Baseline forecast about **4.84**, and the standardized version about **7.07**. This explains why margin-scale expansion sometimes hurts in 2026; it does not establish that book-favorite underperformance persists.

**Decision:** Keep the ten-game lookback in production. Neither lookback-six nor lookback-six-plus-standardization has earned a promotion.

## 2. Week 9 verified-versus-provisional QB-source sensitivity (14 Sunday/Monday games)

Source: `data/week09_review/week09_full_summary.json`, `same_vintage_qb_overlay.all_games`, preserving the published Week 9 official model and price snapshot. Thursday's game is excluded because the same-vintage QB overlay comparison contains 14 games, not all 15.

- Both QB starters independently verified pregame: **2/14 games**. At least one QB starter provisional/unverified: **12/14**.
- Original non-QB injury margin ATS grade: **5–8–1**.
- Full official QB overlay on that same game set: **3–10–1**.
- Hypothetical sensitivity policy *only applies QB overlay when BOTH starters are verified*: **4–9–1** (not a proposed live policy).
- Exactly two game ATS directions flip between non-QB and full QB forecasts:
  - NYG–PHI: non-QB NYG (win) -> official PHI (loss), but **both** QB starters were verified.
  - BUF–MIN: non-QB BUF (win) -> official MIN (loss), with one provisional QB label.
- Hence “only trust source-verified starters” would have prevented one of the two Week 9 losing flips, **not both**. Starter identity verification does not validate the numerical impact adjustment. This 14-game retrospective comparison is *not* independent evidence for a policy change, and cannot establish causation.

The older 68-case QB1-OUT team-game validation similarly did not find a stable association between estimated QB impact magnitude and score residual. Before adjusting QB coefficients or setting automatic source thresholds, we need better historical pregame starter verification and prospective calibration.

**Decision:** Keep QB overlay parameters unchanged for existing official records. Conduct verified-replacement calibration in research only; do not infer the correct QB impact from two negative flips.

## 3. Test integrity

GitHub workflow `Test efficiency feature integrity` run #42847190835 failed solely because the workflow did not install `pytest` used by `tests/test_qb_epa_model.py`. Fixed `.github/workflows/test-feature-integrity.yml` to install pytest and run both unittest discovery and the dedicated QB pytest suite. The new workflow run [#42851029681](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42851029681) **passed**.

## Next evidence-driven task

Validate the *Week 10* probable and confirmed starting QBs against timestamped team/NFL sources, keep unknown/provisional labels explicit and compare verified-only versus unverified shifts separately. Preserve the published Baseline and Injury projections unless a genuinely prospective controlled alternative proves superior.

No NFLMeta or EndzoneAPI credits were spent in these research workflows.


## 4. QB starter-source metadata audit (new)

- Added `research/audit_qb_starter_source_metadata.py`, `tests/test_qb_starter_source_metadata.py`, and `.github/workflows/audit-qb-starter-source-metadata.yml`. The audit is separate from the live model; it validates team/game membership, HTTPS source metadata, DST-aware exact kickoff versus publication time, and stale article timestamps, without claiming it has read article content.
- The archived Week 9 input `data/qb_starters/2026_week09_confirmed.csv` has **8 entries**. The audit saved `data/week09_review/qb_source_metadata_audit_2026_week09.json` and .csv.
- **7/8** entries have plausible recent source metadata but have **not** been content-verified by this automated audit; **1/8** needs manual reconfirmation because it is stale.
- Specifically, the ATL Michael Penix Jr. Week 9 override (`2026_09_CIN_ATL`) cites a source dated **September 21, 2026**, about **1,146 hours (47.75 days)** before the actual kickoff. Merely being published before the game is insufficient for game-specific confirmation.
- Research audit output status is `RESEARCH_METADATA_AUDIT_NO_OFFICIAL_CHANGES`. Do not automatically downgrade, retune, or rewrite Week 9 official predictions because of the audit. Source article content still requires a separate human or reliable pregame verification step.
- The feature-integrity workflow runs the metadata unit tests alongside the existing QB pytest suite; the new tests cover correct DST handling and same-day publication before kickoff, which the prior `capture_qb_aware_injury.py` date-only check did not implement. Repairing future candidate-capture validation is a separate task and **has not been applied to the production projection pipeline**.
