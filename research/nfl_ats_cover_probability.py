"""Season-forward cover probabilities from archived fixed-fit forecasts."""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ARCHIVE = Path(__file__).resolve().parent / "reports/nfl_ats_injury_ablation_20261117"
FEATURES = {
    "Market only": ["spread_line"],
    "Market + Injury": ["spread_line", "full_edge"],
    "Market + separated adjustments": ["spread_line", "base_edge", "nonqb_delta", "qb_margin_adjustment"],
}
THRESHOLD = 0.55


def forecast(games):
    g = games.copy()
    g["cover_margin"] = g.actual_margin - g.spread_line
    g["home_cover"] = g.cover_margin.gt(0).astype(int)
    g["full_edge"] = g.nonqb_on_qb_on - g.spread_line
    g["base_edge"] = g.nonqb_off_qb_off - g.spread_line
    g["nonqb_delta"] = g.nonqb_on_qb_off - g.nonqb_off_qb_off
    outputs = []
    for season in (2024, 2025, 2026):
        train = g.loc[g.season.lt(season) & g.cover_margin.ne(0)]
        test = g.loc[g.season.eq(season)].copy()
        test["Flat 50%"] = 0.5
        for name, columns in FEATURES.items():
            model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0))
            model.fit(train[columns], train.home_cover)
            test[name] = model.predict_proba(test[columns])[:, 1]
        outputs.append(test)
    return pd.concat(outputs, ignore_index=True)


def summarize(predictions):
    rows = []
    for season, games in [*predictions.groupby("season"), ("Pooled", predictions)]:
        graded = games.cover_margin.ne(0)
        for name in ("Flat 50%", *FEATURES):
            probability = games[name]
            pick = np.select(
                [probability.ge(THRESHOLD), probability.le(1 - THRESHOLD)], [1, -1], default=0
            )
            result = pick * np.sign(games.cover_margin)
            wins = int((result == 1).sum())
            losses = int((result == -1).sum())
            actions = int(np.count_nonzero(pick))
            rows.append(dict(
                season=season, model=name, games=len(games),
                brier=brier_score_loss(games.loc[graded, "home_cover"], probability[graded]),
                log_loss=log_loss(games.loc[graded, "home_cover"], probability[graded]),
                wins=wins, losses=losses, pushes=actions - wins - losses,
                roi_pct=100 * (wins / 1.1 - losses) / actions if actions else np.nan,
            ))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(summarize(forecast(pd.read_csv(ARCHIVE / "games.csv"))).to_string(index=False))
