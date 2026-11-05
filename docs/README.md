# Tedgy Trends — connected public site

This directory contains the static, mobile-responsive Tedgy Trends NFL model dashboard. It is a **presentation layer only**: it never recalculates, retrains, modifies, or grades source models in GitHub.

## Data connected (GitHub main, read-only on browser refresh)

- `data/public_snapshots/nfl_week_09_six_model_research_2026-11-04.csv`: the saved Week 9 model predictions. Only Baseline and Injury appear as default public views; Efficiency and Combined are available as clearly labeled research comparisons in each matchup.
- `data/bovada_lines.csv`: the latest archived user-supplied Week 9 Bovada quotes. Archive ingestion timestamps should **not** be represented as screenshot capture timestamps.
- `data/public_snapshots/nfl_week_08_public_2026-11-01.csv`: the original twelve-row Week 8 published projection record.
- `data/four_model_week08/week08_four_model_comparison.csv`: final scores and a distinct all-four-model fourteen-game **research** comparison, which contains reconstructed projections.

The site recalculates Week 8 grades from the original documented picks and lines plus the final scores, then displays a standardized flat -110 ROI estimate separately from any actual or price-verified ROI. Two games present in the fourteen-game research comparison are not automatically added to the original twelve-game public snapshot.

**Week 9 research status:** The saved model data currently carries `RESEARCH_ONLY_NOT_OFFICIAL`. The site preserves that label rather than calling these official tracked picks.

**Latest model:** The repository currently has a committed research/frozen Week 9 snapshot and a more recent archived Bovada market. The site intentionally disables the Latest *model* toggle until a separately timestamped latest projection feed exists. Market refresh is not a replacement model projection.

## Deployment (no paid website builder)

1. Merge the associated pull request after reviewing changes.
2. Go to **Settings → Pages → Build and deployment → Source → GitHub Actions**.
3. Open **Actions → Publish Tedgy Trends site** and run workflow if not already triggered by the merge.
4. The standard project URL should become `https://tedgytrends-bit.github.io/sports-betting-model/` **only after GitHub Pages reports a successful deployment**.

The workflow deploys only the `docs/` directory. GitHub Pages hosting is separate from Streamlit and does not use the model's paid API keys. Public GitHub raw CSV files are loaded read-only by browser JavaScript.

## Next season-week extension

The dashboard intentionally points to the fixed Week 9 file while validation is underway. For Week 10 and later, generate a clearly versioned weekly frozen file and a separate latest projection file (if available), then update the source paths and week labels together. Do not silently retarget an older frozen CSV. The week-by-week prospective-results ledger should accumulate only originally published, timestamped picks.

## Data integrity behavior

The page rejects incomplete Week 9 archive feeds (fewer than 15 matchups, duplicate predictions, missing both primary models, incomplete market archive, or inconsistent capture timestamps). It does not show mock/fallback predictions in place of missing data. Team alias `LAR` is normalized to `LA`. Injury report presence is not treated as verified pre-kickoff delivery.

*Not betting advice. Model performance is research; none of this establishes a profitable betting edge.*
