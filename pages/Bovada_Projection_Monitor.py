from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

from model import MODEL_VERSION, load_schedule_data, load_pbp, build_efficiency_model_dataset, project_upcoming_efficiency
from injury_model import load_injury_reports, add_injury_features, injury_coverage_diagnostics

st.title("Bovada Projection Monitor")
st.caption("Upcoming-game market source: user-supplied Bovada lines. Historical backtests retain their established research data sources.")

ROOT = Path(__file__).resolve().parents[1]
LINE_FILE = ROOT / "data" / "bovada_lines.csv"
PROJECTION_DIR = ROOT / "data" / "prospective_ats_tracking"

@st.cache_data(ttl=1800, show_spinner="Loading NFL schedule...")
def get_schedule():
    return load_schedule_data()

@st.cache_data(ttl=3600, show_spinner="Loading historical injury reports...")
def get_injury_reports():
    return load_injury_reports((2021, 2022, 2023, 2024, 2025, 2026))

@st.cache_data(ttl=900, show_spinner="Building paired baseline and injury-aware projections...")
def get_live_paired_efficiency_projections():
    schedule = load_schedule_data()
    pbp = load_pbp((2021, 2022, 2023, 2024, 2025, 2026))
    baseline_features = build_efficiency_model_dataset(schedule, pbp, lookback_games=10)
    injury_reports = get_injury_reports()
    injury_features = add_injury_features(
        baseline_features, schedule, injury_reports
    )

    # Both models use the same schedule, historical PBP, Ridge estimator,
    # training window, and upcoming games. The only intended difference is
    # the pregame injury-report feature set.
    baseline = project_upcoming_efficiency(
        baseline_features, min_train_games=500
    )
    injury = project_upcoming_efficiency(
        injury_features, min_train_games=500
    )
    if baseline.empty or injury.empty:
        return pd.DataFrame()

    base_cols = ["game_id", "projected_home", "projected_away", "projected_total"]
    injury_cols = [
        "game_id", "projected_home", "projected_away", "projected_total",
        "home_injury_report_available", "away_injury_report_available",
        "home_inj_out", "away_inj_out",
        "home_qb_out", "away_qb_out", "home_ol_out", "away_ol_out",
        "home_skill_out", "away_skill_out", "home_defense_out", "away_defense_out",
        "home_inj_questionable", "away_inj_questionable",
    ]
    base = baseline[base_cols].rename(columns={
        "projected_home": "baseline_projected_home",
        "projected_away": "baseline_projected_away",
        "projected_total": "baseline_projected_total",
    })
    inj = injury[[c for c in injury_cols if c in injury.columns]].rename(columns={
        "projected_home": "injury_projected_home",
        "projected_away": "injury_projected_away",
        "projected_total": "injury_projected_total",
    })
    projections = inj.merge(base, on="game_id", how="inner", validate="one_to_one")
    meta = injury[["game_id", "gameday", "season", "week", "away_team", "home_team"]]
    projections = meta.merge(projections, on="game_id", how="inner", validate="one_to_one")

    projections["gameday"] = pd.to_datetime(projections["gameday"], errors="coerce", utc=True)
    now = pd.Timestamp.now(tz="UTC")
    projections = projections[
        projections["gameday"].notna()
        & (projections["gameday"] >= now.normalize())
        & projections["home_team"].notna()
        & projections["away_team"].notna()
    ].copy()

    for prefix in ("baseline", "injury"):
        projections[f"{prefix}_predicted_home_margin"] = (
            projections[f"{prefix}_projected_home"] - projections[f"{prefix}_projected_away"]
        )
    projections["baseline_model_total"] = projections["baseline_projected_total"]
    projections["injury_model_total"] = projections["injury_projected_total"]
    projections["baseline_home_margin"] = projections["baseline_predicted_home_margin"]
    projections["injury_home_margin"] = projections["injury_predicted_home_margin"]
    projections["injury_home_margin_delta"] = (
        projections["injury_home_margin"] - projections["baseline_home_margin"]
    )
    projections["injury_total_delta"] = (
        projections["injury_model_total"] - projections["baseline_model_total"]
    )
    projections["model_version"] = f"{MODEL_VERSION}+paired-live"
    projections["projection_captured_at_utc"] = now.isoformat()
    projections["injury_features_included"] = True

    home_available = pd.to_numeric(projections.get("home_injury_report_available"), errors="coerce")
    away_available = pd.to_numeric(projections.get("away_injury_report_available"), errors="coerce")
    projections["injury_data_coverage"] = np.select(
        [
            home_available.eq(1) & away_available.eq(1),
            home_available.eq(1) & away_available.eq(0),
            home_available.eq(0) & away_available.eq(1),
            home_available.eq(0) & away_available.eq(0),
        ],
        ["Both teams", "Home only", "Away only", "No report data"],
        default="Unknown",
    )
    # Preserve the existing monitor's latest-projection field names as aliases
    # for the injury-aware output, while exposing the paired baseline separately.
    projections["projected_home"] = projections["injury_projected_home"]
    projections["projected_away"] = projections["injury_projected_away"]
    projections["model_projected_total"] = projections["injury_model_total"]
    projections["model_predicted_home_margin"] = projections["injury_home_margin"]
    return projections

