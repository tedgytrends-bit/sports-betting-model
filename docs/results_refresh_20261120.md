# Results refresh and chronological game ordering

Both projection cards and the Results tab consume the same automatically graded final-score files. The existing workflow runs after Thursday, Sunday and Monday nights and now also reconciles at 12:15, 13:15 and 14:15 UTC on Fridays, Mondays and Tuesdays. These morning runs include 7:15 a.m. America/Chicago in both daylight and standard time, with retries for source or scheduler delays. A successful grader workflow triggers the Pages deployment through workflow_run, including when its commit uses GITHUB_TOKEN.

The November 19 Houston 26–3 Indianapolis final was retrieved from the explicit FINAL ESPN scoreboard. Injury IND +12.5 is a loss and Under 44 is a win. Results and the projection-card final strips use those same grades. The forecast remains the timestamped pregame version.

Results now keep the newest week first when viewing all weeks, and sort games within each week from earliest to latest kickoff. Thursday precedes Sunday, and Monday comes last. Week 8's original archive has dates but no kickoff times. A separate read-only kickoff CSV reconstructs display chronology from the public nflverse schedule, including the Sunday afternoon windows, without changing the frozen forecast or game grades. Streamlit uses the same supplemental kickoff metadata. Pages stages this file with the results assets.

Regression checks cover Week 8 Thursday/Sunday/Monday ordering, Sunday 4:05-before-4:25 Eastern, and Week 9 TNF-first/MNF-last on desktop and mobile. Both HTML routes bump the results script version so cached Safari JavaScript picks up the new order.
