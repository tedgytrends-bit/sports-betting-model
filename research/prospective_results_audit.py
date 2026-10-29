from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from model import load_schedule_data
from research.actual_price_grading import matchup_teams_match

st.title("Prospective Results Audit")
st.caption("Forward-looking snapshot grading • Research only • No claim of sportsbook execution")

SNAPSHOT_DIR = Path("data/prospective_ats_tracking")
SNAPSHOT_PATTERN = "ats_market_snapshot_*.csv"
EDGE_THRESHOLD = 3.5
UNIT_RISK = 1.0
WIN_PROFIT_AT_MINUS_110 = 100 / 110

files = sorted(SNAPSHOT_DIR.glob(SNAPSHOT_PATTERN))
if not files:
    st.info("No saved snapshots found yet. Run the GitHub Actions workflow named 'Capture prospective ATS snapshots'.")
    st.stop()

parts = []
read_errors = []
for path in files:
    try:
        frame = pd.read_csv(path, low_memory=False)
        if not frame.empty:
            frame["snapshot_file"] = path.name
            parts.append(frame)
    except Exception as exc:
        read_errors.append(f"{path.name}: {exc}")

for message in read_errors:
    st.warning(f"Could not read snapshot file — {message}")

if not parts:
    st.info("Snapshot files are empty or could not be read.")
    st.stop()

archive = pd.concat(parts, ignore_index=True, sort=False)
required_snapshot_columns = ["game_id", "captured_at_utc"]
missing_columns = [col for col in required_snapshot_columns if col not in archive.columns]
if missing_columns:
    st.error(f"Snapshot archive is missing required columns: {missing_columns}")
    st.stop()

archive["captured_at_utc"] = pd.to_datetime(archive["captured_at_utc"], errors="coerce", utc=True)
for col in [
    "spread_line_source_value",
    "total_line_source_value",
    "baseline_predicted_home_margin",
    "baseline_projected_total",
]:
    if col not in archive.columns:
        archive[col] = np.nan
    archive[col] = pd.to_numeric(archive[col], errors="coerce")

# Preserve the raw archive, but do not let an early incomplete observation
# permanently disqualify a game. Older collector versions sometimes saved the
# matchup before a line/prediction was available. For each market, select the
# earliest pregame observation containing both its prediction and market line.
# The selection is made independently for ATS and totals; no later result or
# score is used to choose a snapshot.
archive = archive.sort_values(
    ["game_id", "captured_at_utc", "snapshot_file"],
    ascending=[True, True, True],
    na_position="last",
)
unique_game_count = int(archive["game_id"].nunique())
duplicate_observations = int(len(archive) - unique_game_count)

# Timing classification must be available before choosing market snapshots.
# Use the raw archive to determine whether each observation was captured before
# the scheduled UTC date; exact kickoff/publication timestamps are unavailable.
if "gameday_utc" in archive.columns:
    archive["scheduled_date_utc"] = pd.to_datetime(
        archive["gameday_utc"], errors="coerce", utc=True
    ).dt.floor("D")
elif "gameday" in archive.columns:
    archive["scheduled_date_utc"] = pd.to_datetime(
        archive["gameday"], errors="coerce", utc=True
    ).dt.floor("D")
else:
    archive["scheduled_date_utc"] = pd.NaT
archive["capture_date_utc"] = archive["captured_at_utc"].dt.floor("D")
archive["timing_status"] = np.select(
    [
        archive["captured_at_utc"].isna() | archive["scheduled_date_utc"].isna(),
        archive["capture_date_utc"] < archive["scheduled_date_utc"],
        archive["capture_date_utc"] == archive["scheduled_date_utc"],
        archive["capture_date_utc"] > archive["scheduled_date_utc"],
    ],
    ["Unknown timing", "Definitely before scheduled date", "Same-day timing uncertain", "Captured after scheduled date"],
    default="Unknown timing",
)

# Compute edge fields on every archived observation before selecting the first
# complete observation for each market.
archive["ats_edge"] = archive["baseline_predicted_home_margin"] - archive["spread_line_source_value"]
archive["total_edge"] = archive["baseline_projected_total"] - archive["total_line_source_value"]
first_snapshot = archive.drop_duplicates("game_id", keep="first").copy()

try:
    schedule = load_schedule_data()
except Exception as exc:
    st.error(f"Unable to load schedule/final scores: {exc}")
    st.stop()

score_columns = ["game_id", "home_score", "away_score"]
missing_score_columns = [col for col in score_columns if col not in schedule.columns]
if missing_score_columns:
    st.error(f"Schedule source is missing score fields: {missing_score_columns}")
    st.stop()

scores = schedule.copy()
scores["home_score"] = pd.to_numeric(scores["home_score"], errors="coerce")
scores["away_score"] = pd.to_numeric(scores["away_score"], errors="coerce")
scores["gameday"] = pd.to_datetime(scores["gameday"], errors="coerce", utc=True).dt.floor("D")
scores["home_team"] = scores["home_team"].astype(str).str.upper().str.strip()
scores["away_team"] = scores["away_team"].astype(str).str.upper().str.strip()
scores = scores.drop_duplicates("game_id", keep="first")
score_lookup = scores[["game_id", "home_score", "away_score", "gameday", "home_team", "away_team"]].copy()

# Join by source game_id first; use date + both teams only as a fallback.
snapshots_for_join = first_snapshot.copy()
snapshots_for_join["gameday_join"] = pd.to_datetime(
    snapshots_for_join.get("gameday_utc", snapshots_for_join.get("gameday")),
    errors="coerce", utc=True
).dt.floor("D")
for col in ["home_team", "away_team"]:
    if col not in snapshots_for_join.columns:
        snapshots_for_join[col] = ""
    snapshots_for_join[col] = snapshots_for_join[col].astype(str).str.upper().str.strip()

graded = snapshots_for_join.merge(
    score_lookup[["game_id", "home_score", "away_score"]],
    on="game_id", how="left", validate="one_to_one"
)
graded["score_match_method"] = np.where(
    graded["home_score"].notna() & graded["away_score"].notna(), "game_id", ""
)

