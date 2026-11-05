"""Public graded model records, beginning with the published Week 8 slate.

Only the two public model families are displayed. Experimental model variants
and older retrospectively reconstructed weeks are deliberately excluded from
the public tracked results.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
WEEK_8 = ROOT / "data" / "four_model_week08" / "week08_four_model_comparison.csv"

st.title("Tedgy Trends — Model Results")
st.caption("2026 NFL ATS and totals · Public tracking starts Week 8")
st.info(
    "Only games from Week 8 onward belong to this public record. "
    "Earlier-season reconstruction and historical backtests are research, "
    "not part of the published tracking record."
)

if not WEEK_8.exists():
    st.error("The Week 8 results dataset could not be located.")
    st.stop()

df = pd.read_csv(WEEK_8)
if len(df) != 14 or df["game_id"].nunique() != 14:
    st.error("Incomplete Week 8 results file; refusing to display partial records.")
    st.stop()
required = {
    "date", "away_team", "home_team", "actual_away_score", "actual_home_score",
    "market_favorite", "market_spread_points", "market_total",
    "baseline_ats_pick", "baseline_ats_result", "baseline_total_pick",
    "baseline_total_result", "baseline_projected_total",
    "injury_ats_pick", "injury_ats_result", "injury_total_pick",
    "injury_total_result", "injury_projected_total"
}
if not required.issubset(df.columns):
    st.error("Week 8 results file is missing required model or grading columns.")
    st.stop()

def record(values: pd.Series) -> tuple[str, str]:
    v = values.fillna("").astype(str).str.strip().str.lower()
    wins = int(v.eq("win").sum())
    losses = int(v.eq("loss").sum())
    pushes = int(v.eq("push").sum())
    missing = int(len(v) - wins - losses - pushes)
    rec = f"{wins}–{losses}" + (f"–{pushes}" if pushes else "")
    extra = (
        f"{wins / (wins + losses):.1%} of decisive games"
        if wins + losses else "No decisive games"
    )
    if missing:
        extra += f" · {missing} ungraded"
    return rec, extra

st.subheader("Week 8 · Nov 1, 2026")
left, right = st.columns(2)
for container, model, label in ((left, "baseline", "Baseline"), (right, "injury", "Injury")):
    with container:
        st.markdown(f"**{label}**")
        ats, ats_desc = record(df[f"{model}_ats_result"])
        total, total_desc = record(df[f"{model}_total_result"])
        st.metric("ATS", ats)
        st.caption(ats_desc)
        st.metric("Totals", total)
        st.caption(total_desc)

rows = []
for _, r in df.sort_values(["date", "away_team"]).iterrows():
    away = str(r["away_team"])
    home = str(r["home_team"])
    score = (
        f"{away} {int(r['actual_away_score'])} – "
        f"{home} {int(r['actual_home_score'])}"
        if pd.notna(r["actual_away_score"]) and pd.notna(r["actual_home_score"])
        else "Pending"
    )
    market = (
        f"{r['market_favorite']} -{float(r['market_spread_points']):g} "
        f"· O/U {float(r['market_total']):g}"
    )
    out = {
        "Game": f"{away} @ {home}",
        "Final": score,
        "Bovada": market,
    }
    for model, label in (("baseline", "Baseline"), ("injury", "Injury")):
        ats_status = str(r.get(f"{model}_ats_result", ""))
        total_status = str(r.get(f"{model}_total_result", ""))
        ats_status = ats_status if pd.notna(r.get(f"{model}_ats_result")) else "Ungraded"
        total_status = total_status if pd.notna(r.get(f"{model}_total_result")) else "Ungraded"
        out[f"{label} ATS"] = f"{r[f'{model}_ats_pick']} ({ats_status})"
        out[f"{label} total"] = (
            f"{r[f'{model}_total_pick']} "
            f"{float(r[f'{model}_projected_total']):.1f} ({total_status})"
        )
    rows.append(out)

st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption(
    "Results are graded against the archived, user-provided Bovada lines for "
    "the Week 8 comparison. A blank/ungraded model result is not a loss or win. "
    "Historical and experimental performance are not combined into this public record."
)
st.page_link("pages/Public_Projection_Board.py", label="View original Week 8 published projections", icon=":material/history:")
st.caption("Experimental model research · Not betting advice")
