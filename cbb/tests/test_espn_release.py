from datetime import datetime, timedelta, timezone

import pytest

from cbb.espn_capture_release import CheckoutStore, validate_capture
from cbb.espn_daily_board import MODELS


def test_checkout_retries_preserve_original_freeze(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = CheckoutStore()
    path = "cbb/prospective/2027/frozen/123.json"
    assert store.put_json(path, {"capture":"first"}, True) == "created"
    assert store.put_json(path, {"capture":"later"}, True) == "existing"
    assert store.read_json(path) == {"capture":"first"}


def test_release_rejects_missing_models_stale_tips_and_missing_priors():
    now = datetime.now(timezone.utc)
    game = dict(id="one",tip_utc=(now+timedelta(hours=2)).isoformat(),freeze_candidate=True,
                coverage={"home_prior_matched":10,"away_prior_matched":8},
                rotation_coverage={s:{"past_game_boxes":5} for s in ("home","away")})
    for model in MODELS:
        game[model]=dict(training_games=31259,projected_away_points=75,projected_home_points=70,projected_total=145)
    board = dict(games=[game],source="ESPN",source_sha256={"games":"digest"})
    validate_capture(board, now)
    with pytest.raises(ValueError, match="started"):
        validate_capture(board,now+timedelta(hours=3))
    game["coverage"]["home_prior_matched"]=0
    with pytest.raises(ValueError, match="prior"):
        validate_capture(board,now)
    del game[MODELS[-1]]
    with pytest.raises(KeyError):
        validate_capture(board,now)
