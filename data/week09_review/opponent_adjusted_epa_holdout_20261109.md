# Opponent-adjusted offensive and defensive EPA backtest

**Research only:** Not a replacement for the live Tedgy Trends public Injury model.
All games in the 2026 Week 9 slate and their outcomes are excluded.
An opponent's strength is calculated *before the earlier game occurred*, not using season-end statistics.

| Variant | 2025 ATS | 2025 ≥3.5 ATS | 2025 margin MAE | 2026 W1–8 ATS | 2026 ≥3.5 ATS | 2026 margin MAE |
|---|---:|---:|---:|---:|---:|---:|
| baseline_original | 146–138–1 | 62–65–0 | 10.40 | 60–55–6 | 23–19–2 | 9.68 |
| baseline_std_alpha10 | 145–139–1 | 58–43–0 | 10.16 | 59–56–6 | 26–22–0 | 9.79 |
| opponent_epa_raw | 143–141–1 | 59–61–0 | 10.30 | 59–56–6 | 24–20–0 | 9.66 |
| opponent_epa_standardized | 136–148–1 | 56–45–0 | 10.14 | 60–55–6 | 25–21–0 | 9.75 |
| opponent_epa_std_alpha100 | 143–141–1 | 55–43–0 | 10.13 | 59–56–6 | 24–21–0 | 9.73 |
| opponent_epa_plus_elo_standardized | 142–142–1 | 32–38–0 | 10.17 | 61–54–6 | 16–22–2 | 9.91 |

## Evaluation safeguards

- 1,021 identical historical games, with 2021 in training only.
- Evaluation includes a partial 2022, full 2023–2025 and 2026 Weeks 1–8.
- No Week 9 data, current inactives, or official results were used.
- If 2025 and 2026 disagree, do not change published scores.
