# NFL ATS prospective follow-up

November 17, 2026. Research branch only.

## Passing forecast

Matched the last same-capture Baseline and passing forecasts available at the archived Bovada quote, with the quote strictly before kickoff. Finals and kickoff timestamps come from the frozen results archive. Week 8 lacks matched passing captures.

| Week | Games | Baseline ATS | Passing ATS | Baseline / passing / spread margin MAE |
|---|---:|---:|---:|---:|
| 9 | 15 | 4–10–1 | 3–11–1 | 11.02 / 10.83 / 8.63 |
| 10 | 14 | 3–11 | 4–10 | 13.00 / 12.47 / 10.39 |
| Both | 29 | 7–21–1 | 7–21–1 | 11.98 / 11.62 / 9.48 |

The passing component changed four picks. Its lower MAE did not improve the combined ATS record. The raw spread had lower margin MAE each week.

The season-forward test used already archived Ridge predictions with the same fixed alpha 10. It controls for absolute spread, favorite location, and raw Baseline disagreement. It then adds the passing-minus-Baseline margin as one feature in a logistic regression. Training and scaling use only prior seasons. The 679 settled evaluation games use historical schedule spreads with unverified sportsbook timing. The passing feature improved Brier score in 2024, worsened it in 2025 and 2026 through Week 8, and did not add stable information. This specifically tests the incremental forecast produced by the existing all-passing model. An isolated early-down, opponent-adjusted feature would be a distinct experiment.

## Earlier-to-later Bovada capture

Matched all 13 Week 10 games with both timestamped screenshot quotes and a forecast available at the first quote. These are the earliest and latest archived captures for these games. Market opening and closing lines are unverified. Baseline and passing each called the direction of the spread move on five games, went against it on five, and had three unchanged spreads. Each averaged +0.12 points of spread movement in the picked direction. At the earlier quote and the actual archived side-specific American prices, Baseline went 4–9 (−40.91% simulated ROI) and passing went 5–8 (−26.09%). These are simulated returns using captured prices. They are separate from public grades and the personal betting ledger.

## QB-on/off

The initial Week 10 Injury snapshot preserves both scores from the same capture. Grading both at its initial pregame Bovada quote gave QB-off 5–9 (12.10 margin MAE) and QB-on 8–6 (11.17 MAE). The overlay moved three picks from losses to wins (WAS–NYG, MIN–GB, LAC–BAL). This early-vintage test includes provisional starter identities and differs from the later official Week 10 grades.

Week 11 froze 13 paired margins at 11:59:36 a.m. Central, with the same Ridge score base, starter-source and dropback evidence, and kickoff times. The regular-season roster file for Week 11 rejected the schedule's picks of Gardner Minshew (ARI) and Tyler Huntley (BAL), both listed RES. Those two rows retain the provisional output for diagnostic traceability and are ineligible for the starter-validated comparison. The other 11 games passed the current-week roster gate, with starter assignments still provisional. Kyle McCord had insufficient prior dropbacks by the existing model label.

Bovada quotes for Week 11 are pending. Match each pair to one shared timestamped Bovada quote and side prices before kickoff. Keep new source-verified captures separate from the first pair and record the identity and source timestamp with the new capture. Evaluate ATS and margin MAE on eligible pairs, with the full slate and pick flips shown separately once there are finals.

The audit ran with `python -m research.audit_passing_and_market`. The Week 11 capture used `python -m research.freeze_nfl_qb_pair --season 2026 --week 11 --inputs /path/to/public-inputs --output /path/to/new-capture.csv`. The capture lists input hashes for the public schedule, roster, injury and play-by-play CSVs. No paid data requests or public model changes.
