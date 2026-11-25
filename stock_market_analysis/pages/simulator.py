"""Simulator: virtual trading, portfolio dashboard, transaction history, historical replay, hypothetical market."""
import pandas as pd
import streamlit as st

from modules import data_processor as dp, database as db, ui, visualization as viz
from modules.constants import COMPANY_NAMES, START_CASH
from modules.data_fetcher import DataCategory
from modules.formatting import money, percent, signed_money
from modules.portfolio import ReplaySession, compute_holdings, portfolio_summary

ui.apply_theme()
service = ui.get_data_service()
user = ui.current_user()
ui.manual_refresh(service)
options = ui.symbol_options(user)


def label(sym):
    return f"{sym} · {COMPANY_NAMES[sym]}" if sym in COMPANY_NAMES else sym


st.title("Stock Market Simulator")
ui.sim_banner()
tab_trade, tab_port, tab_hist, tab_replay, tab_hypo = st.tabs(
    ["Virtual trading", "Portfolio", "Transactions", "Market replay", "Hypothetical market"])

# =============================================================== 1. virtual trading
with tab_trade:
    if "trade_msg" in st.session_state:  # result of the previous click (we rerun after each trade)
        ok, msg = st.session_state.pop("trade_msg")
        (st.success if ok else st.error)(msg)

    state = db.get_state(user)
    holdings = compute_holdings(state["transactions"])
    left, right = st.columns([1, 1])
    symbol = left.selectbox("Company", options, key="trade_symbol", format_func=label)
    qres = service.quote(symbol)
    left.markdown(ui.stock_card_html(symbol, qres), unsafe_allow_html=True)
    owned = holdings[symbol].shares if symbol in holdings else 0
    right.metric("Available virtual cash", money(state["cash"]))
    right.metric(f"{symbol} shares you own", owned)

    can_trade = False
    if not qres.ok or qres.data is None:
        st.error("No market price is available, so trading is paused. The simulator never uses invented prices. "
                 f"Reason: {qres.message}")
    else:
        q = qres.data
        needs_confirmation = qres.stale or q.category == DataCategory.HISTORICAL
        if needs_confirmation:
            st.warning("Live data is not available for this stock right now (the market may be closed, or a refresh failed). "
                       f"The reference price is the latest available close of {money(q.price)}, dated {q.as_of:%Y-%m-%d}, "
                       "and it is HISTORICAL, not live.")
            can_trade = st.checkbox("I understand this trade will use that price", key="confirm_price")
        else:
            can_trade = True
            st.info(f"Reference price: {money(q.price)} ({q.category.value.lower()} data). Simulated trades are not real exchange transactions.")

    shares = st.number_input("Number of shares", min_value=1, value=1, step=1, key="trade_shares")
    if qres.ok and qres.data is not None:
        st.write(f"Estimated total: **{money(shares * qres.data.price)}**")

    buy_col, sell_col, _ = st.columns([1, 1, 3])
    for side, col in (("BUY", buy_col), ("SELL", sell_col)):
        if col.button(f"{side.title()} (simulated)", disabled=not can_trade, key=f"btn_{side}"):
            fresh = service.quote(symbol, ttl=30)  # use the latest retrieved price at the moment of the click
            if not fresh.ok or fresh.data is None:
                st.session_state["trade_msg"] = (False, "Trade cancelled: no price available.")
            else:
                category = fresh.data.category.value + (" (stale)" if fresh.stale else "")
                result = db.execute_trade(user, symbol, side, int(shares), fresh.data.price, category)
                st.session_state["trade_msg"] = (result.ok, result.message)
            st.rerun()

