from datetime import datetime, timezone

from cbb.ats_diagnostic import MODELS, metrics, score, walk_forward


def test_home_spread_grading_and_push_denominator():
    game = {"spread": -5, "actual": 5}
    rows = [(game, score(game, "home"), 6), (game, "W", 3), (game, None, 5)]
    result = metrics(rows)
    assert result["games"] == 3
    assert result["selections"] == 2
    assert result["pushes"] == 1
    assert result["win_rate_pct"] == 100
    assert round(result["roi_minus_110_pct"], 2) == 45.45
    assert result["signed_home_residual"] == -1 / 3


def test_walk_forward_excludes_finals_unavailable_at_the_first_freeze():
    def stamp(day, hour):
        return datetime(2026, 11, day, hour, tzinfo=timezone.utc)

    def make_game(ident, day, available, actual):
        return dict(id=ident, day=f"2026-11-{day}", available=available,
                    capture=stamp(day, 10), actual=actual, spread=-4,
                    preds=dict.fromkeys(MODELS, 8), edges=dict.fromkeys(MODELS, 4),
                    picks=dict.fromkeys(MODELS, "home"))

    earlier = [make_game(i, 10 + i % 2, stamp(12, 9), 7) for i in range(75)]
    earlier.append(make_game(75, 11, stamp(12, 10), 100))
    test = make_game(76, 12, stamp(13, 9), 8)
    audit = walk_forward([*earlier, test])
    assert len(audit["folds"]) == 1
    assert audit["folds"][0]["train_games"] == 75
    assert audit["folds"][0]["fitted_intercepts"] == dict.fromkeys(MODELS, 0)
