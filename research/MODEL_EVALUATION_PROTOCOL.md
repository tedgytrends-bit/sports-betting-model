# Model Evaluation Protocol

## Purpose

Avoid mistaking repeated experiments on overlapping historical games for independent evidence of a betting edge.

## Current conclusion

As of model version 0.8.0, the current NFL ATS research has not demonstrated a robust, repeatable betting edge. The raw efficiency model has worse pooled margin MAE than the recorded market spread and negative simulated ATS ROI at the 3.5-point threshold in the 2023–2025 seasons. Tested market-anchored and injury-enhanced variants have not shown stable performance across seasons. Historical lines are public schedule-feed values, not verified executable sportsbook quotes.

## Rules for future comparisons

1. **Use the same games for model comparisons.** Compare models only on the intersection of games where each model has a prediction. Report coverage separately.
2. **Separate development from evaluation.** Historical results may diagnose a model, but they are not independent validation of changes chosen after viewing those results.
3. **Do not optimize thresholds on the reported test sample.** Keep 3.5, 4.5, 5.5, 6.5, and 7.5 points as descriptive fixed thresholds. Do not choose the best-looking threshold after seeing results.
4. **Pre-register each new model experiment.** Record the hypothesis, changed feature/model, training window, evaluation window, primary metric, and pass/fail rule before running it.
5. **Report predictive and betting metrics separately.** Include margin MAE, calibration/signed error, W-L-P, units, ROI, bet count, and market-price source/timestamp where available.
6. **Account for price realism.** Until a line and odds are captured from an identifiable sportsbook before kickoff, label ROI as a schedule-feed simulation, not executable betting performance.
7. **Keep prospective predictions immutable.** Store prediction timestamp, model version, market line, odds/source, and projection. Grade against final results without replacing the original forecast.
8. **Require prospective testing before claiming an edge.** Historical results generate hypotheses; they do not establish profitability. Do not promote a model because one threshold or season looks positive.

## Proposed next experiment

Do not add another model variant yet. First improve prospective records' line-source and timing metadata. Freeze the current efficiency model as the baseline and collect out-of-sample forecasts. Any later candidate must be compared against the frozen baseline on the same games with a predeclared metric.

## What counts as useful progress

- More reliable timestamped forecasts and verifiable market prices.
- Better performance on untouched games, not just a better historical table.
- Stable calibration and ROI across time with adequate sample size.
- Transparent negative results and no threshold selection based on hindsight.
