"""Market overview: indices, trends, best/worst performers and trading volume."""
import pandas as pd
import streamlit as st

from modules import data_processor as dp, technical_indicators as ti, ui, visualization as viz
from modules.constants import FEATURED, POPULAR
from modules.data_fetcher import quotes_to_frame
from modules.formatting import compact, percent

ui.apply_theme()
service = ui.get_data_service()
user = ui.current_user()
ui.manual_refresh(service)

st.title("Market Overview")
index_map = service.provider.indices
with st.spinner("Loading indices..."):
    index_quotes = service.quotes(list(index_map.values()))
ui.status_bar(service, index_quotes)
if service.provider.index_note:
    st.info(service.provider.index_note)

# ------------------------------------------------------------ indices and trends
st.subheader("Major indices")
up_count = 0
for col, (name, sym) in zip(st.columns(len(index_map)), index_map.items()):
    r = index_quotes[sym]
    with col:
        if r.ok and r.data is not None:
            up_count += (r.data.change or 0) > 0
            st.metric(name, f"{r.data.price:,.2f}", percent(r.data.change_pct) if r.data.change_pct is not None else None)
            hist = service.history(sym, "6mo")
            if hist.ok:
                close = hist.data["Close"]
                st.plotly_chart(viz.sparkline(close), key=f"idx_{sym}")
                trend = []
                month = dp.period_return(close, 21)
                if month is not None:
                    trend.append(f"1-month change: {percent(month * 100)}")
                sma50 = ti.sma(close, 50).dropna()
                if len(sma50):
                    trend.append("trading " + ("above" if close.iloc[-1] > sma50.iloc[-1] else "below") + " its 50-day average")
                st.caption("; ".join(trend).capitalize() if trend else "Not enough history for trend.")
        else:
            st.metric(name, "N/A")
            st.caption(r.message)
st.markdown(f"**Overall performance:** {up_count} of {len(index_map)} indices are up versus the previous close.")

# ------------------------------------------------------------ movers and volume
st.subheader("Watchlist performers")
symbols = list(dict.fromkeys(ui.symbol_options(user)))
results = service.quotes(symbols)
ui.status_bar(service, results)
frame = quotes_to_frame(results)
if frame.empty:
    st.warning("No stock data is available right now.")
else:
    ranked = frame.dropna(subset=["Change %"]).sort_values("Change %", ascending=False)
    c1, c2 = st.columns(2)
    c1.markdown("**Top performers**")
    c1.dataframe(ranked[["Symbol", "Price", "Change %"]].head(5), hide_index=True)
    c2.markdown("**Worst performers**")
    c2.dataframe(ranked[["Symbol", "Price", "Change %"]].tail(5).iloc[::-1], hide_index=True)

    st.subheader("Trading volume")
    vols = frame.set_index("Symbol")["Volume"].dropna()
    if len(vols):
        st.pyplot(viz.volume_bars(vols))
        st.caption("Volume of the latest trading day available (it may be partial while the market is open).")
    st.dataframe(frame.assign(Volume=frame["Volume"].map(compact), **{"Market cap": frame["Market cap"].map(lambda v: compact(v, "$"))}), hide_index=True)