# Use a strict date + home/away team key only to fill scores missing from the
# game_id join. Update the existing rows rather than appending duplicate rows.
unmatched = graded["home_score"].isna() | graded["away_score"].isna()
fallback_scores = score_lookup.dropna(subset=["gameday", "home_score", "away_score"]).rename(
    columns={"gameday": "gameday_join"}
).drop_duplicates(["gameday_join", "home_team", "away_team"], keep="first")
fallback = graded.loc[unmatched, ["gameday_join", "home_team", "away_team"]].merge(
    fallback_scores[["gameday_join", "home_team", "away_team", "home_score", "away_score"]],
    on=["gameday_join", "home_team", "away_team"], how="left", validate="many_to_one"
)
graded.loc[unmatched, "home_score"] = fallback["home_score"].to_numpy()
graded.loc[unmatched, "away_score"] = fallback["away_score"].to_numpy()
fallback_matched = unmatched & graded["home_score"].notna() & graded["away_score"].notna()
graded.loc[fallback_matched, "score_match_method"] = "date+teams"
graded["final_available"] = graded["home_score"].notna() & graded["away_score"].notna()
graded["actual_margin"] = graded["home_score"] - graded["away_score"]
graded["actual_total"] = graded["home_score"] + graded["away_score"]
graded["ats_edge"] = graded["baseline_predicted_home_margin"] - graded["spread_line_source_value"]
graded["total_edge"] = graded["baseline_projected_total"] - graded["total_line_source_value"]

# Select earliest complete pregame observation separately for each market.
# Incomplete early rows remain visible in the raw archive, but do not block a
# later valid pregame observation from being evaluated.
def first_complete_market_snapshot(edge_col, line_col):
    candidates = archive[
        archive["timing_status"].eq("Definitely before scheduled date")
        & archive[edge_col].notna()
        & archive[line_col].notna()
    ].copy()
    return candidates.drop_duplicates("game_id", keep="first")

ats_selected = first_complete_market_snapshot("ats_edge", "spread_line_source_value")
totals_selected = first_complete_market_snapshot("total_edge", "total_line_source_value")
def attach_scores(selected):
    result = selected.drop(columns=["home_score", "away_score"], errors="ignore").merge(
        graded[["game_id", "home_score", "away_score", "score_match_method"]].drop_duplicates("game_id"),
        on="game_id", how="left", validate="one_to_one"
    )
    result["final_available"] = result["home_score"].notna() & result["away_score"].notna()
    result["actual_margin"] = result["home_score"] - result["away_score"]
    result["actual_total"] = result["home_score"] + result["away_score"]
    result["ats_edge"] = result["baseline_predicted_home_margin"] - result["spread_line_source_value"]
    result["total_edge"] = result["baseline_projected_total"] - result["total_line_source_value"]
    return result

ats_population = attach_scores(ats_selected)
totals_population = attach_scores(totals_selected)
timing_uncertain_count = int(first_snapshot["timing_status"].isin(["Same-day timing uncertain", "Unknown timing"]).sum())
late_capture_count = int(first_snapshot["timing_status"].eq("Captured after scheduled date").sum())
pregame = graded[graded["timing_status"] == "Definitely before scheduled date"].copy()


def grade_market(frame, edge_col, actual_col, line_col):
    market = frame.copy()
    market["line_available"] = market[line_col].notna()
    market["prediction_available"] = market[edge_col].notna()
    market["eligible_edge"] = market[edge_col].abs() >= EDGE_THRESHOLD
    eligible = market[
        market["final_available"]
        & market["line_available"]
        & market["prediction_available"]
        & market["eligible_edge"]
    ].copy()

    # Positive spread_line means home favored in the nflverse schedule convention.
    # Therefore actual home margin minus spread_line is the home ATS cover margin.
    eligible["actual_margin_vs_line"] = eligible[actual_col] - eligible[line_col]
    eligible["result"] = np.select(
        [
            eligible["actual_margin_vs_line"].eq(0),
            eligible["actual_margin_vs_line"] * np.sign(eligible[edge_col]) > 0,
        ],
        ["Push", "Win"],
        default="Loss",
    )
    eligible["units_risked"] = UNIT_RISK
    eligible["net_units"] = np.select(
        [eligible["result"].eq("Win"), eligible["result"].eq("Loss")],
        [WIN_PROFIT_AT_MINUS_110, -UNIT_RISK],
        default=0.0,
    )
    return market, eligible


ats_population, ats = grade_market(ats_population, "ats_edge", "actual_margin", "spread_line_source_value")
totals_population, totals = grade_market(totals_population, "total_edge", "actual_total", "total_line_source_value")

st.subheader("Snapshot coverage and data quality")
a, b, c, d = st.columns(4)
a.metric("Unique games in archive", f"{unique_game_count:,}")
b.metric("Repeated observations not re-graded", f"{duplicate_observations:,}")
c.metric("Games with final scores", f"{int(graded['final_available'].sum()):,}")
d.metric("Unique games with definitely pregame snapshots", f"{pregame['game_id'].nunique():,}")

id_matches = int(graded["score_match_method"].eq("game_id").sum())
fallback_matches = int(graded["score_match_method"].eq("date+teams").sum())
st.caption(f"Final-score join: {id_matches:,} matched by game ID; {fallback_matches:,} matched by scheduled date and teams.")

st.write(
    f"Timing not sufficiently certain for primary grading: **{timing_uncertain_count:,}** games. "
    f"Captured after the scheduled UTC date: **{late_capture_count:,}** games."
)
st.caption(
    "Because the archive does not establish the exact source publication time or exact kickoff timestamp, "
    "same-day captures are excluded from primary performance figures rather than assumed to be pregame."
)


def report(title, population, bets, line_col, edge_col):
    st.subheader(title)
    missing_line = int(population[line_col].isna().sum())
    missing_prediction = int(population[edge_col].isna().sum())
    missing_final = int((~population["final_available"]).sum())
    edge_candidates = population[population[edge_col].notna() & (population[edge_col].abs() >= EDGE_THRESHOLD)]
    no_line_among_candidates = int(edge_candidates[line_col].isna().sum())

    x, y, z = st.columns(3)
    x.metric("Missing market lines", f"{missing_line:,}")
    y.metric("Missing predictions", f"{missing_prediction:,}")
    z.metric("Eligible-edge games missing lines", f"{no_line_among_candidates:,}")

    wins = int(bets["result"].eq("Win").sum())
    losses = int(bets["result"].eq("Loss").sum())
    pushes = int(bets["result"].eq("Push").sum())
    net = float(bets["net_units"].sum())
    risked = float(bets["units_risked"].sum())
    roi = 100 * net / risked if risked else np.nan

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Record (W-L-P)", f"{wins}-{losses}-{pushes}")
    m2.metric("Bets", f"{len(bets):,}")
    m3.metric("Net units", f"{net:+.2f}")
    m4.metric("Units risked", f"{risked:.2f}")
    m5.metric("ROI at assumed -110", f"{roi:+.2f}%" if risked else "—")

    if bets.empty:
        st.info("No games currently meet the data, timing, and fixed 3.5-point edge requirements.")
        return

    cols = [
        "game_id", "captured_at_utc", "scheduled_date_utc", "away_team", "home_team",
        line_col, edge_col, "actual_margin", "actual_total", "result", "net_units",
        "timing_status", "snapshot_file",
    ]
    st.dataframe(
        bets[[col for col in cols if col in bets.columns]].sort_values("captured_at_utc", ascending=False),
        hide_index=True,
        use_container_width=True,
    )