def norm_team(value):
    # Preserve missing values as missing; never render the literal "NAN" as a team.
    if pd.isna(value):
        return ""
    return str(value).strip().upper()

def key_team(value):
    # nflverse labels the Rams as LA while Bovada commonly labels them LAR.
    team = norm_team(value)
    return {"LAR": "LA"}.get(team, team)

if not LINE_FILE.exists():
    st.error("Bovada line archive is missing: data/bovada_lines.csv")
    st.stop()

lines = pd.read_csv(LINE_FILE, low_memory=False)
required = {"captured_at_utc", "away_team", "home_team", "home_favorite_spread", "total_line"}
missing = required - set(lines.columns)
if missing:
    st.error(f"Bovada line archive is missing required columns: {sorted(missing)}")
    st.stop()
lines["captured_at_utc"] = pd.to_datetime(lines["captured_at_utc"], errors="coerce", utc=True)
for col in ["home_favorite_spread", "total_line", "away_spread_price", "home_spread_price", "over_price", "under_price"]:
    if col not in lines.columns:
        lines[col] = np.nan
    lines[col] = pd.to_numeric(lines[col], errors="coerce")
lines["away_team"] = lines["away_team"].map(norm_team)
lines["home_team"] = lines["home_team"].map(norm_team)
lines = lines.dropna(subset=["captured_at_utc"]).sort_values("captured_at_utc")
lines["game_key"] = lines["away_team"].map(key_team) + "@" + lines["home_team"].map(key_team)
latest_lines = lines.drop_duplicates("game_key", keep="last").copy()
original_lines = lines.drop_duplicates("game_key", keep="first").copy()
latest_lines = latest_lines.rename(columns={
    "captured_at_utc": "latest_line_time_utc",
    "home_favorite_spread": "latest_home_favorite_spread",
    "total_line": "latest_total_line",
    "away_spread_price": "latest_away_spread_price",
    "home_spread_price": "latest_home_spread_price",
    "over_price": "latest_over_price",
    "under_price": "latest_under_price",
})
original_lines = original_lines[["game_key", "captured_at_utc", "home_favorite_spread", "total_line"]].rename(columns={
    "captured_at_utc": "original_line_time_utc",
    "home_favorite_spread": "original_home_favorite_spread",
    "total_line": "original_total_line",
})

