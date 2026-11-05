import streamlit as st

st.set_page_config(
    page_title="Sports Model | NFL",
    page_icon="🏈",
    layout="wide",
)

# One front-door board that displays committed model predictions and
# user-supplied Bovada prices. Legacy recalculation tools remain accessible
# below but are not the authoritative 24-feature Baseline comparison.
week09_page = st.Page(
    "pages/Week_09_Projection_Board.py",
    title="Week 9 Projections",
    url_path="week-9-projections",
    icon="🏈",
    default=True,
)
week08_public = st.Page(
    "pages/Public_Projection_Board.py",
    title="Week 8 Published Snapshot",
    url_path="week-8-public-projections",
    icon="🌐",
)
week08_comparison = st.Page(
    "pages/Four_Model_Week8_Comparison.py",
    title="Week 8 Results (Four Models)",
    url_path="week-8-four-model-comparison",
    icon="📊",
)
bovada_monitor = st.Page(
    "pages/Bovada_Projection_Monitor.py",
    title="Legacy Live Bovada Monitor",
    icon="🎯",
)
legacy_scoring_board = st.Page(
    "pages/Projection_Board.py",
    title="Legacy Scoring / Schedule Board",
    icon="🏈",
)
totals_backtest = st.Page("research/totals_backtest.py", title="Totals Backtest", icon="📊")
ats_backtest = st.Page("research/ats_backtest.py", title="ATS Backtest", icon="🏈")
schedule_audit = st.Page("research/schedule_audit.py", title="Schedule Data Audit", icon="🧾")
connection_audit = st.Page("research/connection_diagnostics.py", title="Data Connection Diagnostics", icon="🔌")
endzone_sample = st.Page("pages/Endzone_Injury_Sample_Test.py", title="EndzoneAPI Injury Sample Test", icon="🩹")
injury_audit = st.Page("research/injury_snapshot_audit.py", title="Injury Snapshot Audit", icon="🕒")
prospective_tracker = st.Page("research/prospective_ats_tracker.py", title="Prospective ATS Tracker", icon="📈")
prospective_results = st.Page("research/prospective_results_audit.py", title="Prospective Results Audit", icon="✅")

navigation = st.navigation({
    "Current Week": [week09_page],
    "Week 8 Archive": [week08_public, week08_comparison],
    "Research & Diagnostics (Advanced)": [
        bovada_monitor, legacy_scoring_board,
        prospective_tracker, prospective_results,
        ats_backtest, totals_backtest, schedule_audit,
        connection_audit, injury_audit, endzone_sample,
    ],
})
# Visible, lightweight deployment marker for diagnosing stale Cloud instances.
# This identifies the UI release, not a model version or changed projection.
st.sidebar.caption("UI build: 2026-11-05 · Week 9 board + legacy fixes")
navigation.run()
