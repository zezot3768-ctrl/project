"""Portfolio maths and the historical replay engine. No database, no Streamlit.

Money is handled as plain floats and rounded to cents. That is fine for a learning project.
"""
import math
from dataclasses import dataclass

import pandas as pd

from .constants import START_CASH


@dataclass
class Holding:
    symbol: str
    shares: int
    avg_cost: float  # average purchase price per share


def compute_holdings(transactions: list[dict]) -> dict[str, Holding]:
    """Rebuild current holdings from the list of transactions (oldest first).

    Average-cost method: a BUY updates the average price; a SELL reduces the share count only.
    """
    holdings: dict[str, Holding] = {}
    for tx in transactions:
        sym, qty, price = tx["symbol"], int(tx["shares"]), float(tx["price"])
        if tx["side"] == "BUY":
            h = holdings.get(sym) or Holding(sym, 0, 0.0)
            h.avg_cost = (h.shares * h.avg_cost + qty * price) / (h.shares + qty)
            h.shares += qty
            holdings[sym] = h
        else:
            h = holdings[sym]
            h.shares -= qty
            if h.shares == 0:
                del holdings[sym]
    return holdings


def validate_trade(cash, holdings, side, symbol, shares, price) -> tuple[bool, str]:
    """Check a virtual trade. Returns (ok, message)."""
    if side not in ("BUY", "SELL"):
        return False, "Trade type must be BUY or SELL."
    if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0:
        return False, "Enter a whole number of shares greater than zero."
    if price is None or not math.isfinite(price) or price <= 0:
        return False, "No valid price is available for this stock."
    total = round(shares * price, 2)
    if side == "BUY" and total > round(cash, 2):
        return False, f"Not enough virtual cash: this costs ${total:,.2f} but you have ${cash:,.2f}."
    if side == "SELL":
        owned = holdings[symbol].shares if symbol in holdings else 0
        if shares > owned:
            return False, f"You only own {owned} share(s) of {symbol}."
    return True, "OK"


def portfolio_summary(cash, holdings, prices, realized_pl=0.0, start_cash=START_CASH) -> dict:
    """Combine cash, holdings and current prices into dashboard numbers.

    If a price is missing, the average cost is used for that holding and it is listed in
    `missing_prices` so the app can warn the user.
    """
    rows, missing = [], []
    for sym, h in holdings.items():
        price = prices.get(sym)
        if price is None:
            missing.append(sym)
            price = h.avg_cost
        value = h.shares * price
        invested = h.shares * h.avg_cost
        rows.append({
            "Symbol": sym, "Shares": h.shares, "Avg price": h.avg_cost, "Current price": price,
            "Invested": invested, "Market value": value, "P/L ($)": value - invested,
            "P/L (%)": (value / invested - 1) * 100 if invested else 0.0,
        })
    table = pd.DataFrame(rows)
    market_value = float(table["Market value"].sum()) if rows else 0.0
    invested_total = float(table["Invested"].sum()) if rows else 0.0
    total_value = cash + market_value
    return {
        "cash": cash, "market_value": market_value, "invested": invested_total, "total_value": total_value,
        "unrealized_pl": market_value - invested_total, "realized_pl": realized_pl,
        "total_pl": total_value - start_cash, "total_pl_pct": (total_value / start_cash - 1) * 100,
        "table": table, "missing_prices": missing,
    }


class ReplaySession:
    """Educational replay of REAL historical closing prices, one day at a time.

    The player starts with virtual cash and may buy/sell at the current day's close.
    A buy-and-hold benchmark buys as many shares as possible on day 1 and never trades.
    """

    def __init__(self, close: pd.Series, symbol: str = "", start_cash: float = START_CASH):
        if len(close) < 2:
            raise ValueError("A replay needs at least two days of prices.")
        self.close = close.astype(float)
        self.symbol = symbol
        self.start_cash = float(start_cash)
        self.i = 0  # index of the "current day"
        self.cash = float(start_cash)
        self.shares = 0
        self.trades: list[dict] = []
        self.bh_shares = int(self.start_cash // self.close.iloc[0])
        self.bh_cash = self.start_cash - self.bh_shares * self.close.iloc[0]
        self._history = [self._snapshot()]

    # ---- state ----
    @property
    def price(self) -> float:
        return float(self.close.iloc[self.i])

    @property
    def date(self):
        return self.close.index[self.i]

    @property
    def finished(self) -> bool:
        return self.i >= len(self.close) - 1

    def portfolio_value(self) -> float:
        return self.cash + self.shares * self.price

    def buy_hold_value(self) -> float:
        return self.bh_cash + self.bh_shares * self.price

    def _snapshot(self) -> dict:
        return {"Date": self.date, "Price": self.price, "Portfolio": self.portfolio_value(), "Buy & hold": self.buy_hold_value()}

    # ---- actions ----
    def step(self) -> bool:
        """Move forward one trading day. Returns False if already at the end."""
        if self.finished:
            return False
        self.i += 1
        self._history.append(self._snapshot())
        return True

    def trade(self, side: str, shares: int) -> tuple[bool, str]:
        holdings = {self.symbol: Holding(self.symbol, self.shares, 0.0)} if self.shares else {}
        ok, msg = validate_trade(self.cash, holdings, side, self.symbol, shares, self.price)
        if not ok:
            return False, msg
        total = round(shares * self.price, 2)
        if side == "BUY":
            self.cash -= total
            self.shares += shares
        else:
            self.cash += total
            self.shares -= shares
        self.trades.append({"Date": self.date, "Side": side, "Shares": shares, "Price": self.price})
        self._history[-1] = self._snapshot()
        return True, f"{side} {shares} {self.symbol} at ${self.price:,.2f}"

    # ---- results ----
    def history(self) -> pd.DataFrame:
        return pd.DataFrame(self._history)

    def result(self) -> dict:
        pv, bv = self.portfolio_value(), self.buy_hold_value()
        return {
            "portfolio_value": pv, "profit_loss": pv - self.start_cash, "return_pct": (pv / self.start_cash - 1) * 100,
            "buy_hold_value": bv, "buy_hold_profit_loss": bv - self.start_cash, "buy_hold_return_pct": (bv / self.start_cash - 1) * 100,
            "beat_buy_hold": pv > bv,
        }
