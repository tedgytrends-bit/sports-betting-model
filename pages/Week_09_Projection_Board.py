"""Week 9: ONE official, timestamped QB-aware Injury forecast per upcoming game.

Sunday/Monday predictions are immutable once published. No model is retrained
on page load. The original Thursday projection, prior Injury v1 and four-model
research datasets stay in source archives rather than competing on this board.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "data/public_snapshots/nfl_week09_final_injury_2026-11-08.csv"
MARKET = ROOT / "data/bovada_lines.csv"
BASE = "https://github.com/tedgytrends-bit/sports-betting-model/blob/main/"
ORIGINAL = BASE + "data/public_snapshots/nfl_week_09_six_model_research_2026-11-04.csv"
ORIGINAL_INJURY = BASE + "data/public_snapshots/nfl_week09_injury_qb_epa_margin_2026-11-05.csv"
FINAL_LINK = BASE + "data/public_snapshots/nfl_week09_final_injury_2026-11-08.csv"
TEAM_ALIASES = {"LA": "LAR"}


def team(x):
    t = str(x).upper().strip()
    return TEAM_ALIASES.get(t, t)


def check_columns(frame, names, label):
    missing = set(names) - set(frame.columns)
    if missing:
        st.error(f"{label} missing columns: {sorted(missing)}")
        st.stop()


def lean(row, quote):
    a, h, total = (float(row[k]) for k in
                   ("projected_away", "projected_home", "projected_total"))
    home_line = float(quote["home_favorite_spread"])
    total_line = float(quote["total_line"])
    edge = (h-a) - home_line
    away, home = team(row["away_team"]), team(row["home_team"])
    if abs(edge) < 1e-9:
        ats = "No ATS edge"
    elif edge > 0:
        ats = f"{home} {(-home_line):+g}"
    else:
        ats = f"{away} {home_line:+g}"
    total_side = "Over" if total > total_line else "Under" if total < total_line else "Even"
    fav = home if home_line > 0 else away if home_line < 0 else "Pick'em"
    return {
        "_date": pd.to_datetime(row["gameday"], errors="coerce"),
        "Game": f"{away} @ {home}",
        "Bovada": f"{fav} -{abs(home_line):g} · O/U {total_line:g}" if home_line else f"Pick'em · O/U {total_line:g}",
        "Projected score": f"{away} {a:.1f} – {home} {h:.1f}",
        "ATS lean": ats,
        "Projected total": round(total, 1),
        "Total lean": f"{total_side} {total_line:g}",
        "Starting QBs": f"{row['away_qb_name']} / {row['home_qb_name']}",
        "QB verification": "Both verified" if row["away_qb_starter_source"] == "verified_pregame"
                           and row["home_qb_starter_source"] == "verified_pregame" else "Includes provisional listing",
    }


st.title("NFL Week 9 — Final Projections")
st.caption("One QB-aware Injury model · 14 Sunday/Monday games · Previous snapshots are retained separately.")

if not FINAL.exists() or not MARKET.exists():
    st.error("The final 14-game Injury release or Bovada archive is missing. No fallback projections will be shown.")
    st.stop()

pred = pd.read_csv(FINAL, low_memory=False)
quotes = pd.read_csv(MARKET, low_memory=False)
check_columns(pred, [
    "game_id", "gameday", "season", "week", "model", "model_version",
    "publication_status", "published_at_utc", "away_team", "home_team",
    "projected_away", "projected_home", "projected_total",
    "home_qb_name", "away_qb_name", "home_qb_starter_source",
    "away_qb_starter_source", "home_injury_report_available",
    "away_injury_report_available",
], "Final Injury")
check_columns(quotes, ["season", "week", "away_team", "home_team",
                       "captured_at_utc", "home_favorite_spread", "total_line"], "Bovada")

pred = pred[
    pd.to_numeric(pred.season, errors="coerce").eq(2026)
    & pd.to_numeric(pred.week, errors="coerce").eq(9)
].copy()
if len(pred) != 14 or pred.game_id.nunique() != 14 or "2026_09_JAX_BAL" in set(pred.game_id):
    st.error("Final Injury snapshot must have exactly 14 unique unplayed games.")
    st.stop()
if not pred.model.eq("injury").all() or not pred.publication_status.eq("FINAL_PREGAME_2026_WEEK09_SUN_MON").all():
    st.error("Final Injury publication metadata is invalid.")
    st.stop()
if not (pred.home_injury_report_available.eq(1) & pred.away_injury_report_available.eq(1)).all():
    st.error("A finalized game lacks required injury-report coverage.")
    st.stop()
for col in ["projected_away", "projected_home", "projected_total"]:
    if pd.to_numeric(pred[col], errors="coerce").isna().any():
        st.error(f"Invalid model score: {col}")
        st.stop()

quotes = quotes[
    pd.to_numeric(quotes.season, errors="coerce").eq(2026)
    & pd.to_numeric(quotes.week, errors="coerce").eq(9)
].copy()
quotes["captured_at_utc"] = pd.to_datetime(quotes.captured_at_utc, utc=True, errors="coerce")
quotes["key"] = quotes.away_team.map(team) + "@" + quotes.home_team.map(team)
market = (quotes.dropna(subset=["captured_at_utc"])
          .sort_values("captured_at_utc").drop_duplicates("key", keep="last")
          .set_index("key"))
if len(market) != 15:
    st.error("Week 9 Bovada archive must contain 15 unique game quotes.")
    st.stop()

dates = pd.to_datetime(pred.published_at_utc, utc=True, errors="coerce")
if dates.isna().any() or dates.nunique() != 1:
    st.error("Final Injury scores do not share a valid publication timestamp.")
    st.stop()
published_ct = dates.iloc[0].tz_convert("America/Chicago").strftime("%b %d, %I:%M %p CT")
st.caption(
    f"Final pregame model released **{published_ct}**. Scores are frozen; Bovada prices "
    "come from the latest saved screenshots and may differ from today's live lines. "
    "Questionable designations and unverified starter listings may change on game day."
)

rows = []
for _, game in pred.iterrows():
    key = team(game.away_team) + "@" + team(game.home_team)
    if key not in market.index:
        st.error(f"No Bovada screenshot for {key}.")
        st.stop()
    rows.append(lean(game, market.loc[key]))
board = pd.DataFrame(rows).sort_values(["_date", "Game"]).drop(columns=["_date"])

st.subheader("Official Week 9 Injury forecast")
st.dataframe(board, hide_index=True, width="stretch")
st.caption("One projected score, ATS lean and total lean per matchup. This is a pregame model release, not betting advice.")

with st.expander("QB EPA inputs and starter confirmation"):
    details = []
    for _, g in pred.iterrows():
        for side in ("away", "home"):
            details.append({
                "Game": team(g.away_team) + " @ " + team(g.home_team),
                "Team": team(g[f"{side}_team"]),
                "Expected QB": g[f"{side}_qb_name"],
                "Source": "Verified pregame" if g[f"{side}_qb_starter_source"] == "verified_pregame" else "Provisional schedule",
                "Prior dropbacks": g.get(f"{side}_qb_prior_dropbacks"),
                "Incremental QB EPA/dropback": g.get(f"{side}_qb_delta_epa_per_dropback"),
            })
    st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch")
    st.caption(
        "A documented starter choice is not the same as a final game-day inactive list. "
        "EPA values are shrunk for small samples; QB impact is capped at five points per team."
    )

with st.expander("Bovada screenshot archive and model methodology"):
    st.dataframe(
        market.loc[[team(r.away_team)+"@"+team(r.home_team) for _, r in pred.iterrows()],
                   ["home_favorite_spread","total_line","captured_at_utc"]]
        .reset_index().rename(columns={"key":"Game","captured_at_utc":"Source reference UTC"}),
        hide_index=True, width="stretch"
    )
    st.markdown(f"[Final Injury source]({FINAL_LINK}) · [Original six-model research snapshot]({ORIGINAL}) · "
                f"[Earlier Injury version]({ORIGINAL_INJURY})")
    st.caption("Baseline, Efficiency and Combined remain available for internal research, not as competing public predictions. "
               "Thursday's completed game is excluded from the upcoming slate and remains historically archived.")