# =============================================================== 2. portfolio dashboard
with tab_port:
    state = db.get_state(user)
    holdings = compute_holdings(state["transactions"])
    prices = {}
    if holdings:
        for sym, res in service.quotes(list(holdings)).items():
            if res.ok and res.data is not None:
                prices[sym] = res.data.price
    summary = portfolio_summary(state["cash"], holdings, prices, state["realized_pl"])
    if summary["missing_prices"]:
        st.warning(f"No current price for {', '.join(summary['missing_prices'])}. Their purchase price is used for now.")

    a, b, c, d = st.columns(4)
    a.metric("Available cash", money(summary["cash"]))
    b.metric("Total portfolio value", money(summary["total_value"]))
    c.metric("Total invested", money(summary["invested"]))
    d.metric("Total profit / loss", signed_money(summary["total_pl"]), percent(summary["total_pl_pct"]))
    a, b, _, _ = st.columns(4)
    a.metric("Unrealized P/L (open positions)", signed_money(summary["unrealized_pl"]))
    b.metric("Realized P/L (closed sales)", signed_money(summary["realized_pl"]))

    if holdings:
        st.markdown("**Current holdings**")
        st.dataframe(summary["table"], hide_index=True, column_config={
            "Avg price": st.column_config.NumberColumn(format="$%.2f"), "Current price": st.column_config.NumberColumn(format="$%.2f"),
            "Invested": st.column_config.NumberColumn(format="$%.2f"), "Market value": st.column_config.NumberColumn(format="$%.2f"),
            "P/L ($)": st.column_config.NumberColumn(format="$%.2f"), "P/L (%)": st.column_config.NumberColumn(format="%.2f%%")})
        labels = ["Cash"] + list(summary["table"]["Symbol"])
        values = [summary["cash"]] + list(summary["table"]["Market value"])
        st.plotly_chart(viz.donut_chart(labels, values, "Portfolio allocation"), key="alloc")
    else:
        st.info("You do not own any shares yet. Use the 'Virtual trading' tab to make your first simulated purchase.")

    with st.expander("Reset my virtual portfolio"):
        st.write(f"This deletes your transactions and restores {money(START_CASH)} of virtual cash.")
        if st.checkbox("Yes, reset my portfolio", key="confirm_reset") and st.button("Reset now"):
            db.reset_account(user)
            st.rerun()

# =============================================================== 3. transaction history
with tab_hist:
    txs = db.get_state(user)["transactions"]
    if not txs:
        st.info("No transactions yet.")
    else:
        table = pd.DataFrame(txs).rename(columns={
            "executed_at": "Date and time (UTC)", "symbol": "Symbol", "side": "Type", "shares": "Shares",
            "price": "Execution price", "total": "Total value", "data_category": "Price data type", "realized_pl": "Realized P/L"})
        table = table[["Date and time (UTC)", "Symbol", "Type", "Shares", "Execution price", "Total value", "Price data type", "Realized P/L"]].iloc[::-1]
        st.dataframe(table, hide_index=True)
        st.download_button("Download as CSV", table.to_csv(index=False), "transactions.csv", "text/csv")
        st.caption("All entries are simulated trades with virtual money.")

