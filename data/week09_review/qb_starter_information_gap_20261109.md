# QB starter hindsight-bias audit: 2026 Weeks 1–8

Research only. This report separates **pregame inferable QB identity** from **actual QB known after kickoff**.
All model comparisons use the same 2026 pregame non-QB Injury forecast and the same nflverse lines.

- Correct previous-game QB inference: **214 of 242** team-games.
- Incorrect inference: **28** team-games; 25 games affected.
- QBs with missing inference: 0 game margins.

| Group | N | Non-QB Injury ATS | Prior-only QB ATS | Postgame QB oracle ATS | Non-QB margin MAE | Prior-only MAE | Postgame-oracle MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| all_common | 121 | 62–53–6 | 63–52–6 | 63–52–6 | 9.63 | 9.51 | 9.58 |
| both_qbs_same_as_last_primary | 96 | 51–41–4 | 51–41–4 | 51–41–4 | 8.79 | 8.66 | 8.66 |
| at_least_one_qb_differs_from_last_primary | 25 | 11–12–2 | 12–11–2 | 12–11–2 | 12.87 | 12.76 | 13.12 |

## What this establishes

- Retroactive QB knowledge must not be claimed as a prospective betting result.
- Identify verified starting QBs and their replacement options before freezing the live board.
- For teams without verified starters, label *inferred*, and don't invent an OUT penalty.
- Evaluate model effects on QB-change weeks separately from all stable-starter weeks.
- A postgame oracle is useful only to estimate a potential upper bound on identity quality.
