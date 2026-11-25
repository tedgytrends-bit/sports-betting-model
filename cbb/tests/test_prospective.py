"""Pure deterministic tests of the shadow prospective audit and freeze rules."""
from datetime import datetime, timezone, timedelta

import pytest

from cbb.prospective import build_capture, utc_date
from cbb.prospective_publish import publish, validate


NOW=datetime(2026,11,5,20,0,0,tzinfo=timezone.utc)


def record(i,tip,status="scheduled",spread=-3.5,total=142.5):
    return dict(id=str(i),season=2027,status=status,
      start_date=tip,away="Away",home="Home",away_games=0,home_games=0,
      neutral=0,provider="Bovada",home_spread=spread,market_total=total,
      projected_margin_home=5.0,projected_total=141.0,
      projected_home_points=73.0,projected_away_points=68.0,
      ats_edge=1.5 if spread is not None else None,
      total_edge=-1.5 if total is not None else None,
      ats_lean="home" if spread is not None else "",
      total_lean="under" if total is not None else "",
      training_games=1000)


def games(rows):
    return [dict(id=int(r["id"]),season=2027,status=r["status"],
       startDate=r["start_date"],homeTeamId=1,awayTeamId=2)
       for r in rows]


def captured(rows,priors=None):
    return build_capture(rows,rows,games(rows),priors or {},NOW,
                         season=2027,horizon_days=8,freeze_hours=24,
                         fingerprints={"rosters.json":"abc"},model_commit="123")


def iso(hours):
    return (NOW+timedelta(hours=hours)).isoformat().replace("+00:00","Z")


def test_filters_stale_scheduled_and_completed_events():
    rows=[record(1,iso(-1)),record(2,iso(1)),record(3,iso(2),status="final"),
          record(4,iso(24*9)),record(5,iso(2),spread=None,total=None)]
    c=captured(rows)
    assert {g["id"] for g in c["games"]}=={"2","5"}
    assert c["counts"]["freeze_candidates"]==1
    assert c["counts"]["with_ats_line"]==1
    assert c["counts"]["with_total_line"]==1
    assert c["games"][0]["freeze_candidate"] is True
    assert c["games"][1]["freeze_candidate"] is False


def test_coverage_flag_and_model_projection():
    r=record(2,iso(2))
    p={(2027,"1"):dict(matched_players=4,eligible_players=12,
                        portal_verified=2,elite_freshmen=1),
       (2027,"2"):dict(matched_players=2,eligible_players=12)}
    c=captured([r],p)
    assert c["games"][0]["research_quality"]=="limited"
    assert c["games"][0]["coverage"]["home_verified_portal"]==2
    assert c["games"][0]["baseline"]["projected_total"]==141
    assert c["games"][0]["player_v2"]["training_games"]==1000
    assert c["source_sha256"]["rosters.json"]=="abc"


def test_rejects_duplicate_ids_and_timestamp_without_timezone():
    rows=[record(2,iso(2))]
    with pytest.raises(ValueError,match="Duplicate"):
        captured(rows+rows)
    with pytest.raises(ValueError,match="UTC offset"):
        utc_date("2026-11-05T20:00:00")


class MemoryStore:
    def __init__(self):
        self.files={}
        self.branch="cbb-prospective"

    def put_json(self,path,body,immutable=True):
        if path in self.files and immutable:
            return "existing"
        action="created" if path not in self.files else "updated"
        self.files[path]=body
        return action

    def put_text(self,path,content,immutable=False):
        if path in self.files and immutable:
            return "existing"
        action="created" if path not in self.files else "updated"
        self.files[path]=content
        return action


def test_frozen_is_immutable_but_latest_updates():
    store=MemoryStore()
    c=captured([record(2,iso(2))])
    assert validate(c)==2027
    publish(c,store,"test1")
    path="cbb/prospective/2027/frozen/2.json"
    original=store.files[path]
    c2={**c,"capture_utc":"2026-11-05T20:30:00Z"}
    c2["games"]=[{**c2["games"][0], "player_v2":{"projected_total":150}}]
    publish(c2,store,"test2")
    assert store.files[path] is original
    assert store.files["cbb/prospective/2027/latest.json"]["capture_utc"]=="2026-11-05T20:30:00Z"
    assert len([p for p in store.files if "/snapshots/" in p])==2


def test_rejects_backdated_games_on_publication():
    c=captured([record(2,iso(2))])
    c["games"][0]["tip_utc"]="2026-11-04T20:00:00Z"
    with pytest.raises(ValueError,match="past games"):
        validate(c)