st.caption(
    f"Fixed absolute model-edge threshold: {EDGE_THRESHOLD:.1f} points. One unit risked per bet; wins earn "
    f"{WIN_PROFIT_AT_MINUS_110:.3f} units at assumed -110, losses lose one unit, pushes earn zero. "
    "This convention is illustrative because schedule-feed prices are not verified sportsbook prices."
)
report("ATS results", ats_population, ats, "spread_line_source_value", "ats_edge")
report("Totals results", totals_population, totals, "total_line_source_value", "total_edge")

def threshold_summary(population, edge_col, actual_col, line_col):
    rows = []
    for threshold in [3.5, 4.5, 5.5, 6.5, 7.5]:
        eligible = population[
            population["final_available"]
            & population[line_col].notna()
            & population[edge_col].notna()
            & (population[edge_col].abs() >= threshold)
        ].copy()
        cover_or_total_margin = eligible[actual_col] - eligible[line_col]
        eligible["result"] = np.select(
            [cover_or_total_margin.eq(0), cover_or_total_margin * np.sign(eligible[edge_col]) > 0],
            ["Push", "Win"],
            default="Loss",
        )
        wins = int(eligible["result"].eq("Win").sum())
        losses = int(eligible["result"].eq("Loss").sum())
        pushes = int(eligible["result"].eq("Push").sum())
        bets = wins + losses + pushes
        net = wins * WIN_PROFIT_AT_MINUS_110 - losses
        rows.append({
            "Minimum edge": f"{threshold:.1f}+",
            "Record (W-L-P)": f"{wins}-{losses}-{pushes}",
            "Bets": bets,
            "Net units": round(net, 2),
            "Units risked": bets,
            "ROI %": round(100 * net / bets, 2) if bets else np.nan,
        })
    return pd.DataFrame(rows)

st.subheader("Cumulative edge-threshold records")
st.caption("Each row includes every eligible pick at or above that edge; higher-edge picks also count in lower thresholds. Assumes one unit risked and -110 odds.")
left, right = st.columns(2)
with left:
    st.markdown("**ATS**")
    st.dataframe(threshold_summary(ats_population, "ats_edge", "actual_margin", "spread_line_source_value"), hide_index=True, use_container_width=True)
with right:
    st.markdown("**Totals**")
    st.dataframe(threshold_summary(totals_population, "total_edge", "actual_total", "total_line_source_value"), hide_index=True, use_container_width=True)


# Separately grade the frozen efficiency-model forecasts. These files are created by
# a daily, model-specific job and are never mixed with the scoring-baseline snapshots.
efficiency_files = sorted(SNAPSHOT_DIR.glob("efficiency_projection_*.csv"))
efficiency_parts = []
for path in efficiency_files:
    try:
        frame = pd.read_csv(path, low_memory=False)
        if not frame.empty:
            frame["snapshot_file"] = path.name
            efficiency_parts.append(frame)
    except Exception as exc:
        st.warning(f"Could not read efficiency projection file {path.name}: {exc}")

