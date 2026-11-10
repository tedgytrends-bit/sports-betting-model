# 2026 NFL Week 9 — final full-slate model performance audit

**Research only, all 15 completed games** (Thursday + 13 Sunday + MNF).
All grades use committed pregame projections and separately archived Bovada prices.
Do not interpret the market quotes as confirmed executable closing lines.

## Same-game ATS and totals records

| Model | ATS | Totals | Margin MAE | Total MAE |
|---|---:|---:|---:|---:|
| official_injury | 3–11–1 | 9–6–0 | 11.49 | 11.01 |
| baseline_research | 5–9–1 | 8–7–0 | 11.03 | 11.53 |
| injury_legacy_research | 5–9–1 | 7–8–0 | 10.86 | 11.90 |
| efficiency_research | 4–10–1 | 7–8–0 | 10.23 | 11.46 |
| combined_research | 5–9–1 | 7–8–0 | 10.19 | 11.91 |

## Flagged findings

- Official ATS edge ≥3: 0–8–1; assess calibration, not just hit rate.
- Official totals edge ≥3: 6–3–0.
- Official ATS when siding with a favorite: 2–2–0.
- Official ATS when siding with an underdog: 1–9–1.
- The sportsbook favorite covered 11 games, lost ATS in 3, and pushed 1; unusual chalk-heavy week.
- Mean absolute winning margin: model 3.11, market 5.37, actual 12.87.
- Model margin MAE 11.49 vs market spread MAE 8.63; model didn't outperform the market on margin accuracy.
- ATS side flips from Baseline to the final Injury model on previously completed games: 2026_09_NYG_PHI, 2026_09_GB_NE.

## Week 10 research gates

1. Freeze all 15 Week 9 official forecasts and research-only results.
2. Walk-forward test market-relative margin calibration and model overconfidence in underdogs against 2022–2025 and holdout 2026 games.
3. Run player-role and replacement-value injury experiments separately from unmodified Baseline.
4. Compare score MAE, total MAE, ATS by edge bucket, and prospective stability before making any live changes.
5. Preserve the currently published Week 10 model as a pregame snapshot once validated, rather than retroactively changing past picks.

**Data lineage:** data/week09_review/verified_completed_scores_week09_20261110.csv; data/public_snapshots/nfl_week09_final_injury_2026-11-08.csv; data/public_snapshots/nfl_week09_injury_qb_epa_margin_2026-11-05.csv; data/bovada_lines.csv; data/public_snapshots/nfl_week09_kickoffs_2026.csv.
