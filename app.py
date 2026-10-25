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

navigation = st.navigation(
    {
        "Model": [projection_page],
        "Research & Diagnostics": [totals_page, schedule_page, connection_page],
    }
)
navigation.run()