if efficiency_parts:
    efficiency = pd.concat(efficiency_parts, ignore_index=True, sort=False)
    efficiency["captured_at_utc"] = pd.to_datetime(efficiency["captured_at_utc"], errors="coerce", utc=True)
    efficiency["gameday"] = pd.to_datetime(efficiency["gameday"], errors="coerce", utc=True)
    for col in ["spread_line", "total_line", "model_predicted_home_margin", "model_projected_total", "model_ats_edge", "model_total_edge"]:
        if col not in efficiency:
            efficiency[col] = np.nan
        efficiency[col] = pd.to_numeric(efficiency[col], errors="coerce")
    efficiency["scheduled_date_utc"] = efficiency["gameday"].dt.floor("D")
    efficiency["capture_date_utc"] = efficiency["captured_at_utc"].dt.floor("D")
    efficiency["timing_status"] = np.select(
        [
            efficiency["captured_at_utc"].isna() | efficiency["scheduled_date_utc"].isna(),
            efficiency["capture_date_utc"] < efficiency["scheduled_date_utc"],
            efficiency["capture_date_utc"] == efficiency["scheduled_date_utc"],
            efficiency["capture_date_utc"] > efficiency["scheduled_date_utc"],
        ],
        ["Unknown timing", "Definitely before scheduled date", "Same-day timing uncertain", "Captured after scheduled date"],
        default="Unknown timing",
    )
    efficiency = efficiency.sort_values(["game_id", "captured_at_utc", "snapshot_file"])
    eff_ats_selected = efficiency[
        efficiency["timing_status"].eq("Definitely before scheduled date")
        & efficiency["model_ats_edge"].notna()
        & efficiency["spread_line"].notna()
    ].drop_duplicates("game_id", keep="first").copy()
    eff_totals_selected = efficiency[
        efficiency["timing_status"].eq("Definitely before scheduled date")
        & efficiency["model_total_edge"].notna()
        & efficiency["total_line"].notna()
    ].drop_duplicates("game_id", keep="first").copy()

    eff_score_lookup = score_lookup[
        ["game_id", "home_score", "away_score", "home_team", "away_team"]
    ].drop_duplicates("game_id").rename(
        columns={"home_team": "score_home_team", "away_team": "score_away_team"}
    )

    def attach_efficiency_scores(frame):
        frame = frame.merge(eff_score_lookup, on="game_id", how="left", validate="one_to_one")
        frame["score_team_match"] = frame.apply(
            lambda row: matchup_teams_match(
                row.get("home_team"),
                row.get("away_team"),
                row.get("score_home_team"),
                row.get("score_away_team"),
            ),
            axis=1,
        )
        frame["final_available"] = (
            frame["home_score"].notna()
            & frame["away_score"].notna()
            & frame["score_team_match"]
        )
        mismatch_count = int(
            (
                frame["home_score"].notna()
                & frame["away_score"].notna()
                & ~frame["score_team_match"]
            ).sum()
        )
        if mismatch_count:
            st.error(
                f"{mismatch_count:,} efficiency forecast rows have a game-ID score match but a home/away team mismatch. "
                "Those rows are excluded from grading and should be investigated."
            )
        frame["actual_margin"] = frame["home_score"] - frame["away_score"]
        frame["actual_total"] = frame["home_score"] + frame["away_score"]
        return frame

    eff_ats_population = attach_efficiency_scores(eff_ats_selected)
    eff_totals_population = attach_efficiency_scores(eff_totals_selected)
    _, eff_ats = grade_market(eff_ats_population, "model_ats_edge", "actual_margin", "spread_line")
    _, eff_totals = grade_market(eff_totals_population, "model_total_edge", "actual_total", "total_line")

    st.header("Efficiency-model prospective results")
    st.caption("Separate from the recent-scoring baseline. One earliest eligible pre-scheduled-date snapshot per game and market; schedule-feed lines are not verified sportsbook prices.")
    x, y, z = st.columns(3)
    x.metric("Saved efficiency snapshots", f"{len(efficiency):,}")
    y.metric("Unique games with a clearly pre-scheduled-date forecast", f"{efficiency.loc[efficiency['timing_status'].eq('Definitely before scheduled date'), 'game_id'].nunique():,}")
    z.metric("Model version(s)", ", ".join(sorted(efficiency["model_version"].dropna().astype(str).unique())) if "model_version" in efficiency else "Unknown")

    st.subheader("Efficiency forecast archive diagnostics")
    scheduled_min = efficiency["gameday"].min()
    scheduled_max = efficiency["gameday"].max()
    score_index = score_lookup.set_index("game_id")
    score_home = efficiency["game_id"].map(score_index["home_score"])
    score_away = efficiency["game_id"].map(score_index["away_score"])
    score_home_team = efficiency["game_id"].map(score_index["home_team"])
    score_away_team = efficiency["game_id"].map(score_index["away_team"])
    schedule_match = efficiency["game_id"].isin(score_lookup["game_id"])
    efficiency_team_match = pd.Series(
        [
            matchup_teams_match(home, away, score_home_name, score_away_name)
            for home, away, score_home_name, score_away_name in zip(
                efficiency["home_team"],
                efficiency["away_team"],
                score_home_team,
                score_away_team,
            )
        ],
        index=efficiency.index,
    )
    rows_with_final_scores = score_home.notna() & score_away.notna()
    archive_team_mismatches = int((rows_with_final_scores & ~efficiency_team_match).sum())
    current_day_utc = pd.Timestamp.now(tz="UTC").floor("D")
    scheduled_day = efficiency["gameday"].dt.floor("D")
    upcoming_rows = scheduled_day.ge(current_day_utc) & scheduled_day.notna()
    prior_rows = scheduled_day.lt(current_day_utc) & scheduled_day.notna()
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Earliest scheduled game", f"{scheduled_min:%Y-%m-%d}" if pd.notna(scheduled_min) else "Unavailable")
    d2.metric("Latest scheduled game", f"{scheduled_max:%Y-%m-%d}" if pd.notna(scheduled_max) else "Unavailable")
    d3.metric("Rows with final scores + matching teams", f"{int((rows_with_final_scores & efficiency_team_match).sum()):,}")
    d4.metric("Unique forecast game IDs", f"{efficiency['game_id'].nunique():,}")
    if archive_team_mismatches:
        st.error(
            f"{archive_team_mismatches:,} archived efficiency forecast rows have final scores attached by game ID, "
            "but the saved home/away teams do not match the score feed. These rows must not be trusted for grading."
        )
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Rows matching schedule IDs", f"{int(schedule_match.sum()):,} / {len(efficiency):,}")
    e2.metric("Scheduled today/future", f"{int(upcoming_rows.sum()):,}")
    e3.metric("Scheduled before today", f"{int(prior_rows.sum()):,}")
    e4.metric("Distinct saved forecast files", f"{efficiency['snapshot_file'].nunique():,}")
    st.caption("The collector intentionally saves upcoming games only. Zero final scores is expected while every saved forecast is still scheduled today or later. Once a saved game finishes, its score should appear through the schedule feed; if prior-date rows remain ungraded, inspect the game-ID join and source schedule.")

    # Distinguish raw forecasts from actionable-looking rows and graded results.
    # A line alone is not a bet; the forecast must also clear the fixed edge threshold.
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Games with spread line", f"{int(efficiency['spread_line'].notna().sum()):,}")
    m2.metric("Games with total line", f"{int(efficiency['total_line'].notna().sum()):,}")
    m3.metric("ATS forecasts at 3.5+ edge", f"{int((efficiency['model_ats_edge'].abs() >= EDGE_THRESHOLD).where(efficiency['spread_line'].notna(), False).sum()):,}")
    m4.metric("Totals forecasts at 3.5+ edge", f"{int((efficiency['model_total_edge'].abs() >= EDGE_THRESHOLD).where(efficiency['total_line'].notna(), False).sum()):,}")
    st.caption("Counts above are raw archived rows and can include repeat snapshots. Performance grading below uses only the earliest clearly pre-scheduled-date forecast per game and market.")

    def efficiency_summary(title, population, bets, edge_col, line_col, actual_col):
        wins = int(bets["result"].eq("Win").sum())
        losses = int(bets["result"].eq("Loss").sum())
        pushes = int(bets["result"].eq("Push").sum())
        net = float(bets["net_units"].sum())
        risked = float(bets["units_risked"].sum())
        roi = 100 * net / risked if risked else np.nan
        st.subheader(title)
        a, b, d, e, f = st.columns(5)
        a.metric("Record (W-L-P)", f"{wins}-{losses}-{pushes}")
        b.metric("Bets", f"{len(bets):,}")
        d.metric("Net units", f"{net:+.2f}")
        e.metric("Units risked", f"{risked:.2f}")
        f.metric("ROI at assumed -110", f"{roi:+.2f}%" if risked else "—")
        if not bets.empty:
            display_cols = ["game_id", "captured_at_utc", "away_team", "home_team", line_col, edge_col, "actual_margin", "actual_total", "result", "net_units", "snapshot_file"]
            st.dataframe(bets[[col for col in display_cols if col in bets]].sort_values("captured_at_utc", ascending=False), hide_index=True, use_container_width=True)
        st.dataframe(threshold_summary(population, edge_col, actual_col, line_col), hide_index=True, use_container_width=True)

    efficiency_summary("Efficiency-model ATS", eff_ats_population, eff_ats, "model_ats_edge", "spread_line", "actual_margin")
    efficiency_summary("Efficiency-model totals", eff_totals_population, eff_totals, "model_total_edge", "total_line", "actual_total")

    # Prospective disjoint-band calibration: include all nonzero model edges,
    # not only cumulative thresholds, and preserve season-level diagnostics.
    def prospective_edge_calibration(population, edge_col, actual_col, line_col, label):
        eligible = population[
            population["final_available"]
            & population[line_col].notna()
            & population[edge_col].notna()
            & (population[edge_col].abs() > 0)
        ].copy()
        eligible["absolute_edge"] = pd.to_numeric(eligible[edge_col], errors="coerce").abs()
        eligible["Edge band"] = pd.cut(
            eligible["absolute_edge"],
            bins=[0, 1, 2, 3.5, 4.5, 5.5, 6.5, 7.5, np.inf],
            labels=["0–1", "1–2", "2–3.5", "3.5–4.5", "4.5–5.5", "5.5–6.5", "6.5–7.5", "7.5+"],
            right=False,
            include_lowest=True,
        )
        margin = pd.to_numeric(eligible[actual_col], errors="coerce") - pd.to_numeric(eligible[line_col], errors="coerce")
        eligible["result"] = np.select(
            [margin.eq(0), margin * np.sign(pd.to_numeric(eligible[edge_col], errors="coerce")) > 0],
            ["Push", "Win"],
            default="Loss",
        )
        eligible["net_units"] = np.select(
            [eligible["result"].eq("Win"), eligible["result"].eq("Loss")],
            [WIN_PROFIT_AT_MINUS_110, -1.0],
            default=0.0,
        )
        eligible["units_risked"] = 1.0

        def summarize_bands(group_cols):
            rows = []
            grouped = eligible.groupby(group_cols[0] if len(group_cols) == 1 else group_cols, observed=False, dropna=False)
            for key, part in grouped:
                wins = int(part["result"].eq("Win").sum())
                losses = int(part["result"].eq("Loss").sum())
                pushes = int(part["result"].eq("Push").sum())
                bets = len(part)
                decisions = wins + losses
                net = float(part["net_units"].sum())
                row = {
                    "Bets": bets,
                    "Wins": wins,
                    "Losses": losses,
                    "Pushes": pushes,
                    "Win % (no pushes)": round(100 * wins / decisions, 2) if decisions else np.nan,
                    "Net units": round(net, 2),
                    "ROI %": round(100 * net / bets, 2) if bets else np.nan,
                }
                if len(group_cols) == 1:
                    row[group_cols[0]] = key
                else:
                    row.update(dict(zip(group_cols, key)))
                rows.append(row)
            return pd.DataFrame(rows)

        st.subheader(f"Prospective {label}: disjoint edge bands")
        st.caption("Each game is counted once per market, using its earliest clearly pre-scheduled-date model forecast with a nonzero edge and final score. Bands are disjoint; returns assume one unit risked and -110 odds.")

        # Show why the table may be empty instead of presenting zeroes without context.
        diagnostic_cols = st.columns(5)
        diagnostic_cols[0].metric("Selected forecasts", f"{len(population):,}")
        diagnostic_cols[1].metric("With market line", f"{int(population[line_col].notna().sum()):,}")
        diagnostic_cols[2].metric("With nonzero edge", f"{int((pd.to_numeric(population[edge_col], errors='coerce').abs() > 0).sum()):,}")
        diagnostic_cols[3].metric("With final score", f"{int(population['final_available'].sum()):,}")
        valid_count = int((
            population["final_available"]
            & population[line_col].notna()
            & pd.to_numeric(population[edge_col], errors="coerce").notna()
            & (pd.to_numeric(population[edge_col], errors="coerce").abs() > 0)
        ).sum())
        diagnostic_cols[4].metric("Gradeable nonzero edges", f"{valid_count:,}")
        if valid_count == 0:
            st.info(
                "No rows qualify for calibration yet. Use the counts above to identify the gap: "
                "missing saved forecasts, missing market lines, missing final scores, or zero/missing model edges."
            )

        summary = summarize_bands(["Edge band"])
        if not summary.empty:
            summary = summary[["Edge band", "Bets", "Wins", "Losses", "Pushes", "Win % (no pushes)", "Net units", "ROI %"]]
            st.dataframe(summary, hide_index=True, use_container_width=True)
            st.download_button(
                f"Download prospective {label.lower()} edge-band CSV",
                summary.to_csv(index=False).encode("utf-8"),
                f"prospective_{label.lower().replace(' ', '_')}_edge_bands.csv",
                "text/csv",
                on_click="ignore",
            )
        if "season" in eligible.columns:
            season_summary = summarize_bands(["season", "Edge band"])
            if not season_summary.empty:
                season_summary = season_summary.rename(columns={"season": "Season"})
                season_summary = season_summary[["Season", "Edge band", "Bets", "Wins", "Losses", "Pushes", "Win % (no pushes)", "Net units", "ROI %"]]
                st.caption("Season breakdown for the same prospective observations; current partial seasons should not be compared directly with completed seasons.")
                st.dataframe(season_summary, hide_index=True, use_container_width=True)
                st.download_button(
                    f"Download prospective {label.lower()} edge bands by season CSV",
                    season_summary.to_csv(index=False).encode("utf-8"),
                    f"prospective_{label.lower().replace(' ', '_')}_edge_bands_by_season.csv",
                    "text/csv",
                    on_click="ignore",
                )

    prospective_edge_calibration(eff_ats_population, "model_ats_edge", "actual_margin", "spread_line", "ATS")
    prospective_edge_calibration(eff_totals_population, "model_total_edge", "actual_total", "total_line", "totals")
    st.download_button(
        "Download efficiency-model projection archive",
        data=efficiency.to_csv(index=False).encode("utf-8"),
        file_name="prospective_efficiency_projection_archive.csv",
        mime="text/csv",
        on_click="ignore",
    )
