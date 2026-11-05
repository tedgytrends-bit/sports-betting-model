"""Deterministic unit tests; no historical performance is claimed."""
from cbb.engine import pregame_rows, grade, choose_lines, possessions
from cbb.ingest import windows


def game(i,day,season=2025,hp=80,ap=70):
    return dict(id=i,season=season,startDate=day+"T19:00:00Z",status="final",
                neutralSite=False,homeTeamId=1,awayTeamId=2,
                homeTeam="Home",awayTeam="Away",homePoints=hp,awayPoints=ap)


def test_same_day_games_never_leak():
    rows=pregame_rows([game(1,"2024-11-10",hp=150,ap=60),
                       game(2,"2024-11-10",hp=60,ap=150),
                       game(3,"2024-11-11")])
    assert rows[0]["home_games"]==rows[1]["home_games"]==0
    assert rows[0]["home_off"]==rows[1]["home_off"]==100
    assert rows[2]["home_games"]==2


def test_season_reset():
    a=game(1,"2024-11-10",hp=150,ap=60)
    b=game(2,"2025-11-10",season=2026)
    rows=pregame_rows([a,b])
    assert rows[1]["home_games"]==0
    assert rows[1]["home_off"]==100


def test_home_spread_and_total_pushes():
    rows=[dict(home_points=80,away_points=70,projected_margin_home=13,
               projected_total=160,home_spread=-8.5,market_total=145.5,
               ats_edge=4.5,total_edge=14.5),
          dict(home_points=80,away_points=70,projected_margin_home=13,
               projected_total=160,home_spread=-10,market_total=150,
               ats_edge=3,total_edge=10)]
    ats=grade(rows,0,"ats")
    totals=grade(rows,0,"total")
    assert (ats["wins"],ats["losses"],ats["pushes"])==(1,0,1)
    assert (totals["wins"],totals["losses"],totals["pushes"])==(1,0,1)


def test_source_preference_and_possession_fallback():
    odds=choose_lines([dict(gameId=1,lines=[
        dict(provider="Other",spread=-3,overUnder=None),
        dict(provider="DraftKings",spread=-2.5,overUnder=145)])])
    assert odds["1"]["home_spread"]==-2.5
    assert odds["1"]["market_total"]==145
    assert possessions({"teamStats":{"possessions":71}})==71
    assert len(list(windows(2026)))==8
