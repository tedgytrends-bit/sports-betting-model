# Sports Model — NFL Starter

This is a starter project for building a transparent NFL score-projection model and public dashboard.

## Important status
This is **not a validated betting model** and the example game rows are fictional placeholders. Do not use them to place bets or advertise performance. The first milestone is to build a repeatable data pipeline and evaluate predictions on games not used to fit the model.

## What is included
- `app.py`: simple Streamlit dashboard layout with sample rows.
- `model.py`: starter utilities for converting projected team points into spread/total and comparing with market lines.
- `requirements.txt`: Python dependencies.
- `.gitignore`: avoids committing local environment files.

## Run it locally
1. Install Python 3.11 or newer from https://www.python.org/downloads/
2. Open Terminal (Mac) or PowerShell (Windows).
3. Unzip this folder and change into it:
   ```bash
   cd sports_model_starter
   ```
4. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```
   Activate it:
   - Mac: `source .venv/bin/activate`
   - Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
5. Install packages:
   ```bash
   pip install -r requirements.txt
   ```
6. Launch the dashboard:
   ```bash
   streamlit run app.py
   ```

## Planned next steps
1. Select a permitted historical/live odds provider.
2. Load historical NFL play-by-play data (nflverse is one candidate).
3. Build point-in-time features that only use information available before kickoff.
4. Fit a baseline model and evaluate it using chronological/walk-forward tests.
5. Freeze predictions before kickoff and log every game, market line, timestamp, and outcome.
6. Replace sample dashboard rows with the validated model output.
7. Deploy after the local prototype and data pipeline work.

## Non-negotiable integrity rules
- Never use information published after kickoff to make a pregame prediction.
- Save the original timestamped projection and line; don't overwrite it after the result.
- Track every game in the stated scope, including passes/no-bet games, so the denominator is clear.
- Keep backtest results separate from live prospective results.
- Report ATS pushes separately and include odds/juice when calculating ROI.
