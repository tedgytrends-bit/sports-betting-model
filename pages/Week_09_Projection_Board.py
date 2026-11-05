"""Week 9 read-only pregame snapshot board.

The primary numbers come from a committed, immutable, chronological research
snapshot (not from the legacy six-game scoring baseline on Projection Board).
Market quotes come only from user-provided Bovada screenshots archived in CSV.
No model is retrained on page load. No result grading is performed here.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "public_snapshots" / "nfl_week_09_six_model_research_2026-11-04.csv"
BOVADA = ROOT / "data" / "bovada_lines.csv"
ARCHIVE_URL = (
    "https://github.com/tedgytrends-bit/sports-betting-model/blob/main/"
    "data/public_snapshots/nfl_week_09_six_model_research_2026-11-04.csv"
)
MODEL_NAMES = (
    "baseline", "injury", "efficiency", "combined", "baseline_hl1", "injury_hl4"
)
TEAM_ALIASES = {"LA": "LAR"}


def team(value: object) -> str:
    text = str(value).strip().upper()
    return TEAM_ALIASES.get(text, text)


def num(value: float) -> str:
    return f"{float(value):g}"


def signed(value: float) -> str:
    return f"{float(value):+g}"


def score(away: str, home: str, prediction: pd.Series) -> str:
    return (
        f"{away} {float(prediction['projected_away']):.1f} "
        f"— {home} {float(prediction['projected_home']):.1f}"
    )


def ats_lean(away: str, home: str, prediction: pd.Series, home_favored: float) -> str:
    home_margin = float(prediction["projected_home"]) - float(prediction["projected_away"])
    edge = home_margin - float(home_favored)
    if edge > 0:
        return f"Lean {home} {signed(-home_favored)}"
    if edge < 0:
        return f"Lean {away} {signed(home_favored)}"
    return "No edge"


def total_lean(prediction: pd.Series, market_total: float) -> str:
    projected_total = float(prediction["projected_total"])
    word = "Over" if projected_total > market_total else "Under" if projected_total < market_total else "Even"
    return f"{projected_total:.1f} ({word})"


st.title("NFL Week 9 — Projections")
st.caption("Frozen model snapshot · User-verified Bovada market board · 2026 regular season")
st.info(
    "This is the Week 9 **research projection board**, not an official graded betting record. "
    "Baseline here means the evaluated 24-feature efficiency model, **not** the legacy "
    "six-game scoring formula on the old Projection Board."
)

if not SNAPSHOT.exists() or not BOVADA.exists():
    st.error("The frozen Week 9 projections or saved Bovada archive are missing.")
    st.stop()

predictions = pd.read_csv(SNAPSHOT, low_memory=False)
lines = pd.read_csv(BOVADA, low_memory=False)
required_preds = {
    "captured_at_utc", "game_id", "season", "week", "gameday",
    "away_team", "home_team", "model", "projected_away", "projected_home",
    "projected_total", "home_injury_report_available", "away_injury_report_available",
}
required_lines = {
    "captured_at_utc", "season", "week", "away_team", "home_team",
    "home_favorite_spread", "total_line", "away_spread_price",
    "home_spread_price", "over_price", "under_price",
}
if not required_preds.issubset(predictions.columns) or not required_lines.issubset(lines.columns):
    st.error("Saved snapshot schema changed; refusing to silently display mismatched values.")
    st.stop()

predictions = predictions[
    pd.to_numeric(predictions["season"], errors="coerce").eq(2026)
    & pd.to_numeric(predictions["week"], errors="coerce").eq(9)
].copy()
predictions = predictions[predictions["model"].isin(MODEL_NAMES)].copy()
if predictions.duplicated(["game_id", "model"]).any():
    st.error("Duplicate model predictions detected for the same game.")
    st.stop()
common = predictions.groupby("game_id")["model"].nunique()
if len(common) != 15 or (common != len(MODEL_NAMES)).any():
    st.error("Incomplete Week 9 model snapshot; expected six models for all 15 games.")
    st.stop()

lines = lines[
    pd.to_numeric(lines["season"], errors="coerce").eq(2026)
    & pd.to_numeric(lines["week"], errors="coerce").eq(9)
].copy()
lines["captured_at_utc"] = pd.to_datetime(lines["captured_at_utc"], errors="coerce", utc=True)
lines["game_key"] = lines["away_team"].map(team) + "@" + lines["home_team"].map(team)
lines = lines.dropna(subset=["captured_at_utc"]).sort_values("captured_at_utc")
latest_quotes = lines.drop_duplicates("game_key", keep="last").set_index("game_key")
if len(latest_quotes) != 15:
    st.error("Week 9 Bovada archive does not contain 15 unique matchups.")
    st.stop()

frozen_time = pd.to_datetime(predictions["captured_at_utc"], errors="coerce", utc=True)
if frozen_time.isna().any() or frozen_time.nunique() != 1:
    st.error("Model snapshot does not have one unambiguous calculation timestamp.")
    st.stop()
stamp = frozen_time.iloc[0].tz_convert("America/Chicago").strftime("%b %d, %Y %I:%M %p CT")
quote_stamp = lines["captured_at_utc"].max().tz_convert("America/Chicago").strftime("%b %d, %Y %I:%M %p CT")
st.caption(
    f"Model snapshot frozen: {stamp}. Latest **archive ingestion**: {quote_stamp}. "
    "Bovada screenshots were provided Wednesday, November 4; their exact screenshot "
    "capture times were not supplied. When new screenshots are archived, market lines "
    "change without rewriting the frozen projections."
)

rows = []
market_keys = set()
for game_id, group in predictions.groupby("game_id", sort=False):
    variants = group.set_index("model")
    baseline = variants.loc["baseline"]
    injury = variants.loc["injury"]
    away, home = team(baseline["away_team"]), team(baseline["home_team"])
    game_key = f"{away}@{home}"
    if game_key not in latest_quotes.index:
        st.error(f"No matching archived Bovada line for {game_key}.")
        st.stop()
    market_keys.add(game_key)
    market = latest_quotes.loc[game_key]
    home_favored = pd.to_numeric(pd.Series([market["home_favorite_spread"]]), errors="coerce").iloc[0]
    total_market = pd.to_numeric(pd.Series([market["total_line"]]), errors="coerce").iloc[0]
    if pd.isna(home_favored) or pd.isna(total_market):
        st.error(f"Missing Bovada spread/total for {game_key}.")
        st.stop()
    favored = home if home_favored >= 0 else away
    coverage_home = float(injury["home_injury_report_available"]) == 1.0
    coverage_away = float(injury["away_injury_report_available"]) == 1.0
    coverage = "Both teams" if coverage_home and coverage_away else "Incomplete — provisional"
    rows.append({
        "_date": pd.to_datetime(baseline["gameday"], errors="coerce"),
        "Game": f"{away} @ {home}",
        "Bovada": f"{favored} -{num(abs(home_favored))} · O/U {num(total_market)}",
        "Baseline score": score(away, home, baseline),
        "Baseline ATS": ats_lean(away, home, baseline, home_favored),
        "Baseline total": total_lean(baseline, total_market),
        "Injury score": score(away, home, injury),
        "Injury ATS": ats_lean(away, home, injury, home_favored),
        "Injury total": total_lean(injury, total_market),
        "Injury reports": coverage,
    })
if market_keys != set(latest_quotes.index):
    st.error("Bovada market archive and game schedule do not match.")
    st.stop()

display = pd.DataFrame(rows).sort_values(["_date", "Game"]).drop(columns="_date")
st.subheader("Baseline and Injury — frozen pregame comparison")
st.dataframe(display, hide_index=True, width="stretch")
st.caption(
    "Score columns are model estimates, away team first. ATS leans and Over/Under "
    "directions are computed using the latest archived Bovada quotes. "
    "Missing injury reports make the Injury projection provisional; zero report rows "
    "must not be interpreted as zero injured players."
)

st.warning(
    "**TNF quarterback limitation — JAX @ BAL:** Joe Fagnano is starting for Baltimore. "
    "The original Injury model uses position-level injury status counts and does not estimate "
    "his individual replacement value. Saved report game-status fields for Lamar Jackson and "
    "Tyler Huntley were blank, despite both being unavailable. Therefore the default Injury "
    "score is **not** a validated Fagnano-adjusted forecast."
)

with st.expander("TNF quarterback-absence sensitivity (experimental — not official)"):
    scenario = pd.read_csv(SNAPSHOT)
    scenario = scenario[
        scenario["game_id"].eq("2026_09_JAX_BAL")
        & scenario["model"].str.endswith("_qbcount_scenario", na=False)
    ].copy()
    st.caption(
        "Changes only the QB-out count features to represent Jackson and Huntley. "
        "Not a calibrated player-level downgrade and not suitable for official model grading."
    )
    if not scenario.empty:
        scenario["Score"] = (
            "JAX " + scenario["projected_away"].round(1).astype(str)
            + " — BAL " + scenario["projected_home"].round(1).astype(str)
        )
        st.dataframe(
            scenario[["model", "Score", "projected_total"]].rename(
                columns={"model": "Research scenario", "projected_total": "Total"}
            ),
            hide_index=True, width="stretch",
        )

with st.expander("Other model variants (advanced research)"):
    research = predictions[
        predictions["model"].isin(("efficiency", "combined", "baseline_hl1", "injury_hl4"))
    ].copy()
    research["Game"] = research["away_team"].map(team) + " @ " + research["home_team"].map(team)
    research["Score"] = (
        research["away_team"].map(team) + " "
        + research["projected_away"].round(1).astype(str)
        + " — " + research["home_team"].map(team) + " "
        + research["projected_home"].round(1).astype(str)
    )
    st.dataframe(
        research[["Game", "model", "Score", "projected_total"]].rename(
            columns={"model": "Variant", "projected_total": "Projected total"}
        ).sort_values(["Game", "Variant"]),
        hide_index=True, width="stretch",
    )
    st.caption(
        "Efficiency and Combined are historical four-model candidates. "
        "Baseline HL1 and Injury HL4 are recency-weighted shadow candidates. "
        "None should be confused with production-promoted replacements."
    )

with st.expander("Archived Bovada prices and source details"):
    book = latest_quotes.reset_index().copy()
    for col in ("home_favorite_spread", "total_line", "away_spread_price",
                "home_spread_price", "over_price", "under_price"):
        book[col] = pd.to_numeric(book[col], errors="coerce")
    st.dataframe(
        book[["game_key", "home_favorite_spread", "total_line",
              "away_spread_price", "home_spread_price", "over_price", "under_price",
              "captured_at_utc"]].rename(columns={
            "game_key": "Game", "home_favorite_spread": "Home favored spread",
            "total_line": "Total", "away_spread_price": "Away ATS price",
            "home_spread_price": "Home ATS price",
            "over_price": "Over price", "under_price": "Under price",
            "captured_at_utc": "Archived at UTC"
        }),
        hide_index=True, width="stretch",
    )
    st.caption(
        "Signed home-favored spread is positive when the home team is favored, "
        "negative when the away team is favored. This is an internal data convention."
    )

st.markdown(f"[View the frozen research CSV]({ARCHIVE_URL})")
st.caption(
    "Historical ATS/Totals records, official prospective tracking and live odds are "
    "separate. This page does not change those records or retrain models."
)
