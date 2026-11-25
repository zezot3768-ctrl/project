"""Shared Streamlit pieces: theme CSS, data-source badges, stock cards, sidebar controls."""
import html

import streamlit as st

from . import config, database as db
from .constants import DEFAULT_WATCHLIST, FEATURED, POPULAR
from .data_fetcher import DataCategory, FetchResult, MarketData, get_service, market_status
from .errors import ProviderConfigError
from .formatting import compact, money, percent, signed_money, utc_time

CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1250px;}
.card {background:#13203A; border:1px solid #223A5E; border-radius:12px; padding:16px 18px; margin-bottom:8px;}
.card .top {display:flex; justify-content:space-between; align-items:center;}
.card .sym {font-size:1.05rem; font-weight:700; color:#fff; margin-right:8px;}
.card .name {color:#94A3B8; font-size:.85rem;}
.card .price {font-size:2rem; font-weight:700; color:#fff; line-height:1.2; margin-top:6px;}
.card.small .price {font-size:1.5rem;}
.card .chg {font-weight:600; font-size:.95rem;}
.card .meta {color:#94A3B8; font-size:.78rem; margin-top:4px;}
.up {color:#22C55E;} .down {color:#EF4444;}
.badge {display:inline-block; padding:2px 9px; border-radius:999px; font-size:.7rem; font-weight:700; letter-spacing:.03em;}
.b-real {background:rgba(34,197,94,.15); color:#22C55E; border:1px solid #22C55E;}
.b-delayed {background:rgba(245,158,11,.15); color:#F59E0B; border:1px solid #F59E0B;}
.b-hist {background:rgba(56,189,248,.15); color:#38BDF8; border:1px solid #38BDF8;}
.b-hypo {background:rgba(167,139,250,.15); color:#A78BFA; border:1px solid #A78BFA;}
.b-stale {background:rgba(239,68,68,.15); color:#EF4444; border:1px solid #EF4444;}
.status {background:#0F1B33; border:1px solid #223A5E; border-radius:10px; padding:8px 14px; font-size:.85rem; color:#CBD5E1; margin-bottom:10px;}
.sim-banner {background:rgba(167,139,250,.12); border:1px solid #A78BFA; border-radius:10px; padding:10px 14px; color:#E2E8F0; margin-bottom:12px;}
</style>
"""

_BADGE_CLASS = {
    DataCategory.REAL_TIME: "b-real", DataCategory.DELAYED: "b-delayed",
    DataCategory.HISTORICAL: "b-hist", DataCategory.HYPOTHETICAL: "b-hypo",
}


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def badge(category: DataCategory, stale: bool = False) -> str:
    text = html.escape(category.value.upper())
    out = f'<span class="badge {_BADGE_CLASS[category]}">{text}</span>'
    if stale:
        out += ' <span class="badge b-stale">STALE</span>'
    return out


def sim_banner(text="SIMULATION ONLY. No real orders are placed and no real money is used. Trades use the latest retrieved price as a reference."):
    st.markdown(f'<div class="sim-banner">{html.escape(text)}</div>', unsafe_allow_html=True)


def get_data_service() -> MarketData:
    """Return the shared data service, or show a clear message and stop the page."""
    try:
        return get_service()
    except ProviderConfigError as exc:
        st.error(f"Data provider problem: {exc}")
        st.info("Open the README for setup instructions. Tip: set DATA_PROVIDER=yahoo to use Yahoo Finance without an API key.")
        st.stop()


def current_user() -> str:
    """Simple profile selector (no passwords: this is a classroom project, not a bank)."""
    if "profile_input" not in st.session_state:
        st.session_state["profile_input"] = st.session_state.get("user", "student")
    st.sidebar.markdown("### Profile")
    name = st.sidebar.text_input("Profile name", key="profile_input", help="Your virtual portfolio and watchlist are saved under this name.")
    user = db.clean_user(name)
    st.session_state["user"] = user
    db.ensure_account(user)
    return user


def refresh_controls(service: MarketData) -> tuple[bool, int]:
    """Sidebar controls for automatic and manual refresh. Returns (auto_on, seconds)."""
    st.sidebar.markdown("### Data refresh")
    auto = st.sidebar.toggle("Auto-refresh", value=not service.provider.requires_key, key="auto_refresh",
                             help="Keyed APIs have strict request limits, so auto-refresh starts off for them.")
    seconds = st.sidebar.number_input("Every (seconds)", min_value=15, max_value=900, value=config.get_settings().refresh_seconds,
                                      step=15, key="refresh_seconds")
    if st.sidebar.button("Refresh now"):
        service.clear_quotes()
    return bool(auto), int(seconds)


def stock_card_html(symbol: str, result: FetchResult, small: bool = False) -> str:
    cls = "card small" if small else "card"
    if not result.ok or result.data is None:
        return (f'<div class="{cls}"><div class="top"><span class="sym">{html.escape(symbol)}</span></div>'
                f'<div class="price">Unavailable</div><div class="meta">{html.escape(result.message)}</div></div>')
    q = result.data
    direction = "up" if (q.change or 0) >= 0 else "down"
    arrow = "▲" if direction == "up" else "▼"
    change = f'{arrow} {signed_money(q.change)} ({percent(q.change_pct)})' if q.change is not None else "Change N/A"
    return (
        f'<div class="{cls}"><div class="top"><div><span class="sym">{html.escape(symbol)}</span>'
        f'<span class="name">{html.escape(q.name)}</span></div><div>{badge(q.category, result.stale)}</div></div>'
        f'<div class="price">{money(q.price)}</div><div class="chg {direction}">{change}</div>'
        f'<div class="meta">Volume {compact(q.volume)} · Market cap {compact(q.market_cap, "$")}</div>'
        f'<div class="meta">Price date {q.as_of:%Y-%m-%d} · Updated {utc_time(result.fetched_at)}</div></div>')


def status_bar(service: MarketData, results: dict[str, FetchResult]) -> None:
    """Show the data source, data type, last successful update, and any problems."""
    cats = []
    for r in results.values():
        if r.ok and r.data is not None and r.data.category not in cats:
            cats.append(r.data.category)
    badges = " ".join(badge(c) for c in cats) or '<span class="badge b-stale">NO DATA</span>'
    st.markdown(
        f'<div class="status">Source: <b>{html.escape(service.provider.label)}</b> &nbsp;·&nbsp; {badges} &nbsp;·&nbsp; '
        f'Last successful update: <b>{utc_time(service.last_success())}</b></div>', unsafe_allow_html=True)
    notes = [service.provider.delay_note] if service.provider.delay_note else []
    notes.append("Outside market hours, the latest available close is shown and labelled 'Historical (latest close)'.")
    st.caption(" ".join(notes))
    problems = [f"**{s}**: {r.message}" for s, r in results.items() if r.message]
    if problems:
        st.warning("Some data could not be refreshed:\n\n" + "\n\n".join(f"- {p}" for p in problems))


def market_banner(results: dict[str, FetchResult]) -> str:
    """Text such as 'Open (regular session ...)' based on the newest price date we have."""
    dates = [r.data.as_of.date() for r in results.values() if r.ok and r.data is not None]
    return market_status(max(dates) if dates else None)[1]


def symbol_options(user: str) -> list[str]:
    """Stocks the user can pick from: watchlist first, then featured and popular ones."""
    return list(dict.fromkeys(db.get_watchlist(user) + FEATURED + POPULAR + DEFAULT_WATCHLIST))


def go_to_analysis(symbol: str) -> None:
    """Remember the chosen stock and open the Stock Analysis page."""
    st.session_state["selected_symbol"] = symbol
    st.switch_page("pages/stock_analysis.py")


def manual_refresh(service: MarketData) -> None:
    """Sidebar button that clears cached quotes so the next load downloads new ones."""
    st.sidebar.markdown("### Data refresh")
    if st.sidebar.button("Refresh now"):
        service.clear_quotes()
