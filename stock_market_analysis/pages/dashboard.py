"""Dashboard: live (or latest available) quotes for Apple, NVIDIA and other popular stocks."""
import streamlit as st

from modules import data_processor as dp, ui, visualization as viz
from modules.constants import FEATURED, POPULAR
from modules.data_fetcher import quotes_to_frame
from modules.formatting import percent

ui.apply_theme()
service = ui.get_data_service()
user = ui.current_user()
auto, seconds = ui.refresh_controls(service)

st.title("Market Dashboard")
st.markdown(f"Welcome back, **{user}**. Prices below come from a real data provider and are labelled by data type.")


def live_section():
    """Everything that should refresh automatically lives in this function (a Streamlit fragment)."""
    ttl = max(5, seconds - 5) if auto else None  # make sure each refresh really downloads new data
    with st.spinner("Loading market data..."):
        results = service.quotes(FEATURED + POPULAR, ttl=ttl)
        index_results = service.quotes(list(service.provider.indices.values()), ttl=ttl)

    ui.status_bar(service, {**results, **index_results})
    st.markdown(f"**Market status:** {ui.market_banner(results)}")

    # ---- market overview numbers
    st.subheader("Market overview")
    cols = st.columns(len(service.provider.indices))
    for col, (name, sym) in zip(cols, service.provider.indices.items()):
        r = index_results[sym]
        if r.ok and r.data is not None:
            delta = percent(r.data.change_pct) if r.data.change_pct is not None else None
            col.metric(name, f"{r.data.price:,.2f}", delta)
        else:
            col.metric(name, "N/A")
    if service.provider.index_note:
        st.caption(service.provider.index_note)

    # ---- featured stocks (Apple and NVIDIA) with one-month sparklines
    st.subheader("Featured stocks")
    for col, sym in zip(st.columns(len(FEATURED)), FEATURED):
        with col:
            st.markdown(ui.stock_card_html(sym, results[sym]), unsafe_allow_html=True)
            hist = service.history(sym, "1mo")
            if hist.ok:
                st.plotly_chart(viz.sparkline(hist.data["Close"]), key=f"spark_{sym}")
                st.caption("Last month of closing prices (historical data)")

    # ---- other popular stocks
    st.subheader("Popular stocks")
    for col, sym in zip(st.columns(len(POPULAR)), POPULAR):
        col.markdown(ui.stock_card_html(sym, results[sym], small=True), unsafe_allow_html=True)

    # ---- best and worst performers today
    frame = quotes_to_frame(results).dropna(subset=["Change %"])
    if len(frame) >= 2:
        st.subheader("Today's movers")
        ranked = frame.sort_values("Change %", ascending=False)[["Symbol", "Price", "Change %"]]
        c1, c2 = st.columns(2)
        c1.markdown("**Top performers**")
        c1.dataframe(ranked.head(3), hide_index=True)
        c2.markdown("**Weakest performers**")
        c2.dataframe(ranked.tail(3).iloc[::-1], hide_index=True)


# run_every makes Streamlit re-run only this fragment on a timer (or never, if auto-refresh is off)
st.fragment(run_every=seconds if auto else None)(live_section)()

st.subheader("Open a detailed analysis")
for col, sym in zip(st.columns(len(FEATURED + POPULAR)), FEATURED + POPULAR):
    if col.button(f"{sym}", key=f"analyze_{sym}"):
        ui.go_to_analysis(sym)

st.subheader("Performance comparison")
period = st.radio("Period", ["1mo", "3mo", "6mo", "1y"], index=2, horizontal=True)
chosen = st.multiselect("Stocks", FEATURED + POPULAR, default=FEATURED)
series = {}
for sym in chosen:
    res = service.history(sym, period)
    if res.ok:
        series[sym] = dp.normalize(res.data["Close"])
    else:
        st.warning(f"{sym}: {res.message}")
if series:
    st.plotly_chart(viz.comparison_chart(series), key="compare")
    st.caption("Historical closing prices, rescaled so every stock starts at 100. Past performance does not guarantee future results.")
