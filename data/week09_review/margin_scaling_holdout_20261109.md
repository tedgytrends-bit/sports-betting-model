# Week 10 research: test historical score-margin compression

**Exploratory and research-only.** Model scores and public pick records are unchanged.
A multiplier is chosen on 2022–2024 only, then tested on 2025 and 2026 Weeks 1–8.
We require a held-out improvement rather than blindly increasing predicted favorites.

| Model | Trained factor | 2025 MAE unscaled → scaled | 2026 W1–8 MAE unscaled → scaled | 2025 ATS unscaled → scaled |
|---|---:|---:|---:|---|
| baseline | 1.25× | 10.40 → 10.37 | 9.68 → 9.80 | 146–138–1 → 138–146–1 |
| injury_legacy | 1.0× | 10.55 → 10.55 | 9.62 → 9.62 | 137–147–1 → 137–147–1 |
| efficiency | 1.1× | 10.40 → 10.42 | 9.76 → 9.83 | 142–142–1 → 141–143–1 |
| combined_legacy | 1.0× | 10.52 → 10.52 | 9.71 → 9.71 | 131–153–1 → 131–153–1 |

**Decision:** Do not apply blanket margin multiplication to live forecasts. Test richer
team-strength features, standardized inputs and market-residual approaches in
chronological backtests, preserving a fresh 2026 Week 10 prospective test.
