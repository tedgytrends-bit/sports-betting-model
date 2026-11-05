# CBB player-adjusted v1 — research only

The player-adjusted experiment is built on top of the isolated team-only CBB
baseline. No NFL code or website files are affected.

### Historical inputs

Each season S uses:
- Season S official CBBD roster, strictly filtering to player membership
  startSeason <= S-1 and endSeason >= S. Reject unknown membership bounds.
- Complete individual performance only from season S-1.
- Transfer portal records for calendar S-1; destination and source checked.
- Recruiting grades for freshman class S-1, assigned to a rostered player.
- Player matching via exact athleteId or athleteSourceId only (NO name-only
  joining of historical stats). Names are used only as a portal verification
  aid. This is deliberate protection against same-name false matches.

Individual features include weighted prior offensive/defensive efficiencies,
points per 40 minutes, weighted player quality, roster-minute continuity,
incoming transfer minutes, roster matching coverage, incoming freshmen
recruiting grades, and portal verified counts.

These are *preseason* signals and are exponentially attenuated after real
games are completed. Two independent Ridge regressions model spread and
totals. Compare player v1 and baseline on exactly the same games and market
lines in seasons 2024–26.

### Commands

    python -m cbb.cli fetch --seasons 2022 2023 2024 2025 2026
    python -m cbb.player_cli fetch --seasons 2022 2023 2024 2025 2026
    python -m pytest -q cbb/tests
    python -m cbb.player_cli backtest --seasons 2022 2023 2024 2025 2026 --test-seasons 2024 2025 2026

The workflow "CBB Player V1 Historical Comparison" runs all these steps and
uploads detailed CSVs, market grading, and roster coverage.

### Research integrity

**Archived rosters are not timestamped preseason snapshots.** CBBD can
retroactively revise team membership and portal destinations. Season-bound
membership protects against obvious future players, but does not guarantee
that every roster or transfer was known at each tipoff date. Therefore this
is a **retrospective research proxy**, NOT verified point-in-time historical
player availability. A prospective frozen roster snapshot is required before
public claims of predictive betting advantage.

Missing player match means *unknown*, not zero true talent. The model uses
missingness and roster coverage as explicit features and refuses reporting
when fewer than 100 teams in a tested season have three documented prior-year
player matches. The 2026 season is the untouched comparison year; no v1
hyperparameter adjustment is allowed after looking at 2026 outcomes.

Historical odds prices are assumed -110 for hypothetical ROI and require
source identity, timestamp and home spread direction verification.
