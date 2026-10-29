import pandas as pd

from injury_model import add_injury_features


def test_injury_features_use_only_pregame_rows_and_deduplicate_players():
    schedule = pd.DataFrame([
        {
            "game_id": "HIST1", "season": 2025, "week": 3, "gameday": "2025-09-18",
            "gametime": "20:15", "game_type": "REG", "home_team": "BUF", "away_team": "MIA",
            "home_score": 24, "away_score": 17,
        }
    ])
    dataset = pd.DataFrame([
        {
            "game_id": "HIST1", "season": 2025, "week": 3, "gameday": pd.Timestamp("2025-09-18"),
            "home_team": "BUF", "away_team": "MIA", "home_score": 24, "away_score": 17,
            "sample_feature": 1.0,
        }
    ])
    reports = pd.DataFrame([
        {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
         "player_name": "QB One", "report_status": "QUESTIONABLE", "practice_status": "LIMITED",
         "date_modified": "2025-09-18T15:00:00Z"},
        # Later pregame update for the same player replaces the earlier row.
        {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
         "player_name": "QB One", "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
         "date_modified": "2025-09-18T18:00:00Z"},
        # This update happened after kickoff and must not leak into the features.
        {"season": 2025, "week": 3, "season_type": "REG", "team": "BUF", "position": "QB",
         "player_name": "QB Two", "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
         "date_modified": "2025-09-19T02:00:00Z"},
        {"season": 2025, "week": 3, "season_type": "REG", "team": "MIA", "position": "OT",
         "player_name": "Tackle One", "report_status": "OUT", "practice_status": "DID NOT PARTICIPATE",
         "date_modified": "2025-09-18T18:00:00Z"},
    ])

    result = add_injury_features(dataset, schedule, reports).iloc[0]
    assert result["home_injury_report_available"] == 1
    assert result["away_injury_report_available"] == 1
    assert result["home_qb_out"] == 1
    assert result["home_qb_questionable"] == 0
    assert result["away_ol_out"] == 1
    assert result["home_inj_out"] == 1
