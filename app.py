import streamlit as st

st.set_page_config(
    page_title="Sports Model | NFL",
    page_icon="🏈",
    layout="wide",
)

bovada_monitor_page = st.Page(
    "pages/Bovada_Projection_Monitor.py",
    title="Bovada Projection Monitor",
    icon="🎯",
    default=True,
)
projection_page = st.Page(
    "pages/Projection_Board.py",
    title="Projection Board (Schedule Feed)",
    icon="🏈",
)
public_projection_page = st.Page(
    "pages/Public_Projection_Board.py",
    title="Week 8 Public Projections",
    icon="🌐",
)
totals_page = st.Page("research/totals_backtest.py", title="Totals Backtest", icon="📊")
ats_page = st.Page("research/ats_backtest.py", title="ATS Backtest", icon="🏈")
schedule_page = st.Page("research/schedule_audit.py", title="Schedule Data Audit", icon="🧾")
connection_page = st.Page("research/connection_diagnostics.py", title="Data Connection Diagnostics", icon="🔌")
endzone_injury_test_page = st.Page("pages/Endzone_Injury_Sample_Test.py", title="EndzoneAPI Injury Sample Test", icon="🩹")
injury_snapshot_audit_page = st.Page("research/injury_snapshot_audit.py", title="Injury Snapshot Audit", icon="🕒")
prospective_ats_page = st.Page("research/prospective_ats_tracker.py", title="Prospective ATS Tracker", icon="📈")
results_audit_page = st.Page("research/prospective_results_audit.py", title="Prospective Results Audit", icon="✅")

navigation = st.navigation({
    "Model": [bovada_monitor_page, projection_page, public_projection_page],
    "Research & Diagnostics": [
        totals_page, ats_page, prospective_ats_page, results_audit_page,
        schedule_page, connection_page, endzone_injury_test_page, injury_snapshot_audit_page,
    ],
})
navigation.run()