try:
    schedule = get_schedule()
    frozen_files = sorted(PROJECTION_DIR.glob("efficiency_projection_*.csv"))
    frozen_parts = []
    for file in frozen_files:
        try:
            part = pd.read_csv(file, low_memory=False)
            if not part.empty:
                if "captured_at_utc" not in part.columns:
                    part["captured_at_utc"] = pd.NaT
                part["captured_at_utc"] = pd.to_datetime(part["captured_at_utc"], errors="coerce", utc=True)
                frozen_parts.append(part)
        except Exception as exc:
            st.warning(f"Could not read frozen projection file {file.name}: {exc}")
    frozen = pd.concat(frozen_parts, ignore_index=True, sort=False) if frozen_parts else pd.DataFrame()
    latest = get_live_paired_efficiency_projections()
    injury_reports = get_injury_reports()
    injury_diagnostics = injury_coverage_diagnostics(
        schedule[schedule["season"].eq(schedule["season"].max())], injury_reports
    )
except Exception as exc:
    st.error(f"Could not build the efficiency-model view: {type(exc).__name__}: {exc}")
    st.stop()

def prep_projection(frame):
    if frame.empty:
        return pd.DataFrame(columns=["game_key"])
    f = frame.copy()
    f["away_team"] = f["away_team"].map(norm_team)
    f["home_team"] = f["home_team"].map(norm_team)
    f["game_key"] = f["away_team"].map(key_team) + "@" + f["home_team"].map(key_team)
    if "model_predicted_home_margin" not in f.columns:
        f["model_predicted_home_margin"] = pd.to_numeric(f.get("projected_home"), errors="coerce") - pd.to_numeric(f.get("projected_away"), errors="coerce")
    if "model_projected_total" not in f.columns:
        f["model_projected_total"] = pd.to_numeric(f.get("projected_total"), errors="coerce")
    for col in ["model_predicted_home_margin", "model_projected_total", "projected_home", "projected_away"]:
        if col not in f.columns:
            f[col] = np.nan
        f[col] = pd.to_numeric(f[col], errors="coerce")
    # Market archive owns matchup labels. Projection-side team columns can be
    # null for completed games or differ in abbreviation, and must not suffix
    # or overwrite the authoritative Bovada team names during the left merge.
    return f.drop(columns=["away_team", "home_team"], errors="ignore")

frozen = prep_projection(frozen)
latest = prep_projection(latest)
if not frozen.empty:
    # The first archived projection per matchup is the immutable weekly baseline.
    frozen = frozen.sort_values("captured_at_utc", na_position="last").drop_duplicates("game_key", keep="first")
    frozen = frozen.rename(columns={
        "captured_at_utc": "frozen_projection_time_utc",
        "model_predicted_home_margin": "frozen_home_margin",
        "model_projected_total": "frozen_model_total",
        "projected_home": "frozen_projected_home",
        "projected_away": "frozen_projected_away",
        "model_version": "frozen_model_version",
    })
else:
    frozen = pd.DataFrame(columns=["game_key", "frozen_projection_time_utc", "frozen_home_margin", "frozen_model_total", "frozen_projected_home", "frozen_projected_away", "frozen_model_version"])
if not latest.empty:
    latest = latest.sort_values("projection_captured_at_utc", na_position="last").drop_duplicates("game_key", keep="last")
    latest = latest.rename(columns={
        "projection_captured_at_utc": "latest_projection_time_utc",
        "model_predicted_home_margin": "latest_home_margin",
        "model_projected_total": "latest_model_total",
        "projected_home": "latest_projected_home",
        "projected_away": "latest_projected_away",
        "model_version": "latest_model_version",
    })
else:
    latest = pd.DataFrame(columns=["game_key", "latest_projection_time_utc", "latest_home_margin", "latest_model_total", "latest_projected_home", "latest_projected_away", "latest_model_version"])

board = latest_lines.merge(original_lines, on="game_key", how="left").merge(frozen, on="game_key", how="left").merge(latest, on="game_key", how="left")
# Same-run live comparison: identical historical training data and market,
# with only the injury-report feature block differing.
for col in [
    "baseline_projected_home", "baseline_projected_away",
    "baseline_model_total", "baseline_home_margin",
    "injury_projected_home", "injury_projected_away",
    "injury_model_total", "injury_home_margin",
    "injury_home_margin_delta", "injury_total_delta",
]:
    if col not in board.columns:
        board[col] = np.nan
