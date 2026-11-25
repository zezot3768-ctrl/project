"""MarketLens: Stock Market Analysis web app. Start it with:  streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="MarketLens · Stock Market Analysis", page_icon="📈", layout="wide")

from modules import ui  # noqa: E402  (after set_page_config, which must be the first Streamlit call)

ui.apply_theme()
try:
    st.logo("assets/logo.svg", size="large")
except Exception:  # older Streamlit versions may not support SVG logos or the size option
    st.sidebar.markdown("## MarketLens")

pages = [
    st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    st.Page("pages/stock_analysis.py", title="Stock Analysis", icon=":material/candlestick_chart:"),
    st.Page("pages/simulator.py", title="Simulator", icon=":material/sports_esports:"),
    st.Page("pages/market_overview.py", title="Market Overview", icon=":material/public:"),
    st.Page("pages/watchlist.py", title="Watchlist", icon=":material/star:"),
    st.Page("pages/about.py", title="About", icon=":material/info:"),
]
try:
    navigation = st.navigation(pages, position="top")   # top navigation bar (Streamlit 1.46+)
except TypeError:
    navigation = st.navigation(pages)                   # older versions: sidebar navigation
navigation.run()
