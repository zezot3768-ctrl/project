"""Watchlist: follow the stocks you care about."""
import streamlit as st

from modules import database as db, ui
from modules.data_fetcher import normalize_symbol
from modules.errors import DataError
from modules.formatting import compact, money, percent

ui.apply_theme()
service = ui.get_data_service()
user = ui.current_user()
ui.manual_refresh(service)

st.title("Watchlist")

# ---------------------------------------------------------------- add a stock
c1, c2, _ = st.columns([2, 1, 3])
new_symbol = c1.text_input("Add a ticker (for example MSFT)", key="wl_new")
if c2.button("Add to watchlist"):
    try:
        symbol = normalize_symbol(new_symbol)
        check = service.quote(symbol)          # only add tickers that really return data
        if check.ok:
            db.add_to_watchlist(user, symbol)
            st.success(f"{symbol} added.")
        else:
            st.error(f"Could not add {symbol}: {check.message}")
    except DataError as exc:
        st.error(str(exc))

watch = db.get_watchlist(user)
if not watch:
    st.info("Your watchlist is empty. Add a ticker above.")
    st.stop()

with st.spinner("Loading prices..."):
    results = service.quotes(watch)
ui.status_bar(service, results)

# ---------------------------------------------------------------- table of stocks
header = st.columns([1.3, 2.2, 1.3, 1.6, 1.3, 1, 1])
for col, text in zip(header, ["Symbol", "Company", "Price", "Change", "Volume", "", ""]):
    col.markdown(f"**{text}**")
for sym in watch:
    r = results[sym]
    cols = st.columns([1.3, 2.2, 1.3, 1.6, 1.3, 1, 1])
    cols[0].markdown(f"**{sym}**")
    if r.ok and r.data is not None:
        q = r.data
        cls = "up" if (q.change or 0) >= 0 else "down"
        cols[1].write(q.name)
        cols[2].write(money(q.price))
        cols[3].markdown(f'<span class="{cls}">{percent(q.change_pct)}</span>', unsafe_allow_html=True)
        cols[4].write(compact(q.volume))
    else:
        cols[1].write("Unavailable")
        cols[2].write("N/A")
    if cols[5].button("Analyze", key=f"wl_an_{sym}"):
        ui.go_to_analysis(sym)
    if cols[6].button("Remove", key=f"wl_rm_{sym}"):
        db.remove_from_watchlist(user, sym)
        st.rerun()
st.caption("Prices are labelled by data type in the status bar above. Not investment advice.")