board["live_baseline_spread_edge"] = board["baseline_home_margin"] - board["latest_home_favorite_spread"]
board["live_injury_spread_edge"] = board["injury_home_margin"] - board["latest_home_favorite_spread"]
board["live_baseline_total_edge"] = board["baseline_model_total"] - board["latest_total_line"]
board["live_injury_total_edge"] = board["injury_model_total"] - board["latest_total_line"]
board["live_baseline_ats_lean"] = board.apply(
    lambda r: ats_lean(r["live_baseline_spread_edge"], r["latest_home_favorite_spread"], r["home_team"], r["away_team"]), axis=1
)
board["live_injury_ats_lean"] = board.apply(
    lambda r: ats_lean(r["live_injury_spread_edge"], r["latest_home_favorite_spread"], r["home_team"], r["away_team"]), axis=1
)
board["live_baseline_total_lean"] = board["live_baseline_total_edge"].map(total_lean)
board["live_injury_total_lean"] = board["live_injury_total_edge"].map(total_lean)
board["spread_edge_frozen"] = board["frozen_home_margin"] - board["latest_home_favorite_spread"]
board["total_edge_frozen"] = board["frozen_model_total"] - board["latest_total_line"]
board["spread_edge_latest"] = board["latest_home_margin"] - board["latest_home_favorite_spread"]
board["total_edge_latest"] = board["latest_model_total"] - board["latest_total_line"]
board["original_spread_edge_frozen"] = board["frozen_home_margin"] - board["original_home_favorite_spread"]
board["original_total_edge_frozen"] = board["frozen_model_total"] - board["original_total_line"]

def ats_lean(edge, signed_home_line, home_team, away_team):
    if pd.isna(edge) or pd.isna(signed_home_line):
        return "Unavailable"
    if abs(edge) < 0.05:
        return "No clear lean"
    if edge > 0:
        # Positive signed line means home favorite; invert it to show the home's actual spread.
        return f"Lean {home_team} {-signed_home_line:+.1f}"
    return f"Lean {away_team} {signed_home_line:+.1f}"

def total_lean(edge):
    if pd.isna(edge):
        return "Unavailable"
    if abs(edge) < 0.05:
        return "No clear lean"
    return "Lean Over" if edge > 0 else "Lean Under"

board["frozen_ats_lean"] = board.apply(
    lambda r: ats_lean(r["spread_edge_frozen"], r["latest_home_favorite_spread"], r["home_team"], r["away_team"]), axis=1
)
board["latest_ats_lean"] = board.apply(
    lambda r: ats_lean(r["spread_edge_latest"], r["latest_home_favorite_spread"], r["home_team"], r["away_team"]), axis=1
)
board["frozen_total_lean"] = board["total_edge_frozen"].map(total_lean)
board["latest_total_lean"] = board["total_edge_latest"].map(total_lean)

st.subheader("How to use this board")
st.info("Official evaluation uses the earliest saved efficiency projection per game (frozen). The latest efficiency projection is shown separately as the current outlook. All upcoming-game edges use the latest Bovada line archived below; schedule-feed lines are not used as the market reference.")
st.caption("Frozen = earliest archived weekly projection. Live baseline and live injury-aware projections below are rebuilt together from the same historical training data and current schedule; the only intended difference is the injury-report feature block. Injury-feed coverage can be incomplete, and the injury adjustment has not demonstrated reliable out-of-sample improvement. Weather is not automatically adjusted. Paired live projections are cached for up to 15 minutes.")

if frozen.empty:
    st.warning("No saved frozen efficiency projection files were found. Latest projections can be monitored, but the official frozen baseline is unavailable until the capture workflow saves a projection. Do not substitute the schedule-feed baseline for the official record.")

