# Week 11 publication

Initial Thursday release uses all 13 Bovada quotes supplied November 19 at approximately 1:11 p.m. Central. The user will supply Sunday morning updates. Both the existing Baseline and Injury projections were calculated using completed games through Week 10, the existing Ridge parameters, and the latest timestamped Week 11 injury snapshot. The QB adjustment preserves the non-QB total.

All 26 projected quarterbacks passed the current Week 11 active-roster check. Arizona's schedule listing of Gardner Minshew and Baltimore's listing of Tyler Huntley were stale. Current team reports support Carson Beck and Jacoby Brissett preparing as the expected quarterbacks. All starters remain provisional for this initial board. Beck and Miami's Kyle McCord have insufficient prior dropback samples under the existing model label.

Sources reviewed November 19:
- https://www.azcardinals.com/news/injury-report-week-11-vs-chiefs
- https://www.baltimoreravens.com/news/transcript-press-conferences-11-18-26
- https://www.houstontexans.com/news/week-11-injury-report-texans-vs-colts
- https://www.colts.com/news/colts-rule-out-5-players-for-week-11-thursday-night-football-game-vs-houston-texans
- https://media.nfl.com/news-and-releases/week-11-schedule-change--jaguars-giants-to-4-25-p-m--et--steeler

The TNF final injury report includes four Houston OUT designations and five Indianapolis OUT designations. Inactives are released closer to kickoff. The NFL flex announcement supersedes the stale schedule for PIT–PHI (1 p.m. Eastern) and JAX–NYG (4:25 p.m. Eastern). The display and frozen kickoff metadata follow those official times.

The release is at data/public_snapshots/nfl_week11_initial_projections_2026-11-19.csv with an input-hash manifest and QB roster audit. This preserves the QB-on and non-QB score base for paired research at the same Bovada quote. The existing results generator added 26 pending model rows for 13 games. Every prior Week 8–10 game row matches field-for-field. Sunday updates should be new timestamped score and market captures. Preserve TNF and this initial snapshot.

Validation before publication passed 156 Python tests, projected-score arithmetic and injury-total invariants, pre-kickoff and quote timestamps, all 26 roster assignments, complete 13-game/two-model coverage, and previous-result immutability. No paid NFLMeta or EndzoneAPI requests.
