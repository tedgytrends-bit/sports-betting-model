# Historical standardized efficiency and player-role injury comparison

**Research only.** The public Week 9 model, totals model, official ledger, and Week 10 projections were not modified.
Identical 1,021 historical games. 2022 W16 start; 2023-2025 full seasons; 2026 weeks 1-8 only.

## Chronological 2025 evaluation

| Variant | ATS W-L-P | ATS ≥3.5 pts W-L-P | Margin MAE | Total MAE |
|---|---:|---:|---:|---:|
| baseline_unscaled | 146–138–1 | 62–65–0 | 10.40 | 10.68 |
| baseline_std_alpha10 | 145–139–1 | 58–43–0 | 10.16 | 10.64 |
| baseline_std_alpha100 | 142–142–1 | 59–47–0 | 10.17 | 10.62 |
| nonqb_counts_unscaled | 135–149–1 | 68–68–0 | 10.55 | 10.70 |
| nonqb_counts_std_alpha10 | 144–140–1 | 61–59–0 | 10.35 | 10.68 |
| nonqb_counts_std_alpha100 | 142–142–1 | 57–59–0 | 10.33 | 10.65 |
| nonqb_player_role_std_alpha10 | 143–141–1 | 64–54–0 | 10.34 | 10.70 |
| nonqb_counts_plus_roles_std_alpha10 | 143–141–1 | 63–59–0 | 10.36 | 10.71 |

## 2026 weeks 1-8 evaluation

| Variant | ATS W-L-P | ATS ≥3.5 pts W-L-P | Margin MAE | Total MAE |
|---|---:|---:|---:|---:|
| baseline_unscaled | 60–55–6 | 23–19–2 | 9.68 | 11.53 |
| baseline_std_alpha10 | 59–56–6 | 26–22–0 | 9.79 | 11.54 |
| baseline_std_alpha100 | 62–53–6 | 24–22–0 | 9.79 | 11.53 |
| nonqb_counts_unscaled | 62–53–6 | 23–17–2 | 9.63 | 11.51 |
| nonqb_counts_std_alpha10 | 58–57–6 | 25–21–0 | 9.78 | 11.46 |
| nonqb_counts_std_alpha100 | 58–57–6 | 24–21–0 | 9.77 | 11.48 |
| nonqb_player_role_std_alpha10 | 57–58–6 | 24–21–0 | 9.80 | 11.51 |
| nonqb_counts_plus_roles_std_alpha10 | 56–59–6 | 24–22–0 | 9.85 | 11.44 |

## How to read this

- Compare 2025 and 2026 W1–8 separately. Do not choose the largest in-sample ATS count.
- A good model needs lower margin MAE and stable directional accuracy, not just 3-point-edge hits.
- Role input uses prior PBP participation shares and cannot price OL or long-term IR accurately.
- This ablation excludes the production QB-EPA overlay, which needs its own separately audited replacement-based test.
- If improvement is weak or inconsistent, leave the production scores unchanged.
