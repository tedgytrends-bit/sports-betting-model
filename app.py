"""Tedgy Trends public NFL app: one projection page and one results page.

Old research pages remain registered as hidden routes to avoid breaking any
existing links, but they must not appear as alternate public model boards.
"""
import streamlit as st

st.set_page_config(
    page_title="Tedgy Trends | NFL",
    page_icon="🏈",
    layout="wide",
)

week10 = st.Page(
    "pages/Week_10_Projection_Board.py",
    title="Week 10 Projections",
    icon="🏈",
    default=True,
)

week09 = st.Page(
    "pages/Week_09_Projection_Board.py",
    title="Week 9 Archived Projections",
    icon="🏈",
    url_path="week-9-projections",
    visibility="hidden",
)

results = st.Page(
    "pages/Results.py",
    title="Model Results",
    icon="📊",
    url_path="results",
)

# Preserve the previously tweeted URL without cluttering the public menu.
week08_published = st.Page(
    "pages/Public_Projection_Board.py",
    title="Week 8 Published Snapshot",
    icon="🌐",
    url_path="week-8-public-projections",
    visibility="hidden",
)
week08_comparison = st.Page(
    "pages/Four_Model_Week8_Comparison.py",
    title="Week 8 Four-Model Research Comparison",
    icon="📊",
    url_path="week-8-four-model-comparison",
    visibility="hidden",
)

# Legacy research pages remain accessible by their direct routes, not shown
# in the public navigation. Keeping the files permits debugging and research
# while eliminating contradictory projection products from the menu.
legacy = [
    st.Page(
        "pages/Bovada_Projection_Monitor.py",
        title="Legacy Live Bovada Monitor",
        icon="🎯",
        visibility="hidden",
    ),
    st.Page(
        "pages/Projection_Board.py",
        title="Legacy Scoring / Schedule Board",
        icon="🏈",
        visibility="hidden",
    ),
    st.Page("research/prospective_ats_tracker.py", title="Prospective ATS Tracker", visibility="hidden"),
    st.Page("research/prospective_results_audit.py", title="Prospective Results Audit", visibility="hidden"),
    st.Page("research/ats_backtest.py", title="ATS Backtest", visibility="hidden"),
    st.Page("research/totals_backtest.py", title="Totals Backtest", visibility="hidden"),
    st.Page("research/schedule_audit.py", title="Schedule Data Audit", visibility="hidden"),
    st.Page("research/connection_diagnostics.py", title="Data Connection Diagnostics", visibility="hidden"),
    st.Page("research/injury_snapshot_audit.py", title="Injury Snapshot Audit", visibility="hidden"),
    st.Page("pages/Endzone_Injury_Sample_Test.py", title="EndzoneAPI Injury Sample Test", visibility="hidden"),
]

nav = st.navigation([week10, results, week09, week08_published, week08_comparison, *legacy])
st.sidebar.caption("Tedgy Trends · Public UI v2026.11.12-week10")
nav.run()
