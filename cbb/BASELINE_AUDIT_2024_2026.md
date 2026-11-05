# CBB v0 historical backtest — 2026-11-05

Source: CBB Research Backtest workflow run [42106666978](https://github.com/tedgytrends-bit/sports-betting-model/actions/runs/42106666978), artifact **cbb-backtest-reports** (four CSV files). Tests passed. Input seasons 2022–26; held-out test seasons 2024–26. Earlier seasons used exclusively for training. No 2026–27 games or projections in this audit.

## Baseline results (all market-covered games, threshold 0, hypothetical -110)

| Season | ATS W | ATS L | ATS Push | ATS ROI | Totals W | Totals L | Totals Push | Totals ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024 (2023–24) | 2647 | 2662 | 0 | -4.82% | 2670 | 2638 | 0 | -3.97% |
| 2025 (2024–25) | 2676 | 2761 | 0 | -6.04% | 2643 | 2791 | 0 | -7.15% |
| 2026 (2025–26) | 2848 | 2777 | 102 | -3.28% | 2811 | 2862 | 53 | -5.35% |

At ATS threshold 3.5: 2024 1377–1371 (0 pushes), -4.34%; 2025 1461–1450 (0 pushes), -4.18%; 2026 1571–1468–58, -1.29%. No evidence of positive stable ROI.

## Provider and market audit

The market source in the output is not the same across all seasons:

- 2024: ESPN BET on 5,308 games with spread and total, 5,309 spread matches overall.
- 2025: ESPN BET on 5,436 games with both, 5,437 spread matches overall.
- 2026: 4,904 Bovada, 468 Draft Kings, 333 ESPN BET on 5,705 games with both; 5,727 spread matches overall.

Current provider priority normalizes neither "Draft Kings" nor unknown provider naming. This is a high-priority audit item before claiming sportsbook-specific edges. In 2024 and 2025, selected ESPN BET spreads are all half-point lines, explaining zero spread pushes; 2026 includes integer lines, explaining pushes. It would be inappropriate to attribute the changed push counts to model changes.

The signs in the selected lines are consistent with **home team's signed spread**: market home-cover residual MAE roughly 8.87/8.75/9.02 points for 2024/25/26 versus approximately 18–19 points if the sign is reversed; still independently verify manually against published odds.

## Error analysis

- Model ATS MAE all completed games: 10.81 (2024), 11.03 (2025), 11.16 (2026).
- Market ATS MAE on market-covered games: 8.87, 8.76, 9.03.
- Model total MAE all completed games: 13.86, 13.54, 14.42.
- Market total MAE on market-covered games: 12.90, 12.69, 13.38.
- Team's first game of a season: model spread error ~16.2, 17.8, 18.3 points by season, respectively. The market on those covered games ~9.9, 10.2, 9.5 points.
- Teams with 12+ games: model ATS MAE ~9.8 points in each season; market ~8.8, 8.5, 8.8.

This confirms the biggest current deficit is **early-season team strength priors**. The zeroed prior year team performance deliberately avoids stale rosters but also leaves first-game talent effectively unknown.

## Prioritized v1 work

1. Collect *pregame-relevant* rosters, prior-season player stats, transfer destination/source and recruit rankings, and record coverage. Beware historical roster revisions / future-information leakage.
2. Build season-beginning roster-strength priors with player IDs, previous minutes, usage, transfers, and freshman talent. Evaluate against identical test games and lines, with 2026 locked as holdout.
3. Add opponent-strength-adjusted efficiencies and schedule context; test incremental performance, retaining only validated gains.
4. Normalize line providers, record provider and odds timestamps and run audit against independent sportsbook examples.
5. Freeze official prospective projections *before* tipoff, keep latest separate, and only publish after instrumentation/coverage is reliable.

**Research-only**: all ROI at hypothetical -110, lines may not represent accessible pregame bookmaker prices. Historic aggregate results do not imply tradable advantage.
