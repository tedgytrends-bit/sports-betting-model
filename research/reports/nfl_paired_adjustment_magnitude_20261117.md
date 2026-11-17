# Published model-pair adjustment-magnitude test — 2026 NFL Weeks 8–10

**Research only, November 17 2026.** Source: `data/public_results/nfl_2026_graded_games.csv`, matched 43 FINAL games with original Baseline and Injury published predictions and Bovada spreads. This comparison is not a pure player-injury/QB ablation: other model differences may be present. Frozen public results and totals are unchanged.

Magnitude is `abs((injury projected home - injury projected away) - (baseline projected home - baseline projected away))`. Bands selected for descriptive analysis, not a prospectively tested strategy.

| Change in margin | Games | ATS pick flips | Baseline W-L-P | Injury W-L-P | Baseline margin MAE | Injury margin MAE |
|---|---:|---:|---|---|---:|---:|
| <1 point | 8 | 1 | 3-5 | 2-6 | 12.261 | 12.108 |
| >=1 and <3 points | 24 | 4 | 9-14-1 | 7-16-1 | 10.789 | 11.088 |
| >=3 points | 11 | 4 | 5-6 | 7-4 | 12.207 | 11.314 |
| ALL | 43 | 9 | 17-25-1 | 16-26-1 | 11.426 | 11.336 |

The largest-change subgroup is directionally promising, but **n=11** is far too small to claim a valid filter or recommend bets. Comparing subgroup ROI after seeing results would be in-sample selection. Some small-change picks flip because they sit near the spread, so flip count is not proportional to adjustment size.

## Next experiment: true QB ablation

1. Find the actual pregame player-level Injury pipeline and saved per-game QB replacement feature values, source timestamps and role status.
2. On a single **identical** game set, rerun with QB feature zeroed while holding all other player injury, efficiency, weather, rest and odds features fixed; separately zero non-QB injury values. Ensure model code and training are held fixed.
3. Audit cases where QB feature differs from zero and its sign/magnitude, starter/backup identification and injury information availability at kickoff.
4. Compare paired MAE, ATS picks and log loss/calibration if probabilities are produced, on season-forward historical holdouts. Do not tune on W8–10 and call it out-of-sample.
5. No changes to production model or official results based on these exploratory bins.

**Current status:** Published Baseline vs Injury paired comparison completed. Actual isolated QB/non-QB ablation not yet run; archived per-player feature data and model runner need to be located and validated.
