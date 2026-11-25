"""Version the derived historical training rows so Actions cache eviction is recoverable."""
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cbb.engine import choose_lines, pregame_rows, predict
from cbb.live_rotation import load_live_player_boxes
from cbb.opponent_adjusted import ADJ_FEATURES, attach_adjustments, pregame_opponent_adjustments
from cbb.opponent_experiment import fitted_predictions
from cbb.player_adjusted import PLAYER_FEATURES, extend_rows, player_predictions
from cbb.rotation_features import ROTATION_FEATURES, attach_rotations, pregame_rotation_features

ROOT = Path("archive/cbb/prospective/2027/model_inputs")
BANK = ROOT / "historical_features.npz"
STATE = ROOT / "team_priors.json"
INDEX = ROOT / "team_game_index.json.gz"
COLUMNS = tuple(dict.fromkeys(("season","home_points","away_points",*PLAYER_FEATURES,*ADJ_FEATURES,*ROTATION_FEATURES)))


def save_derived(rows, priors, season):
    ROOT.mkdir(parents=True,exist_ok=True)
    if not BANK.exists():
        matrix = np.asarray([[r[k] for k in COLUMNS] for r in rows
                             if r["season"]<season and r["home_points"] is not None and r["away_points"] is not None])
        if not np.isfinite(matrix).all() or len(matrix)<1000:
            raise ValueError("Invalid historical training feature checkpoint")
        np.savez_compressed(BANK, columns=np.array(COLUMNS),rows=matrix)
    state = {"season":season, "prior_as_of":datetime.now(timezone.utc).isoformat(),
             "historical_sha256":hashlib.sha256(BANK.read_bytes()).hexdigest(),
             "priors":{tid:v for (s,tid),v in priors.items() if s==season}}
    STATE.write_text(json.dumps(state, allow_nan=False, separators=(",",":"))+"\n")


def save_index(old):
    if INDEX.exists() or not old:
        return
    ROOT.mkdir(parents=True,exist_ok=True)
    keys=("id","startDate","homeTeamId","awayTeamId","homeTeam","awayTeam")
    with gzip.open(INDEX,"wt") as f:
        json.dump([{k:g[k] for k in keys} for g in old],f,separators=(",",":"))


def replay(raw, rotation, season, now):
    from cbb.prospective import build_capture
    state=json.loads(STATE.read_text())
    digest=hashlib.sha256(BANK.read_bytes()).hexdigest()
    if digest!=state["historical_sha256"] or state["season"]!=season:
        raise ValueError("Training checkpoint integrity mismatch")
    with np.load(BANK,allow_pickle=False) as bank:
        if tuple(bank["columns"])!=COLUMNS:
            raise ValueError("Training feature definition changed")
        historical=[dict(zip(COLUMNS,row)) for row in bank["rows"]]
    inputs={k:json.loads((raw/(k+".json")).read_text()) for k in ("games","boxes","lines")}
    games, boxes=inputs["games"],inputs["boxes"]
    priors={(season,k):v for k,v in state["priors"].items()}
    current=extend_rows(pregame_rows(games,boxes),games,priors)
    current=attach_adjustments(current,pregame_opponent_adjustments(games,boxes))
    current=attach_rotations(current,pregame_rotation_features(games,load_live_player_boxes(season,rotation)))
    rows=historical+current
    lines=choose_lines(inputs["lines"])
    def fit(features,label):
        return fitted_predictions(rows,season,lines,features,250,label)
    fingerprints={k:hashlib.sha256((raw/(k+".json")).read_bytes()).hexdigest() for k in inputs}
    fingerprints["historical_features"]=digest
    fingerprints["team_priors"]=hashlib.sha256(STATE.read_bytes()).hexdigest()
    fingerprints["rotations"]=hashlib.sha256((Path(rotation)/f"{season}_game_players.json.gz").read_bytes()).hexdigest()
    board=build_capture(predict(rows,season,lines),player_predictions(rows,season,lines),games,priors,now,
        season=season,fingerprints=fingerprints,model_commit=os.getenv("GITHUB_SHA",""),
        opponent_player=fit(PLAYER_FEATURES+ADJ_FEATURES,"player_opp_v3"),
        rotation_player=fit(PLAYER_FEATURES+ROTATION_FEATURES,"player_rot_v4"),
        combined_player=fit(PLAYER_FEATURES+ADJ_FEATURES+ROTATION_FEATURES,"player_all_v4"))
    board["source"]="ESPN schedules, markets and rotation boxes; versioned historical features and team priors from "+state["prior_as_of"]
    return board


def main():
    from cbb.espn_daily_board import MODELS
    from cbb.prospective import utc_date
    path=Path("cbb/outputs/prospective/latest_capture.json")
    original=json.loads(path.read_text()) if path.exists() else None
    now=utc_date(original["capture_utc"]) if original else datetime.now(timezone.utc)
    result=replay(Path("cbb/data/raw/2027"),"cbb/data/rotation_live",2027,now)
    if original:
        expected={str(g["id"]):g for g in original["games"]}
        if set(expected)!={str(g["id"]) for g in result["games"]}:
            raise ValueError("Replay changed the forecast slate")
        for g in result["games"]:
            for model in MODELS:
                if g[model]!=expected[str(g["id"])][model]:
                    raise ValueError(f"Checkpoint replay disagrees for {g['id']} {model}")
        print("Verified identical checkpoint predictions",len(expected)*len(MODELS))
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,allow_nan=False))


if __name__=="__main__":
    main()
