"""Stock analysis: charts, technical indicators, statistics and company financials."""
import streamlit as st

from modules import data_processor as dp, technical_indicators as ti, ui, visualization as viz
from modules.constants import COMPANY_NAMES, PERIOD_OPTIONS, VIEW_OPTIONS
from modules.data_fetcher import normalize_symbol
from modules.errors import DataError
from modules.formatting import compact, money, percent

ui.apply_theme()
service = ui.get_data_service()
user = ui.current_user()
ui.manual_refresh(service)

st.title("Stock Analysis")

# ---------------------------------------------------------------- choose stock and view
options = ui.symbol_options(user)
selected = st.session_state.get("selected_symbol", "AAPL")
if selected not in options:
    options.insert(0, selected)
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
symbol = c1.selectbox("Stock", options, index=options.index(selected),
                      format_func=lambda s: f"{s} · {COMPANY_NAMES[s]}" if s in COMPANY_NAMES else s)
custom = c1.text_input("Or type another ticker (for example AMD)")
if custom.strip():
    try:
        symbol = normalize_symbol(custom)
    except DataError as exc:
        c1.error(str(exc))
st.session_state["selected_symbol"] = symbol
period = c2.selectbox("Period", PERIOD_OPTIONS, index=3)
view = c3.selectbox("View", list(VIEW_OPTIONS))
kind = c4.radio("Chart type", ["Candlestick", "Line"])
with st.expander("Indicator settings"):
    sma_windows = st.multiselect("SMA windows", [10, 20, 50, 100, 200], default=[20, 50])
    ema_windows = st.multiselect("EMA windows", [9, 12, 21, 26, 50], default=[])
    show_volume = st.checkbox("Show volume panel", value=True)

# ---------------------------------------------------------------- load data
with st.spinner(f"Loading {symbol} price history..."):
    history = service.history(symbol, period)
    quote = service.quote(symbol)
if not history.ok:
    st.error(f"Could not load data for {symbol}: {history.message}")
    st.stop()
if history.stale:
    st.warning(history.message)

daily = history.data                              # cleaned daily OHLCV
shown = dp.resample_ohlcv(daily, VIEW_OPTIONS[view])  # weekly / monthly / yearly if chosen
is_daily = view == "Daily"

left, right = st.columns([1, 2])
left.markdown(ui.stock_card_html(symbol, quote), unsafe_allow_html=True)
right.markdown(
    f"{ui.badge(ui.DataCategory.HISTORICAL)}<br><br>Historical daily prices from **{daily.index[0]:%Y-%m-%d}** to "
    f"**{daily.index[-1]:%Y-%m-%d}** · source: {service.provider.label}. "
    f"The chart shows {len(shown)} {view.lower()} bars.", unsafe_allow_html=True)

tab_chart, tab_ind, tab_stats, tab_fin, tab_help = st.tabs(["Chart", "Indicators", "Statistics", "Financials", "How it works"])

# ---------------------------------------------------------------- chart tab
with tab_chart:
    usable_sma = [w for w in sma_windows if w <= len(shown)]
    usable_ema = [w for w in ema_windows if w <= len(shown)]
    skipped = [w for w in sma_windows + ema_windows if w > len(shown)]
    if skipped:
        st.info(f"Not enough data to draw averages with window(s) {sorted(set(skipped))}. Choose a longer period.")
    fig = viz.price_chart(shown, f"{symbol} · {view} · {period}", kind, usable_sma, usable_ema, show_volume, is_daily)
    st.plotly_chart(fig, key="price_chart")
    with st.expander("Show OHLCV data (Open, High, Low, Close, Volume)"):
        st.dataframe(shown.tail(60).iloc[::-1])

