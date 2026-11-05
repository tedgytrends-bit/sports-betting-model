"""Season-local, chronological pregame team model; no future game information used."""
from collections import defaultdict
from dataclasses import dataclass
from math import log
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ("neutral","home_off","home_def","away_off","away_def",
            "home_pace","away_pace","elo_diff","home_games","away_games",
            "home_rest","away_rest")


def number(x):
    try:
        y = float(x)
        return y if np.isfinite(y) else None
    except (ValueError, TypeError):
        return None


def key(g, side):
    return str(g.get(side + "TeamId") or g[side + "Team"])


@dataclass
class Team:
    games: int = 0
    offense: float = 0
    defense: float = 0
    pace: float = 0
    elo: float = 1500
    last_date: str = ""

    def ratings(self):
        n = self.games + 6  # shrink small samples toward neutral efficiency
        return ((self.offense + 600) / n,
                (self.defense + 600) / n,
                (self.pace + 414) / n)


def possessions(box):
    if not box:
        return 69
    stats = box.get("teamStats") or {}
    p = number(stats.get("possessions"))
    if p is None or not 45 <= p <= 110:
        def v(field, detail):
            return number((stats.get(field) or {}).get(detail))
        fga, orb, tov, fta = v("fieldGoals","attempted"),v("rebounds","offensive"),v("turnovers","total"),v("freeThrows","attempted")
        p = fga-orb+tov+.475*fta if None not in (fga,orb,tov,fta) else None
    if p is None or not 45 <= p <= 110:
        p = number(box.get("pace"))
    return p if p is not None and 45 <= p <= 110 else 69


def row_features(game, home, away):
    ho, hd, hp = home.ratings()
    ao, ad, ap = away.ratings()
    day = np.datetime64(game["startDate"][:10])
    hr = (day - np.datetime64(home.last_date)).astype(int) if home.last_date else 8
    ar = (day - np.datetime64(away.last_date)).astype(int) if away.last_date else 8
    neutral = int(bool(game.get("neutralSite")))
    return dict(neutral=neutral,home_off=ho,home_def=hd,away_off=ao,
                away_def=ad,home_pace=hp,away_pace=ap,
                elo_diff=home.elo-away.elo+(0 if neutral else 65),
                home_games=min(home.games,25),away_games=min(away.games,25),
                home_rest=min(max(int(hr),0),8),away_rest=min(max(int(ar),0),8))


def update(game, states, box_lookup):
    h, a = states[key(game,"home")], states[key(game,"away")]
    hs, as_ = number(game.get("homePoints")), number(game.get("awayPoints"))
    if hs is None or as_ is None:
        return
    hbox = box_lookup.get((str(game["id"]),key(game,"home")))
    abox = box_lookup.get((str(game["id"]),key(game,"away")))
    p = (possessions(hbox)+possessions(abox))/2
    he, ae = 100*hs/p, 100*as_/p
    h.offense+=he; h.defense+=ae; h.pace+=p; h.games+=1
    a.offense+=ae; a.defense+=he; a.pace+=p; a.games+=1
    h.last_date=a.last_date=game["startDate"][:10]
    expected=1/(1+10**((a.elo-h.elo-(0 if game.get("neutralSite") else 65))/400))
    result=1 if hs>as_ else .5 if hs==as_ else 0
    shift=22*min(2.5,.7+log(1+abs(hs-as_))/3)*(result-expected)
    h.elo+=shift; a.elo-=shift


def pregame_rows(games, boxes=None):
    """Freeze features for a whole day BEFORE applying any games that day."""
    look={(str(b["gameId"]),str(b.get("teamId") or b.get("team"))):b for b in (boxes or [])}
    by_day=defaultdict(list)
    for g in games:
        if g.get("status") in ("final","scheduled"):
            by_day[(int(g["season"]),g["startDate"][:10])].append(g)
    state=defaultdict(Team)
    output=[]
    for (season, day), today in sorted(by_day.items()):
        local={t:state[f"{season}:{t}"] for g in today for t in (key(g,"home"),key(g,"away"))}
        for g in today:
            h,a=local[key(g,"home")],local[key(g,"away")]
            output.append({**row_features(g,h,a),"id":str(g["id"]),"season":season,
                           "date":day,"start_date":g["startDate"],"home":g["homeTeam"],
                           "away":g["awayTeam"],"status":g["status"],
                           "home_points":number(g.get("homePoints")),
                           "away_points":number(g.get("awayPoints"))})
        for g in today:
            if g["status"]=="final":
                update(g,local,look)
    return output


