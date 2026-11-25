"""SQLite storage so the virtual portfolio and watchlist survive between sessions.

Three tables: accounts (cash), transactions (every BUY/SELL) and watchlist.
Holdings are not stored: they are rebuilt from the transactions (see portfolio.compute_holdings).
"""
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .constants import DEFAULT_WATCHLIST, START_CASH
from .portfolio import compute_holdings, validate_trade

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    user TEXT PRIMARY KEY, cash REAL NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    shares INTEGER NOT NULL CHECK (shares > 0), price REAL NOT NULL CHECK (price > 0),
    total REAL NOT NULL, executed_at TEXT NOT NULL, data_category TEXT NOT NULL,
    realized_pl REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS watchlist (
    user TEXT NOT NULL, symbol TEXT NOT NULL, added_at TEXT NOT NULL, PRIMARY KEY (user, symbol));
"""


@dataclass
class TradeResult:
    ok: bool
    message: str


def clean_user(name: str) -> str:
    """Keep user names simple and safe: letters, digits, _ and - (max 30 characters)."""
    cleaned = re.sub(r"[^a-z0-9_-]", "", (name or "").strip().lower())[:30]
    return cleaned or "student"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _connect(db_path=None):
    path = Path(db_path or config.get_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, isolation_level=None)  # we control transactions ourselves
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def ensure_account(user: str, db_path=None) -> None:
    """Create the account ($10,000 virtual cash) and default watchlist on first use."""
    with closing(_connect(db_path)) as con:
        if con.execute("SELECT 1 FROM accounts WHERE user=?", (user,)).fetchone() is None:
            con.execute("INSERT INTO accounts VALUES (?,?,?)", (user, START_CASH, _now()))
            con.executemany("INSERT OR IGNORE INTO watchlist VALUES (?,?,?)", [(user, s, _now()) for s in DEFAULT_WATCHLIST])


def get_state(user: str, db_path=None) -> dict:
    """Return cash, all transactions (oldest first) and realized profit/loss."""
    ensure_account(user, db_path)
    with closing(_connect(db_path)) as con:
        cash = con.execute("SELECT cash FROM accounts WHERE user=?", (user,)).fetchone()["cash"]
        txs = [dict(r) for r in con.execute("SELECT * FROM transactions WHERE user=? ORDER BY id", (user,))]
    return {"cash": cash, "transactions": txs, "realized_pl": round(sum(t["realized_pl"] for t in txs), 2)}


def execute_trade(user, symbol, side, shares, price, data_category, db_path=None) -> TradeResult:
    """Validate and record a virtual trade in a single all-or-nothing database transaction."""
    ensure_account(user, db_path)
    with closing(_connect(db_path)) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            cash = con.execute("SELECT cash FROM accounts WHERE user=?", (user,)).fetchone()["cash"]
            txs = [dict(r) for r in con.execute("SELECT * FROM transactions WHERE user=? ORDER BY id", (user,))]
            holdings = compute_holdings(txs)
            ok, msg = validate_trade(cash, holdings, side, symbol, shares, price)
            if not ok:
                con.execute("ROLLBACK")
                return TradeResult(False, msg)
            total = round(shares * price, 2)
            realized = round((price - holdings[symbol].avg_cost) * shares, 2) if side == "SELL" else 0.0
            new_cash = round(cash - total if side == "BUY" else cash + total, 2)
            con.execute(
                "INSERT INTO transactions (user,symbol,side,shares,price,total,executed_at,data_category,realized_pl) VALUES (?,?,?,?,?,?,?,?,?)",
                (user, symbol, side, shares, price, total, _now(), data_category, realized))
            con.execute("UPDATE accounts SET cash=? WHERE user=?", (new_cash, user))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return TradeResult(True, f"Simulated {side}: {shares} x {symbol} at ${price:,.2f} (total ${total:,.2f}).")


def reset_account(user: str, db_path=None) -> None:
    """Delete all transactions and restore the starting cash."""
    ensure_account(user, db_path)
    with closing(_connect(db_path)) as con:
        con.execute("DELETE FROM transactions WHERE user=?", (user,))
        con.execute("UPDATE accounts SET cash=? WHERE user=?", (START_CASH, user))


def get_watchlist(user: str, db_path=None) -> list[str]:
    ensure_account(user, db_path)
    with closing(_connect(db_path)) as con:
        return [r["symbol"] for r in con.execute("SELECT symbol FROM watchlist WHERE user=? ORDER BY added_at, symbol", (user,))]


def add_to_watchlist(user: str, symbol: str, db_path=None) -> None:
    ensure_account(user, db_path)
    with closing(_connect(db_path)) as con:
        con.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?,?)", (user, symbol, _now()))


def remove_from_watchlist(user: str, symbol: str, db_path=None) -> None:
    with closing(_connect(db_path)) as con:
        con.execute("DELETE FROM watchlist WHERE user=? AND symbol=?", (user, symbol))
