# NFL ATS fixed-fit injury ablation and season-forward calibration

November 17, 2026. Research branch only. **Decision: keep the published Injury model and totals as-is.** The underdog tendency persists with both injury components off, the QB overlay has mixed performance across seasons, and each tested market calibration loses at simulated −110.

## Fixed-fit experiment

The runner scored 1,050 common games from late 2022 through 2026 Week 10. The primary analysis uses 720 games from 2024 onward. For each Monday–Sunday calendar week, the existing Injury scorer fits two Ridge regressions at alpha 10 on completed games strictly before the first target date, with at least 500 training games. Both score forecasts use the same model fit, feature availability and historical medians. Non-QB off sets observed non-QB injury/practice counts to zero on prediction rows only. Missing counts retain their normal imputation and availability flags. This is a zero-reported-count counterfactual within the Injury fit. QB on adds the existing five-point per-team capped EPA shift to the predicted margin. QB off removes that overlay. Existing efficiency, team history and rest inputs, outcomes, and the market spread are identical for each game across all four arms.

| Non-QB counts | QB overlay | Margin MAE | ATS W–L–P | Simulated ROI | Underdog picks |
|---|---|---:|---:|---:|---:|
| Off | Off | 10.510 | 336–373–11 | −9.38% | 568 / 720 |
| On | Off | 10.471 | 345–364–11 | −7.00% | 554 / 720 |
| Off | On | 10.599 | 338–371–11 | −8.85% | 591 / 720 |
| On | On | 10.549 | 339–370–11 | −8.59% | 581 / 720 |

- Turning QB off with non-QB counts on changed 75 picks. The pooled margin MAE difference was −0.079 points with a paired calendar-week bootstrap 95% interval of [−0.209, +0.055]. The QB-on arm went 129–152–4 vs 140–141–4 QB-off in 2024, 138–146–1 vs 135–149–1 in 2025, and 72–72–6 vs 70–74–6 through 2026 Week 10.
- Adding non-QB counts with QB off changed 36 picks and lowered pooled margin MAE by 0.039 points, with a 95% interval of [−0.129, +0.046]. Turning off QB on the 328 games with reports for both teams lowered MAE by 0.202 [−0.378, −0.051]. This coverage-selected cohort is concentrated in 2024 (284 games) and includes no 2025 games.
- Historical injury rows are restricted to timestamps before kickoff. Where present, the research replay takes the latest structurally valid snapshot captured before each actual kickoff. This recovered both-team reports for 44 of 150 games in 2026 and differs from the live loader's latest-file shortcut. The 2025 and 2026 public historical injury CSVs lacked row timestamps. In 2025, the non-QB arms consequently coincide at each QB setting. Coverage is unknown for undelivered or untimestamped reports.
- QB input uses the previous game's primary passer unless a vetted archived confirmation or a coach expectation documented on a previous date is available. The earlier Week 9 confirmation file lacks the content-review fields used by the current validator. Of 1,440 team-games in the primary cohort, 1,436 are inferred, three have an eligible confirmation, and one is coach-expected. Two of the three confirmed QB team-games have insufficient prior dropback history under the model's existing label. Historical game-day roster and reserve status are unverified for the inferred cohort. Target-game schedule QB fields and target-game plays were excluded from starter selection. The QB result evaluates a mostly inferred-starter workflow. It leaves the historical effect of a correctly identified replacement unresolved.

## Structural underdog tendency

With both injury components off, projected margins averaged 3.34 points in absolute value versus 5.03 for the market. That arm still picked 568 underdogs (79%). At spreads of seven or more, it picked the underdog in 173 of 185 games, versus 174 with both components on. This identifies compressed score margins as a source of the directional skew before either injury component is applied. The QB overlay increased the overall underdog count from 554 to 581 with non-QB counts on. For wider spreads, turning the injury components off barely changed the underdog imbalance.

The market tests regress the observed home margin minus the market home margin on prior-season data. The market-only fit uses an intercept and the signed spread. The second adds the full Injury disagreement with the spread. The conditional fit adds favorite location (sign of spread) and its interaction with Injury disagreement. All three freeze their coefficients before each test season and can change pick direction. The raw spread serves as the margin benchmark.

| Variant | Margin MAE | ATS W–L–P | Simulated ROI | Underdog picks |
|---|---:|---:|---:|---:|
| Raw spread | 9.662 | — | — | — |
| Market only, fitted | 9.723 | 347–362–11 | −6.46% | 227 |
| Market and Injury disagreement | 9.736 | 348–361–11 | −6.20% | 228 |
| Conditional favorite adjustment | 9.729 | 349–360–11 | −5.93% | 163 |

The conditional fit recorded two more pooled wins than the market-only fit, with worse pooled margin accuracy. Its season ROIs were −0.13%, −12.57%, and −4.36%. It went 72–72–6 in 2026, the same record as full Injury, while changing 92 picks. The raw market recorded the lowest pooled margin MAE. The primary linear fit's Injury disagreement coefficient was −0.077, +0.131, and −0.002 in the respective test seasons. These results give little support for a stable directional correction or forcing an even favorite/underdog split.

## Interpretation and reproduction

The separate November 17 archives were reproduced on 43 public Weeks 8–10 games. Baseline went 17–25–1 and Injury 16–26–1, with nine flips and MAE of 11.426 and 11.336 respectively. Injury underdogs went 9–20–1. That comparison uses frozen Bovada lines and actual published inputs. The historical experiment uses nflverse schedule spreads with unverified price timestamps and hypothetical flat −110. Its previously studied seasons provide chronological diagnostics. Independent validation needs untouched slates with a frozen quote, matching forecast timestamps, and stronger starter/roster evidence.

Run from the repository root:

```bash
python -m research.nfl_ats_injury_ablation --output /path/to/output
python -m pytest -q
```

The archived run used local copies of public nflverse data with `--inputs /path/to/inputs`. The schedule came from `raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv`. The files named `pbp_YEAR.csv.gz` and `injury_YEAR.csv` came from the `nflverse/nflverse-data` PBP and injuries release assets for 2021–2026. Exact input hashes are in `inputs.sha256`. Game-level forecasts, calibration coefficients, QB source and sample evidence, paired metrics, and market-spread strata are included alongside this report. The backtest made no calls to paid NFLMeta or EndzoneAPI endpoints.
