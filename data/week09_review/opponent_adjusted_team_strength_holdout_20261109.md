# Opponent-adjusted NFL team strength: walk-forward experiment

**Research only.** This test does not change Tedgy Trends' public projections, totals, or official records.
Game-by-game opponent Elo and strength-of-schedule-adjusted recent form are computed before kickoff.
Identical 1,021 games; 2025 and 2026 Weeks 1–8 reported separately.

| Variant | 2025 ATS | 2025 ≥3.5 pts | 2025 margin MAE | 2026 W1–8 ATS | 2026 ≥3.5 pts | 2026 margin MAE |
|---|---:|---:|---:|---:|---:|---:|
| baseline_original | 146–138–1 | 62–65–0 | 10.40 | 60–55–6 | 23–19–2 | 9.68 |
| baseline_standardized | 145–139–1 | 58–43–0 | 10.16 | 59–56–6 | 26–22–0 | 9.79 |
| baseline_plus_elo | 128–156–1 | 30–41–0 | 10.30 | 59–56–6 | 14–18–2 | 9.96 |
| baseline_plus_elo_standardized | 139–145–1 | 32–39–0 | 10.16 | 58–57–6 | 15–22–2 | 9.94 |
| baseline_plus_elo_sos_form | 135–149–1 | 31–34–0 | 10.25 | 64–51–6 | 16–18–2 | 9.99 |
| baseline_plus_elo_sos_form_standardized | 144–140–1 | 36–39–0 | 10.17 | 58–57–6 | 15–21–2 | 9.96 |

## Validation and decision

- Historical Baseline replication max absolute score difference: 0.00000000.
- 2021 is training only; 2022 is a partial evaluation; 2023–2025 complete evaluated seasons.
- Evaluate MAE, ATS directional win rate and conditional edge results together, not merely favorites.
- No optimizer chose Elo features based on Week 9 or MNF; this is a **shadow** research comparison.
- Require stable year-over-year improvement and new prospective weeks before considering a public replacement.
