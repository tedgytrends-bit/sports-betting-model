# Tedgy Trends: CBB research v0

Isolated in the cbb/ directory; does **not** modify the NFL model, public
website, NFL data or frozen prospective records.

## What is implemented

- CollegeBasketballData (CBBD) games, team box scores and historical lines
  fetched and cached in monthly chunks to avoid 3,000-game API caps.
- Two separately fitted Ridge models: home margin and game total.
- Season-local pregame team scoring efficiency per possession (shrunk to
  population mean), possession pace, Elo, rest, and neutral/home features.
- No blind last-season carryover. **Games on the same date cannot influence
  each other's features,** and training always precedes the test season.
- Projected final scores; ATS/Over-Under leans against historical lines.
- ATS/totals W-L-P and hypothetical -110 ROI at 0/2.5/3.5/4.5/5.5 edges.
- Historical year-by-year summaries and full game audit CSVs.

## Authentication and setup

Request a free CBBD API key: https://collegebasketballdata.com/key

Store it as GitHub Actions repository secret **CBBD_API_KEY**, not in code or
chat. The API terms permit commercial use with quota limits. CBBD season=2026
means the 2025–26 season; season=2027 means 2026–27.

Run the commands from the repository root:

    python -m pip install -r requirements.txt pytest
    python -m pytest -q cbb/tests
    python -m cbb.cli fetch --seasons 2022 2023 2024 2025 2026
    python -m cbb.cli backtest --seasons 2022 2023 2024 2025 2026 --test-seasons 2024 2025 2026

For 2026–27, fetch the new season and generate a future board:

    python -m cbb.cli fetch --seasons 2027
    python -m cbb.cli board --seasons 2022 2023 2024 2025 2026 2027 --season 2027

For a single date: append --date 2026-11-05.

Raw data is cached under cbb/data/raw/ and model results under cbb/outputs/.
Neither is added to the repository. A manually triggered CBB Research
Backtest workflow will upload resulting CSVs as workflow artifacts.

## Critical limitations and guardrails

This is a v0 **baseline**, not a demonstrated winning model. No actual
historical dataset has been ingested or graded yet. Synthetic unit tests only
check implementation mechanics. Before citing backtest ROI, verify the CBBD
signed-spread direction against a sportsbook on several games and audit
market-provider coverage. Historical prices may differ from the -110 assumed
in the hypothetical ROI. Market lines are used to grade, never to train.

Missing data should never be treated as zero. Historical end-of-season ratings
are not pregame inputs.

**Next:** real historical data audit/backtests; roster-aware transfers and
freshman priors, player availability; injury model; frozen/latest projections
and scheduled reporting; eventual Tedgy Trends site integration.
