#!/usr/bin/env python3
"""Audit archived QB starter source metadata without treating URLs as proof.

A URL and timestamp are only traceable *metadata*. Even a recent article
cannot establish that its content confirms the named QB for this game without
checking the article. This audit never modifies the official model.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import load_schedule_data

OUTDIR=ROOT/"data"/"week09_review"
MAX_AGE_HOURS=168.0
REQUIRED={"game_id","team","qb_id","qb_name","source_url","source_published_at_utc"}


def kickoff_utc(gameday, gametime):
    """Interpret nflverse game date/time as America/New_York local kickoff."""
    if pd.isna(gameday) or pd.isna(gametime) or not str(gametime).strip():
        return pd.NaT
    day=pd.to_datetime(gameday,errors="coerce")
    if pd.isna(day):
        return pd.NaT
    local=pd.to_datetime(day.strftime("%Y-%m-%d")+" "+str(gametime).strip(),errors="coerce")
    if pd.isna(local):
        return pd.NaT
    try:
        return local.tz_localize("America/New_York",ambiguous="NaT",nonexistent="NaT").tz_convert("UTC")
    except Exception:
        return pd.NaT


def audit(schedule:pd.DataFrame, overrides:pd.DataFrame, *,max_age_hours=MAX_AGE_HOURS):
    missing=REQUIRED-set(overrides.columns)
    if missing:
        raise ValueError(f"Missing override fields {sorted(missing)}")
    schedule_required={"game_id","gameday","gametime","home_team","away_team"}
    missing=schedule_required-set(schedule.columns)
    if missing:
        raise ValueError(f"Schedule missing {sorted(missing)}")
    if overrides.duplicated(["game_id","team"]).any():
        raise ValueError("Duplicate QB starter override for game/team")
    games=schedule[list(schedule_required)].copy()
    if games.game_id.duplicated().any():
        raise ValueError("Duplicate game ID in schedule")
    rows=[]
    for rec in overrides.to_dict("records"):
        gid=str(rec["game_id"]).strip()
        team=str(rec["team"]).upper().strip()
        gameset=games.loc[games.game_id.astype(str).eq(gid)]
        remarks=[]
        if len(gameset)!=1:
            remarks.append("game_not_in_schedule")
        if len(gameset)==1:
            game=gameset.iloc[0]
            if team not in {str(game.home_team).upper(),str(game.away_team).upper()}:
                remarks.append("team_not_in_matchup")
            start=kickoff_utc(game.gameday,game.gametime)
            if pd.isna(start):
                remarks.append("kickoff_unknown")
        else:
            start=pd.NaT
        published=pd.to_datetime(rec.get("source_published_at_utc"),utc=True,errors="coerce")
        if pd.isna(published):
            remarks.append("source_publication_unknown")
        if not str(rec.get("source_url","")).startswith("https://"):
            remarks.append("source_url_missing_or_non_https")
        if not str(rec.get("qb_id","")).strip():
            remarks.append("qb_id_missing")
        if not str(rec.get("qb_name","")).strip():
            remarks.append("qb_name_missing")
        age=None
        if pd.notna(published) and pd.notna(start):
            age=(start-published).total_seconds()/3600.0
            if age<=0:
                remarks.append("source_published_at_or_after_kickoff")
            elif age>max_age_hours:
                remarks.append("stale_older_than_one_week")
        # Never convert machine-validated metadata into human source confirmation.
        if any(s not in {"stale_older_than_one_week"} for s in remarks):
            status="invalid_metadata"
        elif "stale_older_than_one_week" in remarks:
            status="stale_requires_manual_reconfirmation"
        else:
            status="recent_metadata_only_content_unverified"
        rows.append({
            "game_id":gid,
            "team":team,
            "qb_id":str(rec.get("qb_id","")),
            "qb_name":str(rec.get("qb_name","")),
            "source_url":str(rec.get("source_url","")),
            "source_published_at_utc":str(rec.get("source_published_at_utc","")),
            "kickoff_utc":start.isoformat() if pd.notna(start) else "",
            "source_age_hours_before_kickoff":round(age,2) if age is not None else None,
            "metadata_status":status,
            "flags":";".join(remarks),
            "content_checked":False,
            "confirmed_matchup_starter":False,
        })
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--season",type=int,default=2026)
    p.add_argument("--week",type=int,default=9)
    args=p.parse_args()
    if not 1<=args.week<=22:
        p.error("week must be 1 to 22")
    saved=ROOT/"data"/"qb_starters"/f"{args.season}_week{args.week:02d}_confirmed.csv"
    if not saved.exists():
        raise FileNotFoundError(f"QB confirmation file not yet archived: {saved}")
    sources=pd.read_csv(saved,dtype=str,keep_default_na=False)
    result=audit(load_schedule_data(),sources)
    if result.empty:
        raise AssertionError("No source rows to audit")
    OUTDIR.mkdir(parents=True,exist_ok=True)
    stem=f"qb_source_metadata_audit_{args.season}_week{args.week:02d}"
    path=OUTDIR/f"{stem}.csv"
    result.to_csv(path,index=False)
    report={
        "status":"RESEARCH_METADATA_AUDIT_NO_OFFICIAL_CHANGES",
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "input_file":str(saved.relative_to(ROOT)),
        "rows":len(result),
        "metadata_status_counts":result.metadata_status.value_counts().to_dict(),
        "stale_rows":result.loc[result.flags.str.contains("stale_older_than_one_week"),[
            "game_id","team","qb_name","source_age_hours_before_kickoff"
        ]].to_dict("records"),
        "timestamp_method":"nflverse gameday/gametime interpreted America/New_York -> UTC; exact kickoff, DST-aware",
        "interpretation":"Recent valid timestamp, URL and team membership do NOT prove that article content confirms starting QB for this matchup. All rows require source content verification.",
        "output_file":str(path.relative_to(ROOT)),
    }
    (OUTDIR/f"{stem}.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
