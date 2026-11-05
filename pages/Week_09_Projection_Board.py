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
QB_INJURY = ROOT / "data" / "public_snapshots" / "nfl_week09_injury_qb_epa_margin_2026-11-05.csv"
QB_INJURY_ARCHIVE = "https://github.com/tedgytrends-bit/sports-betting-model/blob/main/data/public_snapshots/nfl_week09_injury_qb_epa_margin_2026-11-05.csv"
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
    "**Baseline** is the unchanged evaluated 24-feature model. **Injury** is "
    "our single QB-aware version: it fits non-QB injuries, measures each expected "
    "starter's prior EPA relative to the recent team QB mix, and applies a "
    "conservative margin adjustment without changing the modeled total. "
    "The previously published Injury snapshot remains archived. "
    "Unverified starting QBs and missing injury reports are provisional."
)

if not SNAPSHOT.exists() or not BOVADA.exists() or not QB_INJURY.exists():
    st.error("The frozen Week 9 projections or saved Bovada archive are missing.")
    st.stop()

predictions = pd.read_csv(SNAPSHOT, low_memory=False)
injury_v2 = pd.read_csv(QB_INJURY, low_memory=False)
lines = pd.read_csv(BOVADA, low_memory=False)
required_v2 = {
    "game_id", "season", "week", "model", "model_version",
    "projected_away", "projected_home", "projected_total",
    "published_at_utc", "home_injury_report_available",
    "away_injury_report_available", "home_qb_name", "away_qb_name",
    "home_qb_starter_source", "away_qb_starter_source",
}
if not required_v2.issubset(injury_v2.columns):
    st.error("QB-aware Injury snapshot lacks required fields; refusing to silently use old scores.")
    st.stop()
injury_v2 = injury_v2[
    pd.to_numeric(injury_v2["season"], errors="coerce").eq(2026)
    & pd.to_numeric(injury_v2["week"], errors="coerce").eq(9)
].copy()
if len(injury_v2) != 15 or injury_v2["game_id"].nunique() != 15 or not injury_v2["model"].eq("injury").all():
    st.error("Incomplete or duplicate QB-aware Injury snapshot. Expected 15 games.")
    st.stop()
injury_v2 = injury_v2.set_index("game_id")

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
    injury_original = variants.loc["injury"]
    if game_id not in injury_v2.index:
        st.error(f"Missing new Injury snapshot for {game_id}.")
        st.stop()
    injury = injury_v2.loc[game_id]
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
st.subheader("Baseline and QB-aware Injury — pregame comparison")
st.dataframe(display, hide_index=True, width="stretch")
st.caption(
    "Baseline was frozen Nov 4. QB-aware Injury v1 was published Nov 5 before kickoff, "
    "with a five-point-per-team cap and margin-only QB adjustment. "
    "ATS/total leans use the most recent archived Bovada market quotes. "
    "A provisional starter or missing injury report is not the same as a confirmed player status."
)

st.warning(
    "**QB EPA availability caveat:** Joe Fagnano is verified as Baltimore's Week 9 starter, "
    "but his prior EPA comes from a small sample. Other projected starters are sourced from "
    "the upcoming schedule unless separately verified. The QB-aware Injury forecast uses "
    "a conservative prior and capped margin adjustment, not a validated precise player-point value. "
    "The original Nov 4 Injury prediction is retained in its historical source file."
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

st.markdown(f"[Original frozen research snapshot]({ARCHIVE_URL}) · "
            f"[New QB-aware Injury snapshot]({QB_INJURY_ARCHIVE})")
st.caption(
    "The other four experimental variants remain archived for private research "
    "but are not presented as competing public projections. "
    "Week 9 scores are pregame research projections, not betting advice."
)


# One Injury model, one QB source: use the SAME frozen published QB-aware
# Injury rows as the main board, never a different experimental snapshot.
with st.expander("Starting QB EPA — inputs to the published Injury model"):
    verified = injury_v2.reset_index().copy()
    qb_cols = [
        "game_id", "away_team", "home_team", "away_qb_name", "home_qb_name",
        "away_qb_starter_source", "home_qb_starter_source",
        "away_qb_prior_dropbacks", "home_qb_prior_dropbacks",
        "away_qb_epa_delta", "home_qb_epa_delta",
        "away_qb_shift_capped", "home_qb_shift_capped",
    ]
    if not set(qb_cols).issubset(verified.columns):
        st.error("Published Injury QB metadata is incomplete.")
    else:
        pieces = []
        for side in ("away", "home"):
            q = verified[[
                "game_id", f"{side}_team", f"{side}_qb_name",
                f"{side}_qb_starter_source", f"{side}_qb_prior_dropbacks",
                f"{side}_qb_epa_delta", f"{side}_qb_shift_capped",
            ]].rename(columns={
                f"{side}_team": "Team",
                f"{side}_qb_name": "Expected QB",
                f"{side}_qb_starter_source": "Starter evidence",
                f"{side}_qb_prior_dropbacks": "Career sample (prior dropbacks)",
                f"{side}_qb_epa_delta": "Incremental EPA/dropback",
                f"{side}_qb_shift_capped": "Estimated QB effect (points)",
                "game_id": "Game",
            })
            pieces.append(q)
        detail = pd.concat(pieces, ignore_index=True)
        detail["Starter evidence"] = detail["Starter evidence"].map({
            "verified_pregame": "Verified before kickoff",
            "schedule_provisional_qb_unverified": "Provisional schedule listing",
        }).fillna("Unverified")
        for name in ("Incremental EPA/dropback", "Estimated QB effect (points)"):
            detail[name] = pd.to_numeric(detail[name], errors="coerce").round(3)
        st.dataframe(detail.sort_values(["Game", "Team"]), hide_index=True, width="stretch")
        st.caption(
            "These are the QB inputs used by the single published Injury v1. "
            "The published score adjusts the margin while keeping the non-QB "
            "total projection fixed. Only source-confirmed starters are verified. "
            "QB effects use a conservative sample-size adjustment and a maximum "
            "five-point per-team impact. The 2026 retrospective test used "
            "postgame starter identities; its improvement is not prospective proof."
        )
