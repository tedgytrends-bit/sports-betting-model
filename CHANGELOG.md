Changelog — v0.6.3
- Added explicit model version constant.
- Added UTC run ID/timestamp and model configuration metadata to exported predictions.
- Added requested/loaded PBP seasons, dataset/prediction/comparison counts, and feature list metadata.
- Added integrity check to prevent totals export row count from exceeding comparison predictions.
- Added JSON backtest run manifest with exported game-ID sequence SHA-256 fingerprint.
- Preserved the existing model and features; no coefficients, feature weights, or betting thresholds were changed.
- This version improves auditability; it does not establish profitability.
