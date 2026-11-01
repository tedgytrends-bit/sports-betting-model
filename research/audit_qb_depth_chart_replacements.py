#!/usr/bin/env python3
"""Audit historical QB depth-chart replacement coverage (research only).

Joins NFL injury-report QB rows to nflverse weekly depth charts for 2021-2024.
For 2025+ the source schema changed to timestamped ESPN depth-chart snapshots;
those seasons are reported separately and are not silently mixed into weekly data.
This script does not create model features or point adjustments.
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json, sys
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
HEADERS = {"User-Agent": "sports-betting-model-qb-depth-chart-audit/1.0"}

def load_depth(season: int) -> pd.DataFrame:
    url = f"https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.parquet"
    response = requests.get(url, headers=HEADERS, timeout=(15, 120))
    response.raise_for_status()
    return pd.read_parquet(BytesIO(response.content), engine="pyarrow")

def main() -> None:
    from injury_model import load_injury_reports, _normalize_reports
    injuries = _normalize_reports(load_injury_reports(SEASONS))
    injuries["season"] = pd.to_numeric(injuries["season"], errors="coerce")
    injuries["week"] = pd.to_numeric(injuries["week"], errors="coerce")
    injuries["team"] = injuries["team"].astype("string").str.upper().str.strip()
    injuries["position"] = injuries["position"].astype("string").str.upper().str.strip()
    injuries["gsis_id"] = injuries["gsis_id"].astype("string").str.strip()
    qbs = injuries[injuries["position"].eq("QB")].dropna(subset=["season","week","team","gsis_id"]).copy()
    qbs["season"] = qbs["season"].astype(int); qbs["week"] = qbs["week"].astype(int)
    outputs=[]; errors=[]
    for season in SEASONS:
        try:
            depth=load_depth(season)
            if season <= 2024:
                required={"season","week","club_code","gsis_id","position","depth_team"}
                missing=required-set(depth.columns)
                if missing: raise ValueError(f"Legacy depth chart missing {sorted(missing)}")
                d=depth[(depth["position"].astype(str).str.upper()=="QB")].copy()
                d["team"]=d["club_code"].astype("string").str.upper().str.strip()
                d["player_id"]=d["gsis_id"].astype("string").str.strip()
                # depth_position is typically QB1/QB2/QB3; preserve raw rank text.
                d["depth_rank"]=pd.to_numeric(d["depth_team"],errors="coerce")
                d["season"]=pd.to_numeric(d["season"],errors="coerce")
                d["week"]=pd.to_numeric(d["week"],errors="coerce")
                d=d[["season","week","team","player_id","depth_rank","full_name"]].drop_duplicates()
                inj=qbs[qbs["season"].eq(season)][["season","week","team","gsis_id","report_status","practice_status"]].drop_duplicates()
                joined=inj.merge(d,left_on=["season","week","team","gsis_id"],right_on=["season","week","team","player_id"],how="left")
                # Count charted QBs per team/week; determine charted QB1/QB2 IDs.
                depth_group=d.sort_values("depth_rank").groupby(["season","week","team"])
                rank_map=depth_group.apply(lambda x: list(x[["player_id","depth_rank","full_name"]].dropna(subset=["player_id"]).to_dict("records")),include_groups=False)
                def get_depth(row):
                    vals=rank_map.get((row["season"],row["week"],row["team"]),[])
                    return vals
                joined["team_qb_depth"] = joined.apply(get_depth,axis=1)
                joined["charted_qb_count"]=joined["team_qb_depth"].map(len)
                joined["qb1_id"]=joined["team_qb_depth"].map(lambda x: next((z["player_id"] for z in x if z.get("depth_rank")==1),None))
                joined["qb2_id"]=joined["team_qb_depth"].map(lambda x: next((z["player_id"] for z in x if z.get("depth_rank")==2),None))
                joined["qb3_id"]=joined["team_qb_depth"].map(lambda x: next((z["player_id"] for z in x if z.get("depth_rank")==3),None))
                joined["depth_schema"]="weekly_legacy"
                joined["injury_player_chart_rank"]=joined["depth_rank"]
                outputs.append(joined.drop(columns=["team_qb_depth"],errors="ignore"))
            else:
                # Timestamped ESPN schema: retain raw snapshots for separate future mapping.
                required={"dt","team","gsis_id","pos_abb","pos_rank"}
                missing=required-set(depth.columns)
                if missing: raise ValueError(f"Timestamped depth chart missing {sorted(missing)}")
                d=depth[depth["pos_abb"].astype(str).str.upper().eq("QB")]
                outputs.append(pd.DataFrame([{
                    "season":season,"depth_schema":"timestamped_espn",
                    "timestamp_rows":int(len(d)),"unique_teams":int(d["team"].nunique()),
                    "unique_qbs":int(d["gsis_id"].nunique()),
                    "note":"Requires timestamp-to-game kickoff alignment; not joined to injury rows in this audit."
                }]))
        except Exception as exc:
            errors.append({"season":season,"error":f"{type(exc).__name__}: {exc}"})
    details=pd.concat(outputs,ignore_index=True,sort=False) if outputs else pd.DataFrame()
    legacy=details[details.get("depth_schema",pd.Series(index=details.index,dtype=str)).eq("weekly_legacy")] if not details.empty else pd.DataFrame()
    summary={
      "captured_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
      "status":"QB_DEPTH_CHART_AUDIT_ONLY_NO_MODEL_CHANGES",
      "qb_injury_report_rows":int(len(qbs)),
      "legacy_weekly_join_rows":int(len(legacy)),
      "legacy_injured_qb_charted":int(legacy.get("injury_player_chart_rank",pd.Series(dtype=float)).notna().sum()),
      "legacy_rows_with_qb1_and_qb2":int((legacy.get("qb1_id",pd.Series(dtype=object)).notna() & legacy.get("qb2_id",pd.Series(dtype=object)).notna()).sum()),
      "legacy_injury_rows_where_injured_qb_is_qb1":int((legacy.get("injury_player_chart_rank",pd.Series(dtype=float))==1).sum()),
      "legacy_injury_rows_where_injured_qb_is_qb2":int((legacy.get("injury_player_chart_rank",pd.Series(dtype=float))==2).sum()),
      "timestamped_season_summaries":details[details.get("depth_schema",pd.Series(index=details.index,dtype=str)).eq("timestamped_espn")].to_dict(orient="records") if not details.empty else [],
      "errors":errors,
      "limitations":[
       "Legacy weekly depth-chart data is available for 2021-2024 and is joined by GSIS ID, team, season and week.",
       "2025-2026 depth charts use timestamped ESPN snapshots and require strict timestamp-to-kickoff alignment before joining.",
       "A depth-chart QB2 is evidence of listed depth, not proof that the player was active or the actual game replacement.",
       "This audit does not estimate point-spread impact or change production projections."
      ]
    }
    OUT.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    details.to_csv(OUT/f"qb_depth_chart_replacement_audit_{stamp}.csv",index=False)
    (OUT/f"qb_depth_chart_replacement_audit_{stamp}.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    if errors: raise RuntimeError(f"Depth-chart audit download/parse errors: {errors}")

if __name__=="__main__": main()