def choose_lines(lines):
    """Spread is ASSUMED to be signed HOME spread; verify convention with sportsbook."""
    choices={}
    pref=["DraftKings","FanDuel","Bovada","BetMGM","Caesars"]
    for g in lines:
        avail=[x for x in (g.get("lines") or [])
               if number(x.get("spread")) is not None or number(x.get("overUnder")) is not None]
        avail.sort(key=lambda x:(pref.index(x.get("provider")) if x.get("provider") in pref else 99,str(x.get("provider"))))
        if avail:
            x=avail[0]
            choices[str(g["gameId"])]=dict(provider=x.get("provider"),
                home_spread=number(x.get("spread")),market_total=number(x.get("overUnder")))
    return choices


def predict(rows, season, lines):
    prior=[r for r in rows if r["season"]<season and r["home_points"] is not None and r["away_points"] is not None]
    target=[r for r in rows if r["season"]==season]
    if len(prior)<30:
        raise ValueError(f"Need >=30 training games before season {season}; found {len(prior)}")
    if not target:
        return []
    train=np.array([[r[k] for k in FEATURES] for r in prior])
    test=np.array([[r[k] for k in FEATURES] for r in target])
    results=[]
    for y in ("margin","total"):
        actual=np.array([(r["home_points"]-r["away_points"] if y=="margin" else r["home_points"]+r["away_points"]) for r in prior])
        model=make_pipeline(StandardScaler(),Ridge(alpha=150))
        model.fit(train,actual)
        results.append(model.predict(test))
    output=[]
    for r, margin, total in zip(target,*results):
        market=lines.get(r["id"],{})
        s,ou=market.get("home_spread"),market.get("market_total")
        ats=float(margin)+s if s is not None else None
        over=float(total)-ou if ou is not None else None
        output.append({**r,**market,"training_games":len(prior),
            "projected_margin_home":round(float(margin),3),
            "projected_total":round(float(total),3),
            "projected_home_points":round(float((total+margin)/2),2),
            "projected_away_points":round(float((total-margin)/2),2),
            "ats_edge":round(ats,3) if ats is not None else None,
            "total_edge":round(over,3) if over is not None else None,
            "ats_lean":("home" if ats>0 else "away" if ats<0 else "none") if ats is not None else "",
            "total_lean":("over" if over>0 else "under" if over<0 else "none") if over is not None else ""})
    return output


def grade(rows, threshold, kind):
    assert kind in ("ats","total")
    decisions=[]; model_err=[]; market_err=[]
    for r in rows:
        h,a=r["home_points"],r["away_points"]
        if h is None or a is None:
            continue
        actual=h-a if kind=="ats" else h+a
        forecast=r["projected_margin_home"] if kind=="ats" else r["projected_total"]
        model_err.append(abs(actual-forecast))
        market=r.get("home_spread") if kind=="ats" else r.get("market_total")
        edge=r.get("ats_edge") if kind=="ats" else r.get("total_edge")
        if market is None or edge is None:
            continue
        market_err.append(abs(actual-(-market if kind=="ats" else market)))
        if abs(edge)<threshold or edge==0:
            continue
        result=(actual+market if kind=="ats" else actual-market)*(1 if edge>0 else -1)
        decisions.append("W" if result>0 else "L" if result<0 else "P")
    w,l,p=(decisions.count(c) for c in ("W","L","P"))
    n=len(decisions)
    return dict(market=kind,threshold=threshold,bets=n,wins=w,losses=l,pushes=p,
                win_rate_ex_push=round(w/(w+l),4) if w+l else None,
                roi_at_minus_110=round((w*100/110-l)/n,4) if n else None,
                model_mae_all=round(float(np.mean(model_err)),3) if model_err else None,
                market_mae_covered=round(float(np.mean(market_err)),3) if market_err else None,
                games_with_lines=len(market_err))
