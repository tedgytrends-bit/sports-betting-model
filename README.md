Sports Model --- NFL Projections
A Streamlit dashboard and experimental NFL score-projection project. The
goal is to build a transparent, repeatable data pipeline and evaluate
projections on games not used to fit the model.

Current code version: v0.6.2
Important status
This is not a validated betting model. Historical backtests are
exploratory and do not establish a repeatable betting edge. Do not use
backtest results as a guarantee of future performance or advertise them
as proof of profitability.

The public upcoming-game projection board currently uses a simple
recent-scoring baseline. The historical efficiency model is evaluated
separately; do not assume every feature used in the historical model is
automatically applied to the public projection board.
What is included
- app.py: Streamlit dashboard for upcoming projections, model
  comparison, feature/data-quality checks, and historical backtesting.
- model.py: Data loading, feature engineering, projection, and
  chronological evaluation utilities.
- requirements.txt: Python dependencies.
- .gitignore: Excludes local environment files and other files that
  should not be committed.
Models and inputs
Public upcoming-game baseline
The public projection board uses recent points scored blended with the
opponent's recent points allowed, with a fixed 1.5-point home
adjustment. Its default scoring lookback is six recent games.

This baseline does not automatically adjust for current injuries,
quarterback availability, weather, rest, or live sportsbook odds.
Historical efficiency model
The historical model is designed to use play-by-play-derived team
features, including:
- Offensive EPA per play and offensive success rate.
- Defensive EPA allowed and defensive success rate allowed.
- Offensive-versus-opponent defensive matchup features.
- Pace/plays-per-game features.
- Rest and scheduling features.
- Red-zone touchdown-play-rate and turnover-rate features when the
  required source data are available.
The historical model uses Ridge regression and
chronological/walk-forward evaluation. Its recent-team-game lookback is
configurable; the current default is 10 games.

A feature being listed in the code does not by itself prove that it was
populated correctly or contributed to a given run. Review the
feature/data-quality audit for missingness, constant values, and
plausible ranges before interpreting model results. In particular,
verify red-zone and turnover fields against the live data output after
each relevant code update.
Injury and weather limitations
The selected-matchup preview includes manual scenario controls for
player-group availability and severe weather. These are exploratory
adjustments, not an automatically verified injury feed and not
empirically validated point values.

The historical backtest does not yet provide a fully validated,
point-in-time injury-adjusted evaluation. Any future injury integration
must use information that was available before each historical kickoff;
using later injury updates would introduce hindsight bias.

Weather adjustments should be limited to severe conditions and tested
before being treated as predictive. Manual scenario controls should not
be confused with automatic adjustments to every game on the public
projection board.
Run it locally
1. Install Python 3.11 or newer from
   https://www.python.org/downloads/.
2. Open Terminal (Mac) or PowerShell (Windows).
3. Change into the project folder:
   cd sports_model_starter
4. Create a virtual environment:
   python -m venv .venv
5. Activate it:
   - Mac: source .venv/bin/activate
   - Windows PowerShell: .venv\Scripts\Activate.ps1
6. Install dependencies:
   pip install -r requirements.txt
7. Launch the dashboard:
   streamlit run app.py
Backtesting and settings
- Keep the recent-team-game lookback at 10 for the first comparison,
  then change one setting at a time.
- Compare models on the same chronological test games.
- Review home-score, away-score, and combined-total prediction errors.
  Lower mean absolute error (MAE) is better.
- Keep score-prediction accuracy separate from betting performance.
- For betting simulations, document the market-line source, odds/juice
  assumptions, push handling, and ROI denominator.
- A recorded closing total is not necessarily the exact line or price
  available at a particular sportsbook when a pick would have been
  placed.
- Historical thresholds selected after inspecting results are subject
  to selection bias. Treat them as exploratory until tested on
  untouched data and then prospectively.
Data and integrity rules
- Never use information published after kickoff to make a pregame
  prediction.
- Build every feature from information available before the target
  game's kickoff. For same-day games, verify whether earlier games
  have actually finished before using their data.
- Fit imputation, scaling, and other learned preprocessing using
  training data only; apply those fitted transformations to the test
  data.
- Save original timestamped projections and the market line/odds
  available at publication; do not overwrite them after the result.
- Track all games in the stated scope, including no-bet games, so
  denominators remain clear.
- Keep historical backtest results separate from live prospective
  results.
- Report pushes separately and include odds/juice when calculating
  ROI.
- Check feature availability and value ranges before trusting model
  metrics. A missing feature is not evidence of a zero value.
- Treat injury, weather, pace, red-zone, turnover, and scheduling
  features as hypotheses to test---not guaranteed improvements.
Recommended next steps
1. Verify the live data pipeline and feature audit, especially red-zone
   and turnover calculations.
2. Compare the current efficiency model with the existing baseline on
   identical chronological test games.
3. Add reliable pregame injury data, including quarterback, offensive
   line, skill positions, defensive front, secondary, and kicker
   availability, only when historically point-in-time data can be
   established.
4. Test additions one at a time and retain them only if they improve
   out-of-sample predictions.
5. Start a prospective record that freezes predictions, timestamps,
   market lines, and odds before kickoff.
6. Do not describe the model as profitable unless an adequate untouched
   and prospective record supports that conclusion.