st.subheader("Week 8: original Bovada lines vs latest supplied lines")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Games with Bovada lines", f"{len(board):,}")
c2.metric("Frozen projections available", f"{int(board['frozen_home_margin'].notna().sum()):,}")
c3.metric("Latest projections available", f"{int(board['latest_home_margin'].notna().sum()):,}")
c4.metric("Line updates archived", f"{len(lines) - len(original_lines):,}")

visible = board.copy()
# game_key is created from the original Bovada team codes and survives completed
# games even when the schedule/projection feed stops returning those games.
_key_parts = visible["game_key"].fillna("").astype(str).str.split("@", n=1, expand=True)
visible["Matchup"] = (
    _key_parts[0].fillna("").str.strip() + " @ " +
    _key_parts[1].fillna("").str.strip()
).str.strip()
visible.loc[visible["Matchup"].isin(["@", " @"]), "Matchup"] = "Matchup unavailable"
visible["away_team"] = _key_parts[0].fillna("").str.strip()
visible["home_team"] = _key_parts[1].fillna("").str.strip()
for side, away_col, home_col in [
    ("Frozen", "frozen_projected_away", "frozen_projected_home"),
    ("Latest", "latest_projected_away", "latest_projected_home"),
]:
    visible[f"{side} projected score"] = visible.apply(
        lambda r: (
            f"{r['away_team']} {float(r[away_col]):.1f} — {r['home_team']} {float(r[home_col]):.1f}"
            if pd.notna(r[away_col]) and pd.notna(r[home_col])
            else f"{r['away_team']} @ {r['home_team']} — Not captured" if side == "Frozen"
            else f"{r['away_team']} @ {r['home_team']} — Unavailable"
        ),
        axis=1,
    )
