# Market-anchored NFL ATS — historical holdout experiment

Research only. No Week 9 results or game-day injuries used; public projections and totals are untouched.

The market-only baseline makes **no ATS wagers** by definition; compare margin MAE separately.
The 50% consensus-to-market blend can reduce margin error but **cannot change the ATS side**.
Ridge predicts the signed ATS residual on the past year's data, using only historical pregame model edges.

## 2025_independent_holdout
Train years [2022, 2023, 2024] (615 games); evaluate [2025] (285 games).

| Candidate | Margin MAE | ATS all games (W-L-P) | ATS ≥2.5 (W-L-P) | ATS ≥3.5 (W-L-P) | Bets ≥3.5 | ROI ≥3.5 |
|---|---:|---:|---:|---:|---:|---:|
| market_only | 9.67 | 0-0-0 | 0-0-0 | 0-0-0 | 0 | N/A% |
| baseline | 10.40 | 146-138-1 | 85-83-0 | 62-65-0 | 127 | -6.8% |
| injury_legacy | 10.55 | 137-147-1 | 88-83-0 | 70-69-0 | 139 | -3.859% |
| efficiency | 10.40 | 142-142-1 | 80-80-1 | 53-57-0 | 110 | -8.017% |
| combined_legacy | 10.52 | 131-153-1 | 80-88-1 | 64-58-0 | 122 | 0.149% |
| consensus_margin | 10.42 | 131-153-1 | 81-85-0 | 58-59-0 | 117 | -5.361% |
| half_market_consensus | 9.89 | 131-153-1 | 35-36-0 | 13-12-0 | 25 | -0.727% |
| market_anchored_ridge | 9.74 | 138-146-1 | 5-3-0 | 0-0-0 | 0 | N/A% |

## 2026_weeks01_08_independent_holdout
Train years [2022, 2023, 2024, 2025] (900 games); evaluate [2026] (121 games).

| Candidate | Margin MAE | ATS all games (W-L-P) | ATS ≥2.5 (W-L-P) | ATS ≥3.5 (W-L-P) | Bets ≥3.5 | ROI ≥3.5 |
|---|---:|---:|---:|---:|---:|---:|
| market_only | 9.57 | 0-0-0 | 0-0-0 | 0-0-0 | 0 | N/A% |
| baseline | 9.68 | 60-55-6 | 32-27-2 | 23-19-2 | 44 | 4.339% |
| injury_legacy | 9.62 | 61-54-6 | 34-27-2 | 25-15-2 | 42 | 18.398% |
| efficiency | 9.76 | 60-55-6 | 27-32-3 | 21-24-0 | 45 | -10.909% |
| combined_legacy | 9.71 | 60-55-6 | 31-31-3 | 23-23-1 | 47 | -4.449% |
| consensus_margin | 9.67 | 63-52-6 | 31-27-3 | 20-21-1 | 42 | -6.71% |
| half_market_consensus | 9.56 | 63-52-6 | 11-9-0 | 0-2-0 | 2 | -100.0% |
| market_anchored_ridge | 9.77 | 49-66-6 | 0-0-0 | 0-0-0 | 0 | N/A% |

## Research decision

Do not replace the live ATS model until a candidate improves both forecast quality and reproducible out-of-sample edge behavior, without retroactive Week 9 tuning.
The totals model is deliberately excluded from this experiment.