# ---------------------------------------------------------------- indicators tab
with tab_ind:
    close = shown["Close"]
    if len(shown) < 35:
        st.info("Choose a longer period or a finer view: RSI and MACD need at least about 35 bars.")
    else:
        rsi_series = ti.rsi(close)
        macd_df = ti.macd(close)
        st.plotly_chart(viz.rsi_chart(rsi_series, is_daily), key="rsi_chart")
        last_rsi = rsi_series.dropna().iloc[-1]
        zone = "above 70 (often called 'overbought')" if last_rsi > 70 else "below 30 (often called 'oversold')" if last_rsi < 30 else "between 30 and 70 (neutral zone)"
        st.caption(f"Latest RSI: {last_rsi:.1f}, {zone}. This is a descriptive rule of thumb, not a prediction or advice.")
        st.plotly_chart(viz.macd_chart(macd_df, is_daily), key="macd_chart")
        relation = "above" if macd_df["MACD"].iloc[-1] > macd_df["Signal"].iloc[-1] else "below"
        st.caption(f"The MACD line is currently {relation} its signal line.")
    vol = ti.volume_analysis(shown)
    st.plotly_chart(viz.volume_chart(vol, is_daily), key="volume_chart")
    rel = vol["Relative volume"].dropna()
    if len(rel):
        st.caption(f"Latest volume is {rel.iloc[-1]:.2f}x its 20-bar average.")

# ---------------------------------------------------------------- statistics tab
with tab_stats:
    stats = dp.summary_stats(daily)
    returns = dp.daily_returns(daily["Close"])
    a, b, c = st.columns(3)
    a.metric("Total return (period)", percent(stats["total_return"] * 100))
    b.metric("Average daily return", percent(stats["avg_daily_return"] * 100, 3))
    c.metric("Volatility (annualized)", percent(stats["annual_volatility"] * 100, 1, signed=False))
    a, b, c = st.columns(3)
    a.metric("Highest price", money(stats["max_price"]), f"{stats['max_price_date']:%Y-%m-%d}", delta_color="off")
    b.metric("Lowest price", money(stats["min_price"]), f"{stats['min_price_date']:%Y-%m-%d}", delta_color="off")
    c.metric("Maximum drawdown", percent(stats["max_drawdown"] * 100, 1))
    a, b, c = st.columns(3)
    a.metric("Best day", percent(stats["best_day"] * 100))
    b.metric("Worst day", percent(stats["worst_day"] * 100))
    c.metric("Trading days", f"{stats['trading_days']}")
    st.pyplot(viz.returns_histogram(returns, f"{symbol}: distribution of daily returns"))
    st.markdown("**Historical performance** (calculated from the data above)")
    perf = {label: dp.period_return(daily["Close"], days) for label, days in (("1 month", 21), ("3 months", 63), ("6 months", 126), ("1 year", 252))}
    cols = st.columns(len(perf))
    for col, (label, value) in zip(cols, perf.items()):
        col.metric(label, "N/A" if value is None else percent(value * 100))
    st.caption("N/A means the selected period does not contain enough data. Past performance does not guarantee future results.")

# ---------------------------------------------------------------- financials tab
with tab_fin:
    fund = service.fundamentals(symbol)
    if not fund.ok:
        st.warning(f"Company financials are not available right now: {fund.message}")
    else:
        if fund.stale:
            st.warning(fund.message)
        f = fund.data
        price = quote.data.price if quote.ok and quote.data else None
        rate = f.get("dividend_rate")
        yield_pct = rate / price * 100 if rate and price else None
        a, b, c = st.columns(3)
        a.metric("Market capitalization", compact(f.get("market_cap"), "$"))
        b.metric("Price-to-earnings (P/E)", "N/A" if f.get("pe_ratio") is None else f"{f['pe_ratio']:.1f}")
        c.metric("Earnings per share (EPS)", money(f.get("eps")))
        a, b, c = st.columns(3)
        a.metric("Revenue (trailing 12 months)", compact(f.get("revenue"), "$"))
        b.metric("Net income", compact(f.get("net_income"), "$"))
        c.metric("Dividend per share (yearly)", money(rate) if rate else "None / N/A", percent(yield_pct, 2, signed=False) + " yield" if yield_pct else None, delta_color="off")
        st.caption(f"Source: {service.provider.label}. 'N/A' means the provider does not supply that figure for this stock.")

# ---------------------------------------------------------------- explanations tab
with tab_help:
    for name, text in ti.INDICATOR_HELP.items():
        with st.expander(name):
            st.write(text)