visible["Frozen projected total points"] = visible["frozen_model_total"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
visible["Latest projected total points"] = visible["latest_model_total"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
visible["Frozen ATS lean"] = visible["frozen_ats_lean"]
visible["Latest ATS lean"] = visible["latest_ats_lean"]
visible["Frozen O/U lean"] = visible["frozen_total_lean"]
visible["Latest O/U lean"] = visible["latest_total_lean"]
visible["Live baseline score"] = visible.apply(
    lambda r: f"{r['away_team']} {r['baseline_projected_away']:.1f} — {r['home_team']} {r['baseline_projected_home']:.1f}"
    if pd.notna(r["baseline_projected_away"]) and pd.notna(r["baseline_projected_home"])
    else f"{r['away_team']} @ {r['home_team']} — Unavailable", axis=1
)
visible["Live injury-aware score"] = visible.apply(
    lambda r: f"{r['away_team']} {r['injury_projected_away']:.1f} — {r['home_team']} {r['injury_projected_home']:.1f}"
    if pd.notna(r["injury_projected_away"]) and pd.notna(r["injury_projected_home"])
    else f"{r['away_team']} @ {r['home_team']} — Unavailable", axis=1
)
visible["Live baseline total"] = visible["baseline_model_total"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
visible["Live injury-aware total"] = visible["injury_model_total"].map(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
visible["Injury change: home margin"] = visible["injury_home_margin_delta"].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")
visible["Injury change: total"] = visible["injury_total_delta"].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")
visible["Live baseline ATS lean"] = visible["live_baseline_ats_lean"]
visible["Live injury ATS lean"] = visible["live_injury_ats_lean"]
visible["Live baseline O/U lean"] = visible["live_baseline_total_lean"]
visible["Live injury O/U lean"] = visible["live_injury_total_lean"]
if "injury_data_coverage" in visible.columns:
    visible["Injury data coverage"] = visible["injury_data_coverage"]
for team_side in ("home", "away"):
    for feature, label in (("qb_out", "QB out"), ("ol_out", "OL out"), ("skill_out", "Skill out"), ("defense_out", "Defense out"), ("inj_out", "Players out"), ("inj_questionable", "Questionable")):
        source_col = f"{team_side}_{feature}"
        if source_col in visible.columns:
            visible[f"Latest {team_side.title()} {label}"] = visible[source_col].map(lambda x: f"{x:.0f}" if pd.notna(x) else "Unknown")
for col, label, fmt in [
    ("original_home_favorite_spread", "Original Bovada spread", "{:+.1f}"),
    ("latest_home_favorite_spread", "Latest Bovada spread", "{:+.1f}"),
    ("original_total_line", "Original total", "{:.1f}"),
    ("latest_total_line", "Latest total", "{:.1f}"),
    ("spread_edge_frozen", "Frozen ATS edge vs latest line", "{:+.1f}"),
    ("total_edge_frozen", "Frozen total edge vs latest line", "{:+.1f}"),
    ("spread_edge_latest", "Latest ATS edge vs latest line", "{:+.1f}"),
    ("total_edge_latest", "Latest total edge vs latest line", "{:+.1f}"),
    ("original_spread_edge_frozen", "Frozen ATS edge vs original line", "{:+.1f}"),
    ("original_total_edge_frozen", "Frozen total edge vs original line", "{:+.1f}"),
]:
    visible[label] = visible[col].map(lambda x: fmt.format(x) if pd.notna(x) else "—")
columns = [
    "Matchup", "Original Bovada spread", "Latest Bovada spread", "Original total", "Latest total",
    "Frozen projected score", "Frozen projected total points", "Frozen ATS lean", "Frozen O/U lean",
    "Frozen ATS edge vs latest line", "Frozen total edge vs latest line",
    "Live baseline score", "Live baseline total", "Live baseline ATS lean", "Live baseline O/U lean",
    "Live injury-aware score", "Live injury-aware total", "Live injury ATS lean", "Live injury O/U lean",
    "Injury change: home margin", "Injury change: total",
    "Latest projected score", "Latest projected total points", "Latest ATS lean", "Latest O/U lean", "Injury data coverage",
    "Latest Home QB out", "Latest Away QB out", "Latest Home OL out", "Latest Away OL out",
    "Latest Home Skill out", "Latest Away Skill out", "Latest Home Defense out", "Latest Away Defense out",
    "Latest Home Players out", "Latest Away Players out", "Latest Home Questionable", "Latest Away Questionable",
    "Latest ATS edge vs latest line", "Latest total edge vs latest line",
    "Frozen ATS edge vs original line", "Frozen total edge vs original line",
    "latest_line_time_utc", "frozen_projection_time_utc", "latest_projection_time_utc",
]
st.dataframe(visible[[c for c in columns if c in visible.columns]], hide_index=True, use_container_width=True)

st.caption("Spread convention: positive home_favorite_spread means the home team is favored; negative means the away team is favored. ATS edge = projected home margin − signed home-favorite spread. Total edge = projected total − Bovada total. Positive ATS edge favors the home side; negative favors the away side. Positive total edge leans Over; negative leans Under.")

with st.expander("Injury feed coverage diagnostics", expanded=False):
    st.caption("These counts isolate whether coverage is missing in the source feed, game-type matching, timestamp filtering, or the saved weekly snapshot. They are diagnostic only.")
    st.dataframe(injury_diagnostics, hide_index=True, use_container_width=True)

st.subheader("Archived Bovada lines")
archive_view = lines.sort_values(["game_key", "captured_at_utc"], ascending=[True, False]).copy()
archive_view["Matchup"] = archive_view["away_team"] + " @ " + archive_view["home_team"]
st.dataframe(archive_view[["captured_at_utc", "Matchup", "home_favorite_spread", "total_line", "away_spread_price", "home_spread_price", "over_price", "under_price", "source", "note"]], hide_index=True, use_container_width=True)
st.caption("Initial lines are transcribed from screenshots supplied in chat; prices were not visible/provided and are intentionally blank. For each update, append a new row with a new UTC timestamp; do not overwrite the initial row.")
