import streamlit as st

st.set_page_config(
    page_title="Sports Model | NFL",
    page_icon="🏈",
    layout="wide",
)

projection_page = st.Page(
    "pages/Projection_Board.py",
    title="Projection Board",
    icon="🏈",
    default=True,
)
totals_page = st.Page(
    "research/totals_backtest.py",
    title="Totals Backtest",
    icon="📊",
)
ats_page = st.Page(
    "research/ats_backtest.py",
    title="ATS Backtest",
    icon="🏈",
)
schedule_page = st.Page(
    "research/schedule_audit.py",
    title="Schedule Data Audit",
    icon="🧾",
)
connection_page = st.Page(
    "research/connection_diagnostics.py",
    title="Data Connection Diagnostics",
    icon="🔌",
)
endzone_injury_test_page = st.Page(
    "pages/Endzone_Injury_Sample_Test.py",
    title="EndzoneAPI Injury Sample Test",
    icon="🩹",
)
injury_snapshot_audit_page = st.Page(
    "research/injury_snapshot_audit.py",
    title="Injury Snapshot Audit",
    icon="🕒",
)

navigation = st.navigation(
    {
        "Model": [projection_page],
        "Research & Diagnostics": [
            totals_page,
            ats_page,
            schedule_page,
            connection_page,
            endzone_injury_test_page,
            injury_snapshot_audit_page,
        ],
    }
)
navigation.run()
