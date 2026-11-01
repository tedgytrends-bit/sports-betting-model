#!/usr/bin/env python3
"""Point-in-time audit of injured-QB depth-chart replacement coverage.

Legacy weekly depth charts (2021-2024) are joined by season/week/team/GSIS ID.
ESPN-era snapshots (2025+) are aligned to each game's kickoff: only the latest
team snapshot strictly before kickoff is eligible. Research only; no model
features, projections, or prospective grading are changed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
HEADERS = {"User-Agent": "sports-betting-model-qb-depth-chart-audit/2.0"}
EASTERN = ZoneInfo("America/New_York")


def load_depth(season: int) -> pd.DataFrame:
    url = f"https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.parquet"
    response = requests.get(url, headers=HEADERS, timeout=(15, 120))
    response.raise_for_status()
    return pd.read_parquet(BytesIO(response.content), engine="pyarrow")


def load_schedules() -> pd.DataFrame:
    url = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
    response = requests.get(url, headers=HEADERS, timeout=(15, 120))
    response.raise_for_status()
    games = pd.read_csv(BytesIO(response.content), low_memory=False)
    required = {"season", "week", "gameday", "gametime", "home_team", "away_team", "game_id"}
    missing = required - set(games.columns)
    if missing:
        raise ValueError(f"Schedule is missing required fields: {sorted(missing)}")
    games = games[games["season"].isin(SEASONS)].copy()
    games["season"] = pd.to_numeric(games["season"], errors="coerce")
    games["week"] = pd.to_numeric(games["week"], errors="coerce")
    games["kickoff_utc"] = pd.NaT
    for idx, row in games.iterrows():
        try:
            day = pd.Timestamp(row["gameday"]).date()
            raw_clock = str(row["gametime"]).strip()
            clock = None
            for fmt in ("%I:%M%p", "%I:%M %p", "%H:%M", "%H:%M:%S"):
                try:
                    clock = datetime.strptime(raw_clock, fmt).time()
                    break
                except ValueError:
                    continue
            if clock is None:
                raise ValueError(f"Unrecognized gametime: {raw_clock}")
            local = datetime.combine(day, clock).replace(tzinfo=EASTERN)
            games.at[idx, "kickoff_utc"] = pd.Timestamp(local.astimezone(timezone.utc)).tz_localize(None)
        except Exception:
            # A missing/invalid kickoff is not eligible for a point-in-time join.
            continue
    return games.dropna(subset=["season", "week", "kickoff_utc"])


def _depth_list(group: pd.DataFrame) -> list[dict]:
    rows = group.sort_values(["depth_rank", "player_id"]).dropna(subset=["player_id"])
    return rows[["player_id", "depth_rank", "player_name"]].to_dict("records")


def _add_depth_fields(joined: pd.DataFrame, rank_col: str) -> pd.DataFrame:
    joined["injury_player_chart_rank"] = pd.to_numeric(joined[rank_col], errors="coerce")
    joined["qb1_id"] = joined["qb_rows"].map(lambda x: next((z["player_id"] for z in x if z["depth_rank"] == 1), None))
    joined["qb2_id"] = joined["qb_rows"].map(lambda x: next((z["player_id"] for z in x if z["depth_rank"] == 2), None))
    joined["qb3_id"] = joined["qb_rows"].map(lambda x: next((z["player_id"] for z in x if z["depth_rank"] == 3), None))
    joined["charted_qb_count"] = joined["qb_rows"].map(len)
    joined["listed_replacement_id"] = joined.apply(
        lambda r: r["qb2_id"] if r["injury_player_chart_rank"] == 1
        else r["qb1_id"] if r["injury_player_chart_rank"] == 2
        else (r["qb1_id"] if r["qb1_id"] != r["gsis_id"] else r["qb2_id"]),
        axis=1,
    )
    return joined.drop(columns=["qb_rows"], errors="ignore")


def main() -> None:
    from injury_model import load_injury_reports, _normalize_reports

    injuries = _normalize_reports(load_injury_reports(SEASONS))
    for col in ("season", "week"):
        injuries[col] = pd.to_numeric(injuries[col], errors="coerce")
    injuries["team"] = injuries["team"].astype("string").str.upper().str.strip()
    injuries["position"] = injuries["position"].astype("string").str.upper().str.strip()
    injuries["gsis_id"] = injuries["gsis_id"].astype("string").str.strip()
    qbs = injuries[injuries["position"].eq("QB")].dropna(
        subset=["season", "week", "team", "gsis_id"]
    ).copy()
    qbs["season"] = qbs["season"].astype(int)
    qbs["week"] = qbs["week"].astype(int)

    schedules = load_schedules()
    outputs, errors = [], []

    for season in SEASONS:
        try:
            depth = load_depth(season)
            if season <= 2024:
                required = {"season", "week", "club_code", "gsis_id", "position", "depth_team"}
                missing = required - set(depth.columns)
                if missing:
                    raise ValueError(f"Legacy depth chart missing {sorted(missing)}")
                d = depth[depth["position"].astype(str).str.upper().eq("QB")].copy()
                d["season"] = pd.to_numeric(d["season"], errors="coerce")
                d["week"] = pd.to_numeric(d["week"], errors="coerce")
                d["team"] = d["club_code"].astype("string").str.upper().str.strip()
                d["player_id"] = d["gsis_id"].astype("string").str.strip()
                d["depth_rank"] = pd.to_numeric(d["depth_team"], errors="coerce")
                d["player_name"] = d.get("full_name", pd.Series(index=d.index, dtype="string"))
                d = d.dropna(subset=["season", "week", "depth_rank"])
                inj = qbs[qbs["season"].eq(season)].merge(
                    schedules[schedules["season"].eq(season)][["season", "week", "home_team", "away_team", "kickoff_utc", "game_id"]],
                    left_on=["season", "week"], right_on=["season", "week"], how="left"
                )
                inj = inj[(inj["team"] == inj["home_team"]) | (inj["team"] == inj["away_team"])].copy()
                dgroups = {
                    key: _depth_list(g)
                    for key, g in d.groupby(["season", "week", "team"], sort=False)
                }
                inj["qb_rows"] = inj.apply(lambda r: dgroups.get((r["season"], r["week"], r["team"]), []), axis=1)
                inj["depth_rank"] = inj.apply(
                    lambda r: next((z["depth_rank"] for z in r["qb_rows"] if z["player_id"] == r["gsis_id"]), None), axis=1
                )
                inj = _add_depth_fields(inj, "depth_rank")
                inj["depth_schema"] = "weekly_legacy"
                outputs.append(inj)
            else:
                required = {"dt", "team", "gsis_id", "pos_abb", "pos_rank"}
                missing = required - set(depth.columns)
                if missing:
                    raise ValueError(f"Timestamped depth chart missing {sorted(missing)}")
                d = depth[depth["pos_abb"].astype(str).str.upper().eq("QB")].copy()
                d["snapshot_utc"] = pd.to_datetime(d["dt"], errors="coerce", utc=True).dt.tz_convert(None)
                d["team"] = d["team"].astype("string").str.upper().str.strip()
                d["player_id"] = d["gsis_id"].astype("string").str.strip()
                d["depth_rank"] = pd.to_numeric(d["pos_rank"], errors="coerce")
                d["player_name"] = d.get("player_name", pd.Series(index=d.index, dtype="string"))
                d = d.dropna(subset=["snapshot_utc", "team", "player_id", "depth_rank"])
                inj = qbs[qbs["season"].eq(season)].merge(
                    schedules[schedules["season"].eq(season)][["season", "week", "home_team", "away_team", "kickoff_utc", "game_id"]],
                    on=["season", "week"], how="left"
                )
                inj = inj[(inj["team"] == inj["home_team"]) | (inj["team"] == inj["away_team"])].copy()
                snapshots = {}
                for team, group in d.groupby("team", sort=False):
                    snapshots[team] = group
                chosen = []
                for _, row in inj.iterrows():
                    team_rows = snapshots.get(row["team"])
                    if team_rows is None or pd.isna(row["kickoff_utc"]):
                        chosen.append((pd.NaT, []))
                        continue
                    eligible = team_rows[team_rows["snapshot_utc"] < row["kickoff_utc"]]
                    if eligible.empty:
                        chosen.append((pd.NaT, []))
                        continue
                    latest = eligible["snapshot_utc"].max()
                    snap = eligible[eligible["snapshot_utc"].eq(latest)]
                    chosen.append((latest, _depth_list(snap)))
                inj["selected_snapshot_utc"] = [x[0] for x in chosen]
                inj["qb_rows"] = [x[1] for x in chosen]
                inj["depth_rank"] = inj.apply(
                    lambda r: next((z["depth_rank"] for z in r["qb_rows"] if z["player_id"] == r["gsis_id"]), None), axis=1
                )
                inj = _add_depth_fields(inj, "depth_rank")
                inj["depth_schema"] = "timestamped_espn_point_in_time"
                inj["snapshot_age_hours"] = (
                    inj["kickoff_utc"] - inj["selected_snapshot_utc"]
                ).dt.total_seconds() / 3600
                outputs.append(inj)
        except Exception as exc:
            errors.append({"season": season, "error": f"{type(exc).__name__}: {exc}"})

    details = pd.concat(outputs, ignore_index=True, sort=False) if outputs else pd.DataFrame()
    if details.empty:
        raise RuntimeError(f"No QB depth-chart rows produced. Errors: {errors}")
    legacy = details[details["depth_schema"].eq("weekly_legacy")]
    espn = details[details["depth_schema"].eq("timestamped_espn_point_in_time")]
    summary = {
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "POINT_IN_TIME_QB_DEPTH_CHART_AUDIT_ONLY_NO_MODEL_CHANGES",
        "qb_injury_report_rows": int(len(qbs)),
        "legacy_rows_joined_to_game": int(len(legacy)),
        "legacy_injured_qb_charted": int(legacy["injury_player_chart_rank"].notna().sum()),
        "legacy_injured_qb_qb1": int(legacy["injury_player_chart_rank"].eq(1).sum()),
        "legacy_injured_qb_qb2": int(legacy["injury_player_chart_rank"].eq(2).sum()),
        "timestamped_rows_joined_to_game": int(len(espn)),
        "timestamped_injured_qb_charted_pre_kickoff": int(espn["injury_player_chart_rank"].notna().sum()),
        "timestamped_injured_qb_qb1": int(espn["injury_player_chart_rank"].eq(1).sum()),
        "timestamped_injured_qb_qb2": int(espn["injury_player_chart_rank"].eq(2).sum()),
        "timestamped_rows_with_pre_kickoff_snapshot": int(espn["selected_snapshot_utc"].notna().sum()),
        "timestamped_median_snapshot_age_hours": float(espn["snapshot_age_hours"].median()) if espn["snapshot_age_hours"].notna().any() else None,
        "timestamped_rows_with_listed_replacement": int(espn["listed_replacement_id"].notna().sum()),
        "errors": errors,
        "limitations": [
            "ESPN-era depth charts are assigned using the latest team snapshot strictly before scheduled kickoff in America/New_York.",
            "A depth-chart listing is not proof that a player was active or actually entered the game.",
            "A listed replacement is a depth-chart candidate, not a confirmed game-day replacement.",
            "Legacy weekly depth charts are week-level and do not provide a precise publication timestamp.",
            "No point impact is inferred and no official model or prospective record is changed."
        ]
    }
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    details.to_csv(OUT / f"qb_depth_chart_replacement_audit_{stamp}.csv", index=False)
    (OUT / f"qb_depth_chart_replacement_audit_{stamp}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if errors:
        raise RuntimeError(f"Depth-chart audit download/parse errors: {errors}")


if __name__ == "__main__":
    main()
