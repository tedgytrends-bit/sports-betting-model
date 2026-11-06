"""Rendering and publishing CBB research summary without network access."""
import base64

from cbb.performance_report import generate_performance_report
from cbb.prospective_publish import GitHubStore
from cbb.readable_report import render_markdown, pick_record, roi

from datetime import datetime, timezone


def mock_scorecard():
    score = {"games_with_model":1,"selections":1,
             "wins":1,"losses":0,"pushes":0,
             "roi_minus_110_pct":90.91,
             "model_mae_points":8.5}
    empty = {"games_with_model":0,"selections":0,
             "wins":0,"losses":0,"pushes":0,
             "roi_minus_110_pct":None,
             "model_mae_points":None}
    models = ("baseline","player_v2","player_opp_v3",
              "player_rot_v4","player_all_v4")
    d={}
    for key in models:
        result = score if key in ("baseline","player_v2") else empty
        d[key]={"ats":{"0":result,"3.5":result},
                "total":{"0":result,"3.5":result}}
    return d


def sample_report():
    template=mock_scorecard()
    return dict(
        type="cbb_prospective_research_performance",
        season=2027,as_of_utc="2026-11-06T20:08:00Z",
        tracked_games=1,
        completed_untracked_since_first_capture=3,
        invalid_frozen_records=0,
        all_tracked=template,
        last_48_hours={"tracked_games":1,"models":template},
        last_7_days={"tracked_games":1,"models":template},
        daily_by_central_date=[{
            "date_central":"2026-11-05",
            "completed_tracked_games":1,
            "models":template,
        }],
        paired_model_accuracy_vs_baseline=[{
            "model": m,"paired_games":1 if m=="player_v2" else 0,
            "ats_mae_improvement_vs_baseline":2 if m=="player_v2" else None,
            "total_mae_improvement_vs_baseline":-1 if m=="player_v2" else None,
        } for m in ("player_v2","player_opp_v3","player_rot_v4","player_all_v4")],
        most_recent_60_games=[{
            "date_central":"2026-11-05","game":"Away @ Home",
            "final_score":"75-80","frozen_home_spread":-3.5,
            "frozen_total":160.5,
            "models":{"player_v2":{"ats":"W","total":"L"}},
        }],
    )


def test_readable_scorecard_has_explicit_directional_and_filtered_and_recent():
    content=render_markdown(sample_report())
    assert "November 06, 2026" in content
    assert "Team baseline" in content and "Player v2" in content
    assert "25-17" not in content  # zero hard-coded season records
    assert "+90.91%" in content
    assert "1-0" in content
    assert "2026-11-05" in content
    assert "Past 48 hours" in content
    assert "at least 3.5 points" in content
    assert "0" in content and "3" in content
    assert "Away @ Home" in content
    assert "were added after" in content.lower()
    assert "[Machine-readable review](performance_report.json)" in content


def test_empty_records_no_implied_losses_or_wins():
    report=sample_report()
    report["tracked_games"]=0
    report["most_recent_60_games"]=[]
    for model in report["all_tracked"]:
        report["all_tracked"][model]={"ats":{"0":mock_scorecard()["player_all_v4"]["ats"]["0"],
                                            "3.5":mock_scorecard()["player_all_v4"]["ats"]["3.5"]},
                                      "total":{"0":mock_scorecard()["player_all_v4"]["total"]["0"],
                                               "3.5":mock_scorecard()["player_all_v4"]["total"]["3.5"]}}
    content=render_markdown(report)
    assert "Tracked completed games:** 0" in content
    assert "| Team baseline | — | — | — | — | — | — |" in content


def test_github_text_publisher_base64_preserves_markdown(monkeypatch):
    store=GitHubStore("example/repo","data-only","unit-test-only")
    received={}
    def sha(path):
        return None
    class Response:
        ok=True
        status_code=201
        def raise_for_status(self):
            return None
    def fake_put(url,json,timeout):
        received["url"]=url
        received["branch"]=json["branch"]
        received["content"]=base64.b64decode(json["content"]).decode()
        return Response()
    monkeypatch.setattr(store,"existing_sha",sha)
    monkeypatch.setattr(store.session,"put",fake_put)
    outcome=store.put_text("cbb/prospective/2027/README.md","# Model report\n",immutable=False)
    assert outcome=="created"
    assert received["branch"]=="data-only"
    assert received["content"]=="# Model report\n"