# =============================================================== 4. historical market replay
with tab_replay:
    st.markdown(f"{ui.badge(DataCategory.HISTORICAL)} Replay **real historical prices** one day at a time, make virtual decisions, "
                "and compare your result with simply buying and holding.", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    rp_symbol = c1.selectbox("Stock", options, key="rp_symbol", format_func=label)
    spans = {"3 months": "3mo", "6 months": "6mo", "1 year": "1y", "2 years": "2y"}
    rp_span = c2.selectbox("Historical period", list(spans), index=2, key="rp_span")
    rp_speed = c3.slider("Seconds per day", 0.5, 3.0, 1.0, 0.5, key="rp_speed")
    ss = st.session_state

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Start new session", key="rp_start"):
        res = service.history(rp_symbol, spans[rp_span])
        if not res.ok:
            st.error(f"Could not load history: {res.message}")
        elif len(res.data) < 5:
            st.error("Not enough historical data for a replay.")
        else:
            ss["replay"] = ReplaySession(res.data["Close"], rp_symbol)
            ss["rp_running"], ss["rp_skip_first"] = True, True
    if b2.button("Pause", key="rp_pause"):
        ss["rp_running"] = False
    if b3.button("Resume", key="rp_resume") and "replay" in ss and not ss["replay"].finished:
        ss["rp_running"], ss["rp_skip_first"] = True, True
    if b4.button("Next day", key="rp_step") and "replay" in ss:
        ss["rp_running"] = False
        ss["replay"].step()
    if b5.button("Reset", key="rp_reset"):
        ss.pop("replay", None)
        ss["rp_running"] = False

    def replay_live():
        """Runs on a timer while the replay is playing (a Streamlit fragment)."""
        sess = ss.get("replay")
        if sess is None:
            st.info("Choose a stock and a period, then press 'Start new session'.")
            return
        if ss.get("rp_running"):
            if ss.pop("rp_skip_first", False):
                pass                      # the first display after Start/Resume should not skip a day
            else:
                sess.step()
            if sess.finished:
                ss["rp_running"] = False
                st.rerun()                # full rerun so the timer stops

        top, controls, charts = st.container(), st.container(), st.container()
        with controls:
            q1, q2, q3, _ = st.columns([1, 1, 1, 2])
            qty = q1.number_input("Shares", min_value=1, value=1, step=1, key="rp_qty")
            for side, col in (("BUY", q2), ("SELL", q3)):
                if col.button(f"{side.title()} at today's close", key=f"rp_{side}", disabled=sess.finished):
                    ok, msg = sess.trade(side, int(qty))
                    (st.success if ok else st.error)(msg)
        with top:
            st.progress(sess.i / (len(sess.close) - 1), text=f"Day {sess.i + 1} of {len(sess.close)} · {sess.date:%Y-%m-%d}")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Price (close)", money(sess.price))
            m2.metric("Cash", money(sess.cash))
            m3.metric("Shares held", sess.shares)
            m4.metric("Your portfolio", money(sess.portfolio_value()))
            m5.metric("Buy & hold", money(sess.buy_hold_value()))
        with charts:
            hist = sess.history()
            st.plotly_chart(viz.replay_chart(hist, sess.trades, sess.symbol), key="rp_price")
            st.plotly_chart(viz.portfolio_vs_hold_chart(hist), key="rp_value")
            if sess.finished:
                r = sess.result()
                st.success(f"Session finished. Your profit/loss: {signed_money(r['profit_loss'])} ({percent(r['return_pct'])}). "
                           f"Buy & hold: {signed_money(r['buy_hold_profit_loss'])} ({percent(r['buy_hold_return_pct'])}). "
                           + ("You beat buy & hold." if r["beat_buy_hold"] else "Buy & hold did at least as well."))
                st.caption("Historical results only. Past performance does not guarantee future results.")

    st.fragment(run_every=rp_speed if ss.get("rp_running") else None)(replay_live)()

# =============================================================== 5. hypothetical market
with tab_hypo:
    st.markdown(f"{ui.badge(DataCategory.HYPOTHETICAL)} Every number here is generated from the assumptions you choose. "
                "It is **not** real market data and **not** a forecast.", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    start_price = c1.number_input("Starting price ($)", min_value=1.0, value=100.0, step=1.0, key="hy_price")
    exp_return = c2.slider("Expected annual return (%)", -30.0, 60.0, 8.0, 1.0, key="hy_ret")
    volatility = c3.slider("Annual volatility (%)", 1.0, 100.0, 25.0, 1.0, key="hy_vol")
    d1, d2, d3 = st.columns(3)
    days = d1.slider("Trading days", 20, 756, 252, 4, key="hy_days")
    n_paths = d2.slider("Number of simulations", 10, 500, 100, 10, key="hy_paths")
    seed = d3.number_input("Random seed (same seed = same result)", min_value=0, value=42, step=1, key="hy_seed")

    paths = dp.simulate_gbm(start_price, exp_return / 100, volatility / 100, days, n_paths, int(seed))
    st.plotly_chart(viz.gbm_chart(paths), key="gbm")
    final_values = START_CASH * paths.iloc[-1] / start_price   # value of $10,000 invested at the start
    a, b, c, d = st.columns(4)
    a.metric("Median final value (hypothetical)", money(final_values.median()))
    b.metric("Worst 5% of runs end below", money(final_values.quantile(0.05)))
    c.metric("Best 5% of runs end above", money(final_values.quantile(0.95)))
    d.metric("Runs that lose money", f"{(final_values < START_CASH).mean() * 100:.0f}%")
    st.caption(f"Hypothetical result of investing {money(START_CASH)} at the start and holding. Model: geometric Brownian motion (see About page).")