else:
    st.header("Efficiency-model prospective results")
    st.info("No efficiency-model projection files have been saved yet. The daily GitHub Actions workflow must complete successfully before this section can grade the stronger model.")

st.warning(
    "Important limitations: the saved line fields come from a public schedule feed and are not verified executable "
    "sportsbook prices or odds. The audit grades the first saved snapshot per game and never overwrites it with a later "
    "capture. Same-day/unknown timing is excluded from primary results. Injury-feed coverage is descriptive only; "
    "this page does not establish that the model had complete or actionable injury information."
)

st.subheader("Download audit data")
st.download_button(
    "Download raw snapshot audit archive (all observations)",
    data=archive.to_csv(index=False).encode("utf-8"),
    file_name="prospective_results_audit.csv",
    mime="text/csv",
            on_click="ignore"
        
)
st.download_button(
    "Download eligible ATS bets",
    data=ats.to_csv(index=False).encode("utf-8"),
    file_name="prospective_ats_graded.csv",
    mime="text/csv",
            on_click="ignore"
        
)
st.download_button(
    "Download eligible totals bets",
    data=totals.to_csv(index=False).encode("utf-8"),
    file_name="prospective_totals_graded.csv",
    mime="text/csv",
            on_click="ignore"
        
)


# Verified EndzoneAPI bookmaker archive. Kept separate from schedule-feed results above:
# spread_home uses the sportsbook team-handicap convention (e.g. home -3 when favored),
# which is the opposite sign of nflverse's spread_line (positive when home is favored).
odds_files = sorted(SNAPSHOT_DIR.glob("endzone_odds_*.csv"))
if odds_files:
    st.subheader("Verified sportsbook odds — EndzoneAPI")
    st.caption(
        "Bookmaker-specific odds are audited separately from schedule-feed backtests. "
        "A row is eligible for future prospective grading only when its frozen model prediction "
        "predates the provider's odds timestamp and that timestamp predates kickoff."
    )
    odds_parts = []
    odds_errors = []
    for path in odds_files:
        try:
            frame = pd.read_csv(path, low_memory=False)
            if not frame.empty:
                frame["odds_file"] = path.name
                odds_parts.append(frame)
        except Exception as exc:
            odds_errors.append(f"{path.name}: {exc}")
    for message in odds_errors:
        st.warning(f"Could not read EndzoneAPI file — {message}")
    if odds_parts:
        odds = pd.concat(odds_parts, ignore_index=True, sort=False)
        for col in ["captured_at_utc", "source_snapshot_at_utc", "kickoff_utc"]:
            if col not in odds:
                odds[col] = pd.NaT
            odds[col] = pd.to_datetime(odds[col], errors="coerce", utc=True)
        for col in [
            "spread_home", "spread_home_odds", "spread_away", "spread_away_odds",
            "total", "total_over_odds", "total_under_odds", "home_moneyline", "away_moneyline",
        ]:
            if col not in odds:
                odds[col] = np.nan
            odds[col] = pd.to_numeric(odds[col], errors="coerce")
        for col in ["home_team", "away_team"]:
            if col not in odds.columns:
                odds[col] = ""
            odds[col] = odds[col].astype(str).str.upper().str.strip()

        # Core identifiers determine whether a quote can be matched and deduplicated.
        # Keep malformed rows visible for diagnosis, but never let blank identifiers
        # accidentally collapse into one bookmaker/game during selection.
        missing_core_columns = [
            col for col in ["game_id", "bookmaker", "snapshot_type"] if col not in odds.columns
        ]
        for col in missing_core_columns:
            odds[col] = ""
        odds["game_id"] = odds["game_id"].fillna("").astype(str).str.strip()
        odds["bookmaker"] = odds["bookmaker"].fillna("").astype(str).str.strip()
        odds["snapshot_type"] = odds["snapshot_type"].fillna("").astype(str).str.strip()
        odds["core_identifiers_valid"] = (
            odds["game_id"].ne("")
            & odds["bookmaker"].ne("")
            & odds["snapshot_type"].str.lower().eq("latest")
        )
        if missing_core_columns:
            st.warning(
                "Some EndzoneAPI archive files are missing required identifier columns "
                f"({', '.join(missing_core_columns)}). Those rows are retained for inspection "
                "but excluded from strict eligibility."
            )
        elif not odds["core_identifiers_valid"].all():
            st.caption(
                f"{int((~odds['core_identifiers_valid']).sum()):,} odds rows have blank identifiers "
                "or a snapshot type other than 'latest'; they are not eligible for strict grading."
            )
        odds["provider_time_before_kickoff"] = (
            odds["source_snapshot_at_utc"].notna()
            & odds["kickoff_utc"].notna()
            & (odds["source_snapshot_at_utc"] < odds["kickoff_utc"])
        )
        odds["source_time_not_future_of_capture"] = (
            odds["source_snapshot_at_utc"].notna()
            & odds["captured_at_utc"].notna()
            & (odds["source_snapshot_at_utc"] <= odds["captured_at_utc"])
        )

        # Attach exactly one prediction per odds row: the most recent frozen
        # efficiency projection for the same game/teams captured at or before the
        # provider's odds timestamp. A plain merge multiplies rows when several
        # daily predictions exist for the same game and can leak future predictions.
        # Use object dtype for timestamp assignment, then normalize to UTC after matching.
        # This avoids pandas rejecting tz-aware timestamps assigned into a tz-naive datetime column.
        odds["prediction_captured_at_utc"] = pd.Series([None] * len(odds), index=odds.index, dtype="object")
        odds["model_predicted_home_margin"] = np.nan
        odds["model_projected_total"] = np.nan
        odds["prediction_team_match"] = False
        odds["prediction_precedes_odds"] = False

        if "efficiency" in locals() and not efficiency.empty:
            pred_cols = [
                "game_id", "captured_at_utc", "model_predicted_home_margin",
                "model_projected_total", "home_team", "away_team",
            ]
            preds = efficiency[[col for col in pred_cols if col in efficiency.columns]].copy()
            preds["game_id"] = preds["game_id"].astype(str)
            preds["captured_at_utc"] = pd.to_datetime(
                preds["captured_at_utc"], errors="coerce", utc=True
            )
            preds["home_team"] = preds["home_team"].astype(str).str.upper().str.strip()
            preds["away_team"] = preds["away_team"].astype(str).str.upper().str.strip()

            # Positional indices preserve each bookmaker/snapshot row without row multiplication.
            for idx, odds_row in odds.iterrows():
                candidates = preds[
                    preds["game_id"].eq(str(odds_row["game_id"]))
                    & preds["home_team"].eq(odds_row["home_team"])
                    & preds["away_team"].eq(odds_row["away_team"])
                    & preds["captured_at_utc"].notna()
                    & pd.notna(odds_row["source_snapshot_at_utc"])
                    & (preds["captured_at_utc"] <= odds_row["source_snapshot_at_utc"])
                ].sort_values("captured_at_utc")
                if candidates.empty:
                    continue
                pred = candidates.iloc[-1]
                odds.at[idx, "prediction_captured_at_utc"] = pred["captured_at_utc"]
                odds.at[idx, "model_predicted_home_margin"] = pred["model_predicted_home_margin"]
                odds.at[idx, "model_projected_total"] = pred["model_projected_total"]
                odds.at[idx, "prediction_team_match"] = True
                odds.at[idx, "prediction_precedes_odds"] = True

        odds["prediction_captured_at_utc"] = pd.to_datetime(
            odds["prediction_captured_at_utc"], errors="coerce", utc=True
        )

        odds["endzone_ats_edge"] = odds["model_predicted_home_margin"] + odds["spread_home"]
        odds["endzone_total_edge"] = odds["model_projected_total"] - odds["total"]

        # Always show directional leans when the corresponding market line and
        # model projection exist. Edge thresholds classify stronger candidates;
        # they do not suppress the lean itself.
        odds["ATS lean"] = np.select(
            [
                odds["spread_home"].isna() | odds["model_predicted_home_margin"].isna(),
                odds["endzone_ats_edge"] > 0,
                odds["endzone_ats_edge"] < 0,
            ],
            ["No ATS lean (line/prediction unavailable)", "Home team lean", "Away team lean"],
            default="No directional ATS lean",
        )
        odds["Total lean"] = np.select(
            [
                odds["total"].isna() | odds["model_projected_total"].isna(),
                odds["endzone_total_edge"] > 0,
                odds["endzone_total_edge"] < 0,
            ],
            ["No total lean (line/prediction unavailable)", "Over lean", "Under lean"],
            default="No directional total lean",
        )
        odds["ATS edge qualifies (3.5+)"] = (
            odds["endzone_ats_edge"].abs() >= EDGE_THRESHOLD
        ) & odds["model_predicted_home_margin"].notna() & odds["spread_home"].notna()
        odds["Total edge qualifies (3.5+)"] = (
            odds["endzone_total_edge"].abs() >= EDGE_THRESHOLD
        ) & odds["model_projected_total"].notna() & odds["total"].notna()

        odds["timing_eligible"] = (
            odds["provider_time_before_kickoff"]
            & odds["source_time_not_future_of_capture"]
            & odds["prediction_precedes_odds"]
            & odds["prediction_team_match"]
            & odds["core_identifiers_valid"]
        )

        # Explicit eligibility funnel: distinguish quote availability from a
        # fully gradeable, point-in-time model/market observation.
        st.subheader("EndzoneAPI timing and price-quality funnel")
        funnel_cols = st.columns(5)
        funnel_cols[0].metric("Odds rows", f"{len(odds):,}")
        funnel_cols[1].metric(
            "Provider timestamp before kickoff",
            f"{int(odds['provider_time_before_kickoff'].sum()):,}",
        )
        funnel_cols[2].metric(
            "Prediction matched before odds",
            f"{int((odds['prediction_precedes_odds'] & odds['prediction_team_match']).sum()):,}",
        )
        funnel_cols[3].metric(
            "Timing-eligible rows",
            f"{int(odds['timing_eligible'].sum()):,}",
        )
        price_complete = (
            odds["spread_home"].notna()
            & odds["spread_home_odds"].notna()
            & odds["spread_away_odds"].notna()
            & odds["total"].notna()
            & odds["total_over_odds"].notna()
            & odds["total_under_odds"].notna()
        )
        funnel_cols[4].metric(
            "Timing-eligible with both markets/prices",
            f"{int((odds['timing_eligible'] & price_complete).sum()):,}",
        )
        st.caption(
            "Counts are quote rows, not unique games or bets. Missing timestamps, unmatched predictions, "
            "or missing market prices prevent a row from qualifying for the strict prospective grade. "
            "A timing-eligible row is not automatically a bet: the model must also have a nonzero edge, "
            "a valid selected snapshot, a final score, and the price for the recommended side."
        )

        # Join final scores so completed archive games can eventually be graded
        # at actual American prices. Unfinished games remain ungraded.
        score_lookup_odds = scores[
            ["game_id", "home_score", "away_score", "home_team", "away_team"]
        ].drop_duplicates("game_id").rename(
            columns={"home_team": "score_home_team", "away_team": "score_away_team"}
        )
        odds["game_id"] = odds["game_id"].astype(str)
        score_lookup_odds["game_id"] = score_lookup_odds["game_id"].astype(str)
        odds = odds.merge(score_lookup_odds, on="game_id", how="left", validate="many_to_one")
        # A matching game ID is necessary but not sufficient: fail closed if the
        # score feed's home/away teams disagree with the saved odds matchup.
        odds["score_team_match"] = (
            odds["home_team"].astype(str).str.upper().str.strip().eq(
                odds["score_home_team"].astype(str).str.upper().str.strip()
            )
            & odds["away_team"].astype(str).str.upper().str.strip().eq(
                odds["score_away_team"].astype(str).str.upper().str.strip()
            )
        )
        odds["final_available"] = (
            odds["home_score"].notna()
            & odds["away_score"].notna()
            & odds["score_team_match"]
        )
        odds["actual_home_margin"] = odds["home_score"] - odds["away_score"]
        odds["actual_total"] = odds["home_score"] + odds["away_score"]
        mismatch_count = int(
            (odds["home_score"].notna() & odds["away_score"].notna() & ~odds["score_team_match"]).sum()
        )
        if mismatch_count:
            st.error(
                f"{mismatch_count:,} odds rows have a game-ID match but a home/away team mismatch in the score feed. "
                "Those rows are excluded from grading and should be investigated."
            )

        from research.actual_price_grading import grade_actual_price

        # Only one predeclared snapshot type is eligible for grading. Opening and
        # closing rows remain visible for line-movement analysis but cannot be
        # counted as additional bets alongside the latest snapshot.
        odds["ATS result"] = "Pending/Not eligible"
        odds["ATS net units"] = pd.Series(np.nan, index=odds.index, dtype="float64")
        odds["ATS units risked"] = pd.Series(np.nan, index=odds.index, dtype="float64")
        odds["Totals result"] = "Pending/Not eligible"
        odds["Totals net units"] = pd.Series(np.nan, index=odds.index, dtype="float64")
        odds["Totals units risked"] = pd.Series(np.nan, index=odds.index, dtype="float64")
        latest_mask = odds["snapshot_type"].astype(str).str.lower().eq("latest")
        odds["selected_for_grading"] = False
        latest_odds = odds.loc[latest_mask & odds["timing_eligible"]].copy()
        if not latest_odds.empty:
            # Across repeated captures, select only the most recent eligible quote
            # per game and bookmaker. This prevents daily recaptures of the same
            # game/book from being counted as multiple bets. Different bookmakers
            # remain separate executable prices, but are reported as quotes and
            # unique games separately in the summary.
            latest_odds = latest_odds.sort_values("source_snapshot_at_utc")
            selected = latest_odds.drop_duplicates(
                subset=["game_id", "bookmaker"], keep="last"
            )
            odds.loc[selected.index, "selected_for_grading"] = True
            ats_grades = selected.apply(lambda row: grade_actual_price(row, "ATS", EDGE_THRESHOLD), axis=1)
            totals_grades = selected.apply(lambda row: grade_actual_price(row, "Totals", EDGE_THRESHOLD), axis=1)
            # DataFrame.apply(axis=1) returns a Series of dictionaries here.
            # Normalize it into a DataFrame before selecting result/net-unit fields.
            for result_col, grades, source_col in [
                ("ATS result", ats_grades, "result"),
                ("ATS net units", ats_grades, "net_units"),
                ("ATS units risked", ats_grades, "units_risked"),
                ("Totals result", totals_grades, "result"),
                ("Totals net units", totals_grades, "net_units"),
                ("Totals units risked", totals_grades, "units_risked"),
            ]:
                grade_values = pd.DataFrame(grades.tolist(), index=selected.index)
                full_values = pd.Series(np.nan, index=odds.index, dtype="object")
                if source_col == "result":
                    values = grade_values[source_col].fillna("Not gradable").astype(str).to_numpy()
                else:
                    values = pd.to_numeric(
                        grade_values[source_col], errors="coerce"
                    ).astype("float64").to_numpy()
                full_values.loc[selected.index] = values
                odds[result_col] = full_values

        # Keep the strict eligibility flag defined above, including valid core identifiers.
        odds["timing_status"] = np.select(
            [
                ~odds["provider_time_before_kickoff"],
                ~odds["source_time_not_future_of_capture"],
                ~odds["prediction_team_match"],
                ~odds["prediction_precedes_odds"],
                ~odds["core_identifiers_valid"],
            ],
            [
                "Provider timestamp missing/after kickoff",
                "Provider timestamp after collector capture",
                "No matching frozen prediction/team pairing",
                "Prediction missing or captured after odds",
                "Missing identifier or not selected snapshot type",
            ],
            default="Timing checks passed",
        )
        st.write(
            f"Saved bookmaker rows: **{len(odds):,}** · "
            f"Games: **{odds['game_id'].nunique():,}** · "
            f"Rows passing prediction/odds/kickoff timing checks: **{int(odds['timing_eligible'].sum()):,}**"
        )
        display_cols = [
            "game_id", "away_team", "home_team", "bookmaker", "snapshot_type", "selected_for_grading",
            "source_snapshot_at_utc", "kickoff_utc", "spread_home", "spread_home_odds",
            "spread_away", "spread_away_odds", "total", "total_over_odds", "total_under_odds",
            "model_predicted_home_margin", "model_projected_total", "endzone_ats_edge",
            "endzone_total_edge", "ATS lean", "Total lean", "ATS edge qualifies (3.5+)",
            "Total edge qualifies (3.5+)", "ATS result", "ATS net units",
            "ATS units risked", "Totals result", "Totals net units", "Totals units risked",
            "timing_status", "odds_file",
        ]
        st.dataframe(
            odds[[c for c in display_cols if c in odds.columns]].sort_values(
                ["game_id", "bookmaker", "source_snapshot_at_utc"], ascending=[True, True, False]
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Sign convention: EndzoneAPI spread_home is the home team's signed handicap (negative means home favored); "
            "the model's home-margin ATS edge is projected home margin + spread_home. "
            "Directional leans are shown for every row with a valid projection and market line, even when the edge is below "
            "the 3.5-point candidate threshold. The actual-price performance record grades only edges meeting the fixed "
            "3.5-point threshold; below-threshold rows remain visible but are excluded from the record. Completed eligible "
            "games are graded at the recorded American price; upcoming games remain pending. These are hypothetical model "
            "results, not proof of a durable betting edge."
        )
        for market_label, result_col, units_col, risk_col in [
            ("ATS", "ATS result", "ATS net units", "ATS units risked"),
            ("Totals", "Totals result", "Totals net units", "Totals units risked"),
        ]:
            graded_rows = odds[odds[result_col].isin(["Win", "Loss", "Push"])].copy()
            if not graded_rows.empty:
                wins = int(graded_rows[result_col].eq("Win").sum())
                losses = int(graded_rows[result_col].eq("Loss").sum())
                pushes = int(graded_rows[result_col].eq("Push").sum())
                net_units = float(graded_rows[units_col].sum())
                risked = float(graded_rows[risk_col].sum())
                roi = (net_units / risked * 100.0) if risked else np.nan
                st.write(
                    f"**{market_label} actual-price record (latest snapshots only, quote-weighted):** "
                    f"{wins}-{losses}-{pushes}; net {net_units:+.2f} units; "
                    f"ROI {roi:+.1f}%; {graded_rows['game_id'].nunique()} unique games across "
                    f"{len(graded_rows)} sportsbook quotes."
                )
                st.caption(
                    "This aggregate weights each graded sportsbook quote as one hypothetical bet, so games "
                    "with more eligible book quotes can contribute more than once. Quotes on the same game are "
                    "not independent game outcomes; different lines and prices can also produce different grades. "
                    "Use the quote count to understand the calculation, not as the number of independent games."
                )
                by_game = graded_rows.groupby("game_id").agg(
                    result_count=(result_col, "count"),
                    unique_results=(result_col, "nunique"),
                )
                if (by_game["unique_results"] > 1).any():
                    st.warning(
                        f"{market_label}: sportsbook quotes for the same game disagree on the lean/result. "
                        "Review line/price normalization before interpreting aggregate ROI."
                    )
