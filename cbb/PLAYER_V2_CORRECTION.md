# Correcting CBBD roster-season alignment (player v2)

**Reason:** v1 erroneously treated season=2026 as requiring startSeason<=2025 and endSeason>=2026. CBBD **startSeason and endSeason** are identifiers for the basketball season's ENDING YEAR, not the autumn calendar year. The correct membership guard for season S is **startSeason <= S <= endSeason**.

Authenticated provider evidence from 2026 /stats/player/season and /teams/roster:
- **2026:2026** roster cohort: 2,364 listed; 2,151 have recorded 2025-26 player stats; 198 matched 2025 recruits; 761 matched incoming transfer records.
- **2026:2027** cohort: 1,187 listed; 938 have recorded 2025-26 player stats; 229 recruit matches; 203 transfer matches.
- **2025:2026** cohort: 889 listed; 833 have recorded 2025-26 player stats.

The old guard excluded the first two groups, which can include legitimate 2025–26 players. That suppression explains the first player's model zero recruiting/portal matches in its recorded audit.

The v2 guard includes players whose starting season equals the target. It still excludes future memberships, missing dates and graduated entries. Historical rosters remain a *retrospective proxy* rather than verified pregame rosters. Historical ROI at -110 is hypothetical. v1's historical output remains preserved in the earlier [audit](PLAYER_V1_AUDIT_2024_2026.md) but should not be interpreted as a fully implemented transfer/freshman model.

The fixed team-only baseline remains the comparison standard. V2 writes to a new results directory, not overwriting v1 artifacts.
