#!/usr/bin/env python3
"""Build player-level, point-in-time injury role audit from PFR snap counts.

Research only. Uses prior-game snap shares to classify injured players and identify
the most-used same-team positional replacement candidate. It does not change model
features or projections. PFR player IDs are retained; injury reports are joined by
normalized player name/team because the feeds use different player-ID systems.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import re
import sys
import unicodedata

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
# When executed as `python research/<script>.py`, Python places the research/
# directory (not the repository root) on sys.path. Add the repo root so the
# shared top-level injury_model module can be imported reliably in Actions.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "player_injury_backtests"
SEASONS = range(2021, 2027)
HEADERS = {"User-Agent": "sports-betting-model-player-role-injury-audit/1.0"}
TIMEOUT = (15, 180)

POSITION_GROUP = {
    "QB": "QB", "RB": "RB", "FB": "RB",
    "WR": "WR", "TE": "TE",
    "C": "OL", "G": "OL", "LG": "OL", "RG": "OL",
    "T": "OL", "LT": "OL", "RT": "OL", "OT": "OL", "OL": "OL",
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL", "EDGE": "DL",
    "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB",
    "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "SAF": "DB", "DB": "DB",
    "K": "ST", "P": "ST", "LS": "ST",
}
STATUS_WEIGHT = {"OUT": 1.0, "DOUBTFUL": 0.85, "QUESTIONABLE": 0.55}


def read_parquet(url: str) -> pd.DataFrame:
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return pd.read_parquet(BytesIO(response.content), engine="pyarrow")


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def position_group(value: object) -> str:
    return POSITION_GROUP.get(str(value or "").strip().upper(), "OTHER")


def load_snaps() -> pd.DataFrame:
    frames = []
    for season in SEASONS:
        url = (
            "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/"
            f"snap_counts_{season}.parquet"
        )
        frame = read_parquet(url)
        frame["source_url"] = url
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True, sort=False)
    required = {"season", "week", "player", "team", "position", "offense_snaps",
                "offense_pct", "defense_snaps", "defense_pct", "st_snaps", "st_pct"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Snap-count schema missing required columns: {sorted(missing)}")
    data["season"] = pd.to_numeric(data["season"], errors="coerce")
    data["week"] = pd.to_numeric(data["week"], errors="coerce")
    data["team"] = data["team"].astype("string").str.upper().str.strip()
    data["player_key"] = data["player"].map(normalize_name)
    data["position"] = data["position"].astype("string").str.upper().str.strip()
    data["position_group"] = data["position"].map(position_group)
    for col in ("offense_snaps", "offense_pct", "defense_snaps", "defense_pct", "st_snaps", "st_pct"):
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0.0)

    # nflverse/PFR percentage fields may be encoded as fractions (0-1) rather
    # than percentage points (0-100). Normalize each share column before
    # applying role thresholds expressed on a 0-100 scale.
    pct_scale_factors = {}
    for col in ("offense_pct", "defense_pct", "st_pct"):
        observed_max = float(data[col].max()) if not data.empty else 0.0
        factor = 100.0 if 0.0 < observed_max <= 1.5 else 1.0
        data[col] = data[col] * factor
        pct_scale_factors[col] = factor
        if data[col].max() > 100.5:
            raise ValueError(
                f"{col} exceeds 100 after normalization; refusing invalid snap-share scale"
            )
    data.attrs["pct_scale_factors"] = pct_scale_factors
    return data.dropna(subset=["season", "week", "team", "player_key"]).copy()


def load_reports() -> pd.DataFrame:
    from injury_model import load_injury_reports, _normalize_reports
    reports = _normalize_reports(load_injury_reports(tuple(SEASONS)))
    reports["season"] = pd.to_numeric(reports["season"], errors="coerce")
    reports["week"] = pd.to_numeric(reports["week"], errors="coerce")
    reports["team"] = reports["team"].astype("string").str.upper().str.strip()
    reports["player_key"] = reports["full_name"].map(normalize_name)
    reports["position"] = reports["position"].astype("string").str.upper().str.strip()
    reports["position_group"] = reports["position"].map(position_group)
    reports["report_status"] = reports.get("report_status", "").fillna("").astype(str).str.upper().str.strip()
    reports = reports.dropna(subset=["season", "week", "team", "player_key"]).copy()
    reports["season"] = reports["season"].astype(int)
    reports["week"] = reports["week"].astype(int)
    return reports


def build_prior_role(snaps: pd.DataFrame, season: int, week: int, team: str,
                     player_key: str, group: str) -> dict:
    prior = snaps[
        (snaps["season"] == season) & (snaps["week"] < week) &
        (snaps["team"] == team) & (snaps["position_group"] == group)
    ].copy()
    player = prior[prior["player_key"] == player_key].sort_values("week")
    if player.empty:
        return {
            "prior_games": 0, "last3_offense_pct": None, "last5_offense_pct": None,
            "last3_defense_pct": None, "last5_defense_pct": None,
            "last3_st_pct": None, "last5_st_pct": None,
            "role_class": "NO_PRIOR_SNAP_DATA", "replacement_candidate": None,
            "replacement_last3_offense_pct": None, "replacement_last3_defense_pct": None,
        }

    def mean_last(frame: pd.DataFrame, col: str, n: int):
        values = frame.sort_values("week")[col].tail(n)
        return round(float(values.mean()), 1) if len(values) else None

    n_games = int(player["week"].nunique())
    off3, off5 = mean_last(player, "offense_pct", 3), mean_last(player, "offense_pct", 5)
    def3, def5 = mean_last(player, "defense_pct", 3), mean_last(player, "defense_pct", 5)
    st3, st5 = mean_last(player, "st_pct", 3), mean_last(player, "st_pct", 5)
    primary = def3 if group in {"DL", "LB", "DB"} else off3
    if primary is None:
        role = "INSUFFICIENT_EVIDENCE"
    elif primary >= 70:
        role = "KEY_STARTER"
    elif primary >= 45:
        role = "STARTER_OR_MAJOR_ROTATION"
    elif primary >= 20:
        role = "ROTATIONAL_CONTRIBUTOR"
    else:
        role = "DEPTH_OR_SPECIAL_TEAMS"

    candidates = prior[prior["player_key"] != player_key].copy()
    if not candidates.empty:
        candidates["recent_primary_pct"] = (
            candidates["defense_pct"] if group in {"DL", "LB", "DB"}
            else candidates["offense_pct"]
        )
        recent = candidates.sort_values("week").groupby(
            ["player_key", "player"], as_index=False
        ).tail(3)
        ranking = recent.groupby(["player_key", "player"], as_index=False)[
            "recent_primary_pct"
        ].mean().sort_values("recent_primary_pct", ascending=False)
        replacement = ranking.iloc[0] if not ranking.empty else None
    else:
        replacement = None

    return {
        "prior_games": n_games,
        "last3_offense_pct": off3, "last5_offense_pct": off5,
        "last3_defense_pct": def3, "last5_defense_pct": def5,
        "last3_st_pct": st3, "last5_st_pct": st5,
        "role_class": role,
        "replacement_candidate": str(replacement["player"]) if replacement is not None else None,
        "replacement_last3_offense_pct": (
            mean_last(candidates[candidates["player_key"] == replacement["player_key"]],
                      "offense_pct", 3) if replacement is not None else None
        ),
        "replacement_last3_defense_pct": (
            mean_last(candidates[candidates["player_key"] == replacement["player_key"]],
                      "defense_pct", 3) if replacement is not None else None
        ),
    }


def main() -> None:
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    snaps = load_snaps()
    reports = load_reports()

    # One record per player/team/season/week: preserve the most recent report status.
    sort_cols = [c for c in ("snapshot_captured_at_utc", "report_status") if c in reports.columns]
    if sort_cols:
        reports = reports.sort_values(sort_cols)
    reports = reports.drop_duplicates(
        ["season", "week", "team", "player_key"], keep="last"
    )

    records = []
    for row in reports.itertuples(index=False):
        if row.report_status not in STATUS_WEIGHT:
            continue
        role = build_prior_role(
            snaps, int(row.season), int(row.week), str(row.team),
            str(row.player_key), str(row.position_group)
        )
        records.append({
            "season": int(row.season), "week": int(row.week), "team": str(row.team),
            "player": str(row.full_name), "position": str(row.position),
            "position_group": str(row.position_group),
            "injury_status": str(row.report_status),
            "practice_status": getattr(row, "practice_status", ""),
            "injury": getattr(row, "report_primary_injury", ""),
            "status_weight_proxy": STATUS_WEIGHT[row.report_status],
            **role,
            "classification_note": (
                "Snap-share role proxy only; not a player-quality or point-impact estimate. "
                "Replacement is the most-used same-team player in the broad position group, "
                "not a confirmed next-man-up or depth-chart starter."
            ),
        })

    result = pd.DataFrame(records)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = captured.strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUT / f"player_role_injury_audit_{stamp}.csv"
    json_path = OUT / f"player_role_injury_audit_{stamp}.json"
    result.to_csv(csv_path, index=False)
    summary = {
        "captured_at_utc": captured.isoformat().replace("+00:00", "Z"),
        "status": "RESEARCH_ONLY_NO_MODEL_CHANGES",
        "seasons": list(SEASONS),
        "snap_count_rows": int(len(snaps)),
        "snap_percentage_scale_factors_applied": snaps.attrs.get("pct_scale_factors", {}),
        "injury_player_rows_audited": int(len(result)),
        "role_class_counts": result["role_class"].value_counts(dropna=False).to_dict()
            if not result.empty else {},
        "injury_status_counts": result["injury_status"].value_counts(dropna=False).to_dict()
            if not result.empty else {},
        "match_method": "normalized full player name + team + position group; no forced fuzzy joins",
        "limitations": [
            "PFR snap counts are game-level and available after games; target-week data is excluded.",
            "The audit uses only games strictly before the injury-report week.",
            "Replacement candidates are recent same-team players in broad position groups, not verified depth-chart next men up.",
            "OL grouping is broad and must not be interpreted as a precise like-for-like lineman replacement.",
            "Snap share measures role/opportunity, not player quality or expected points.",
            "No 2026 FTN participation feed is required or assumed.",
            "No production model features, injury weights, or projections are changed.",
        ],
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved {csv_path}")
    print(f"Saved {json_path}")


if __name__ == "__main__":
    main()
