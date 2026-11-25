"""Getting market data from a financial API (the 'data layer').

Structure
---------
* DataCategory      - the four kinds of data the app must never confuse.
* BaseProvider      - what every data provider must be able to do.
* YahooProvider / AlphaVantageProvider - concrete providers (choose with DATA_PROVIDER).
* MarketData        - wraps a provider with caching, rate limiting and error handling.
                      If a request fails it returns the last good data marked as STALE,
                      or a clear error message. It never invents prices.
"""
from __future__ import annotations

import math
import re
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from enum import Enum
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from . import config
from .constants import COMPANY_NAMES, INDICES_ETF_PROXY, INDICES_YAHOO
from .data_processor import clean_ohlcv
from .errors import DataError, ProviderConfigError, RateLimitError

NY = ZoneInfo("America/New_York")
SYMBOL_RE = re.compile(r"^[A-Z0-9.\-\^]{1,10}$")


class DataCategory(str, Enum):
    REAL_TIME = "Real-time"
    DELAYED = "Delayed"
    HISTORICAL = "Historical (latest close)"
    HYPOTHETICAL = "Hypothetical"


def normalize_symbol(raw: str) -> str:
    symbol = (raw or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        raise DataError(f"'{raw}' is not a valid ticker symbol.")
    return symbol


def _num(value) -> float | None:
    """Convert to float, or None if missing / not a finite number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# --------------------------------------------------------------------------- market hours
def market_status(last_bar_date: date | None = None, now: datetime | None = None) -> tuple[bool, str]:
    """Is the US stock market open right now? Returns (is_open, description).

    Holidays: if it is a weekday during trading hours but the newest price bar is not from
    today, the market is treated as closed (holiday or no trading).
    """
    ny = (now or datetime.now(timezone.utc)).astimezone(NY)
    if ny.weekday() >= 5:
        return False, "Closed (weekend)"
    if dtime(9, 30) <= ny.time() < dtime(16, 0):
        if last_bar_date is not None and last_bar_date != ny.date():
            return False, "Closed today (market holiday or no trading yet)"
        return True, "Open (regular session 9:30-16:00 ET)"
    return False, "Closed (outside regular trading hours)"


# --------------------------------------------------------------------------- data objects
@dataclass
class Quote:
    symbol: str
    name: str
    price: float
    previous_close: float | None
    volume: float | None
    market_cap: float | None
    as_of: datetime            # date/time of the newest price bar
    source: str
    category: DataCategory

    @property
    def change(self) -> float | None:
        return None if self.previous_close is None else self.price - self.previous_close

    @property
    def change_pct(self) -> float | None:
        if self.previous_close in (None, 0):
            return None
        return (self.price / self.previous_close - 1) * 100


@dataclass
class FetchResult:
    data: Any = None
    ok: bool = False
    stale: bool = False        # True = old data shown because a refresh failed
    message: str = ""
    fetched_at: datetime | None = None


def _frame_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep the five OHLCV columns and make the index plain (timezone-free) dates."""
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    return df


def _trim(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Keep only the rows inside the requested period (used when a provider returns more)."""
    days = {"5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653}.get(period)
    return df if days is None else df[df.index >= df.index[-1] - timedelta(days=days)]


# --------------------------------------------------------------------------- providers
class BaseProvider(ABC):
    key = "base"
    label = "Base provider"
    requires_key = False
    is_realtime = False          # True only if the provider supplies real-time prices
    delay_note = ""
    rate_limit_per_minute = 60
    indices = INDICES_YAHOO
    index_note = ""

    @abstractmethod
    def get_history(self, symbol: str, period: str = "1y") -> pd.DataFrame: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict: ...

    def _category(self, last_bar: pd.Timestamp) -> DataCategory:
        is_open, _ = market_status(last_bar.date())
        if is_open:
            return DataCategory.REAL_TIME if self.is_realtime else DataCategory.DELAYED
        return DataCategory.HISTORICAL


class YahooProvider(BaseProvider):
    """Yahoo Finance via the community 'yfinance' library (no API key needed)."""

    key = "yahoo"
    label = "Yahoo Finance (via yfinance)"
    delay_note = "Yahoo Finance prices are usually delayed by up to about 15 minutes."
    rate_limit_per_minute = 60

    @staticmethod
    def _yf():
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderConfigError("The 'yfinance' package is not installed. Run: pip install -r requirements.txt") from exc
        return yf

    def get_history(self, symbol, period="1y"):
        raw = self._yf().Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        if raw is None or raw.empty:
            raise DataError(f"No price data was returned for {symbol}. Check the ticker symbol.")
        return _frame_from_raw(raw)

    def get_quote(self, symbol):
        yf = self._yf()
        hist = clean_ohlcv(self.get_history(symbol, "5d"))
        price = float(hist["Close"].iloc[-1])
        previous = float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
        market_cap = None
        try:  # extra details are optional: a failure here must not break the quote
            info = yf.Ticker(symbol).fast_info
            market_cap = _num(_first(info, "market_cap", "marketCap"))
            prev_close = _num(_first(info, "previous_close", "previousClose"))
            last_price = _num(_first(info, "last_price", "lastPrice"))
            if prev_close:
                previous = prev_close
            if last_price:
                price = last_price
        except Exception:
            pass
        last_bar = hist.index[-1]
        return Quote(symbol, COMPANY_NAMES.get(symbol, symbol), price, previous, _num(hist["Volume"].iloc[-1]),
                     market_cap, last_bar.to_pydatetime(), self.label, self._category(last_bar))

    def get_fundamentals(self, symbol):
        info = self._yf().Ticker(symbol).info or {}
        return {
            "name": info.get("longName") or info.get("shortName"),
            "market_cap": _num(info.get("marketCap")), "pe_ratio": _num(info.get("trailingPE")),
            "eps": _num(info.get("trailingEps")), "revenue": _num(info.get("totalRevenue")),
            "net_income": _num(info.get("netIncomeToCommon")), "dividend_rate": _num(info.get("dividendRate")),
        }


def _first(obj, *names):
    for name in names:
        try:
            return obj[name]
        except Exception:
            continue
    return None


class AlphaVantageProvider(BaseProvider):
    """Alpha Vantage REST API (free key from alphavantage.co; about 5 requests/minute, 25/day)."""

    key = "alphavantage"
    label = "Alpha Vantage"
    requires_key = True
    delay_note = "Alpha Vantage free-tier quotes are end-of-day / delayed, not real-time."
    rate_limit_per_minute = 5
    indices = INDICES_ETF_PROXY
    index_note = "Alpha Vantage's free API does not provide index values, so ETFs that track each index are shown as proxies."
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None):
        if not api_key:
            raise ProviderConfigError("ALPHA_VANTAGE_API_KEY is not set. Add it to your .env file or Streamlit secrets (see README).")
        self.api_key = api_key

    def _call(self, params: dict) -> dict:
        resp = requests.get(self.BASE_URL, params={**params, "apikey": self.api_key}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for key in ("Error Message", "Information", "Note"):
            if key in data:
                text = str(data[key])
                if any(w in text.lower() for w in ("rate limit", "requests per", "call frequency", "api call")):
                    raise RateLimitError("Alpha Vantage request limit reached. Try again later.")
                raise DataError(f"Alpha Vantage: {text}")
        return data

    def get_history(self, symbol, period="1y"):
        size = "compact" if period in ("1mo", "3mo") else "full"
        data = self._call({"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": size})
        series = data.get("Time Series (Daily)")
        if not series:
            raise DataError(f"No price data was returned for {symbol}.")
        df = pd.DataFrame.from_dict(series, orient="index")
        df = df.rename(columns={"1. open": "Open", "2. high": "High", "3. low": "Low", "4. close": "Close", "5. volume": "Volume"})
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        df.index = pd.to_datetime(df.index)
        return _trim(df.sort_index(), period)

    def get_quote(self, symbol):
        q = self._call({"function": "GLOBAL_QUOTE", "symbol": symbol}).get("Global Quote") or {}
        price = _num(q.get("05. price"))
        if price is None:
            raise DataError(f"No quote was returned for {symbol}.")
        last_bar = pd.Timestamp(q.get("07. latest trading day"))
        return Quote(symbol, COMPANY_NAMES.get(symbol, symbol), price, _num(q.get("08. previous close")),
                     _num(q.get("06. volume")), None, last_bar.to_pydatetime(), self.label, self._category(last_bar))

    def get_fundamentals(self, symbol):
        d = self._call({"function": "OVERVIEW", "symbol": symbol})
        return {
            "name": d.get("Name"), "market_cap": _num(d.get("MarketCapitalization")), "pe_ratio": _num(d.get("PERatio")),
            "eps": _num(d.get("EPS")), "revenue": _num(d.get("RevenueTTM")), "net_income": None,
            "dividend_rate": _num(d.get("DividendPerShare")),
        }


PROVIDERS = {"yahoo": YahooProvider, "alphavantage": AlphaVantageProvider}


def build_provider(name: str | None = None) -> BaseProvider:
    """Create the provider chosen by DATA_PROVIDER. To add a provider, register it in PROVIDERS."""
    settings = config.get_settings()
    name = (name or settings.provider).lower()
    if name == "yahoo":
        return YahooProvider()
    if name == "alphavantage":
        return AlphaVantageProvider(settings.alpha_vantage_key)
    raise ProviderConfigError(f"Unknown DATA_PROVIDER '{name}'. Choose one of: {', '.join(PROVIDERS)}.")


# --------------------------------------------------------------------------- caching + errors
class RateLimiter:
    """Allow at most `max_calls` provider requests in any `per_seconds` window."""

    def __init__(self, max_calls: int, per_seconds: float = 60.0):
        self.max_calls, self.per_seconds, self.calls = max_calls, per_seconds, deque()

    def check(self) -> None:
        now = time.monotonic()
        while self.calls and now - self.calls[0] > self.per_seconds:
            self.calls.popleft()
        if len(self.calls) >= self.max_calls:
            raise RateLimitError(f"Request limit reached ({self.max_calls} per minute). Showing saved data when available.")
        self.calls.append(now)


def friendly_error(exc: Exception) -> str:
    """Turn technical exceptions into messages a student can understand."""
    if isinstance(exc, DataError):
        return str(exc)
    text = str(exc).lower()
    if isinstance(exc, requests.exceptions.Timeout):
        return "The data provider took too long to respond. Please try again."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Could not reach the data provider. Check your internet connection."
    if "too many requests" in text or "rate limit" in text or "429" in text:
        return "The data provider is rate-limiting requests. Please wait a minute and refresh."
    return f"Unexpected problem while retrieving data ({type(exc).__name__}). Please try again later."


class MarketData:
    """Caching, rate limiting and graceful failure around a provider."""

    def __init__(self, provider: BaseProvider, quote_ttl=60, history_ttl=900, fundamentals_ttl=21600):
        self.provider = provider
        self.quote_ttl, self.history_ttl, self.fundamentals_ttl = quote_ttl, history_ttl, fundamentals_ttl
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._limiter = RateLimiter(provider.rate_limit_per_minute)
        self._last_success: datetime | None = None

    def _fetch(self, key: tuple, ttl: float, loader: Callable[[], Any], force=False) -> FetchResult:
        now = time.time()
        hit = self._cache.get(key)
        if hit and not force and now - hit[0] < ttl:
            return FetchResult(hit[1], True, False, "", datetime.fromtimestamp(hit[0], timezone.utc))
        try:
            self._limiter.check()
            value = loader()
        except Exception as exc:  # any failure: fall back to old data if we have it
            message = friendly_error(exc)
            if hit:
                when = datetime.fromtimestamp(hit[0], timezone.utc)
                return FetchResult(hit[1], True, True, f"{message} Showing saved data from {when:%H:%M:%S} UTC.", when)
            return FetchResult(None, False, False, message)
        self._cache[key] = (now, value)
        self._last_success = datetime.fromtimestamp(now, timezone.utc)
        return FetchResult(value, True, False, "", self._last_success)

    def quote(self, symbol: str, force=False, ttl=None) -> FetchResult:
        try:
            symbol = normalize_symbol(symbol)
        except DataError as exc:
            return FetchResult(message=str(exc))
        return self._fetch(("quote", symbol), ttl or self.quote_ttl, lambda: self.provider.get_quote(symbol), force)

    def quotes(self, symbols, force=False, ttl=None) -> dict[str, FetchResult]:
        return {s: self.quote(s, force, ttl) for s in symbols}

    def history(self, symbol: str, period="1y", force=False) -> FetchResult:
        try:
            symbol = normalize_symbol(symbol)
        except DataError as exc:
            return FetchResult(message=str(exc))
        return self._fetch(("history", symbol, period), self.history_ttl,
                           lambda: clean_ohlcv(self.provider.get_history(symbol, period)), force)

    def fundamentals(self, symbol: str, force=False) -> FetchResult:
        try:
            symbol = normalize_symbol(symbol)
        except DataError as exc:
            return FetchResult(message=str(exc))
        return self._fetch(("fund", symbol), self.fundamentals_ttl, lambda: self.provider.get_fundamentals(symbol), force)

    def clear_quotes(self) -> None:
        """Used by the manual Refresh button: forget cached quotes so new ones are downloaded."""
        self._cache = {k: v for k, v in self._cache.items() if k[0] != "quote"}

    def last_success(self) -> datetime | None:
        return self._last_success


_SERVICES: dict[str, MarketData] = {}


def get_service(provider_name: str | None = None) -> MarketData:
    """Return one shared MarketData object per provider (so the cache survives Streamlit reruns)."""
    settings = config.get_settings()
    name = (provider_name or settings.provider).lower()
    if name not in _SERVICES:
        _SERVICES[name] = MarketData(build_provider(name), settings.quote_ttl, settings.history_ttl)
    return _SERVICES[name]


def quotes_to_frame(results: dict[str, FetchResult]) -> pd.DataFrame:
    """Turn quote results into a table (one row per stock that has data)."""
    rows = []
    for sym, res in results.items():
        if res.ok and res.data is not None:
            q = res.data
            rows.append({"Symbol": sym, "Name": q.name, "Price": q.price, "Change": q.change, "Change %": q.change_pct,
                         "Volume": q.volume, "Market cap": q.market_cap, "Data": q.category.value + (" (stale)" if res.stale else "")})
    return pd.DataFrame(rows)
