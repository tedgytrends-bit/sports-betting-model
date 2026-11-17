# NFL ATS cover-probability test

This follow-up uses the 1,050 fixed-fit injury ablation forecasts already archived in the repository. Logistic regression fits on prior seasons only, with train-only standardization and fixed L2 regularization (C=1). The evaluation covers the same 720 games in 2024, 2025, and 2026 through Week 10. The four models either predict 50% every game, use the signed market spread, add the full Injury edge, or add the both-off model edge and the two injury adjustments individually. Higher confidence means a probability at least 55% for one side. Pushes count in the ATS ledger when selected and are excluded from probability scoring.

| Model | Brier score | Log loss | ATS at 55% | Simulated −110 ROI |
|---|---:|---:|---:|---:|
| Flat 50% | .250000 | .693147 | 0 selections | — |
| Market only | .250413 | .693973 | 0 selections | — |
| Market + Injury | .250739 | .694626 | 0 selections | — |
| Market + separated adjustments | .253063 | .699297 | 61–62 | −5.32% |

Lower Brier score and log loss are better. All three fits had higher loss than flat 50% in each year. The separated fit generated 99 selections in 2024 (47–52), 24 in 2025 (14–10), and zero through 2026 Week 10. The small 2025 positive result had no timestamped non-QB injury coverage. Historic lines are unverified schedule spreads with flat simulated pricing. These previously studied seasons provide chronological diagnostics.

Decision: keep these probability models in research. Prioritize correctly timestamped prospective quotes and starter evidence, then compare opponent-adjusted early-down passing matchups against a market-only control. Retain spread direction and magnitude as controls when testing whether a feature adds ATS information.

Reproduce with `python -m research.nfl_ats_cover_probability`.
