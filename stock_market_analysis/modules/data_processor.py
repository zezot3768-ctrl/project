"""Data cleaning and statistics with Pandas and NumPy.

Every function here is pure (no internet, no Streamlit), so it can be reused in the
Jupyter notebook and tested on its own.
"""
import numpy as np
import pandas as pd

from .errors import DataError

OHLCV = ["Open", "High", "Low", "Close", "Volume"]
TRADING_DAYS = 252  # trading days in a typical year, used to annualize volatility


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean a table of daily prices.

    Steps: check columns -> convert to numbers -> sort by date -> remove duplicate dates
    -> drop rows without a valid Close -> fill missing Open/High/Low with Close
    -> missing Volume becomes 0 -> make sure High/Low really bound Open/Close.
    """
    if df is None or len(df) == 0:
        raise DataError("The data provider returned no price rows.")
    lookup = {str(c).strip().lower(): c for c in df.columns}
    missing = [c for c in OHLCV if c.lower() not in lookup]
    if missing:
        raise DataError(f"Price data is missing columns: {', '.join(missing)}.")

    out = pd.DataFrame({c: pd.to_numeric(df[lookup[c.lower()]], errors="coerce") for c in OHLCV})
    out.index = pd.to_datetime(df.index)
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out[out["Close"].notna() & (out["Close"] > 0)]
    for col in ("Open", "High", "Low"):
        out[col] = out[col].fillna(out["Close"])
    out["Volume"] = out["Volume"].fillna(0)
    out["High"] = out[["High", "Open", "Close"]].max(axis=1)
    out["Low"] = out[["Low", "Open", "Close"]].min(axis=1)
    if out.empty:
        raise DataError("No valid prices remained after cleaning the data.")
    return out


def resample_ohlcv(df: pd.DataFrame, rule: str | None) -> pd.DataFrame:
    """Turn daily bars into weekly ('W-FRI'), monthly ('ME') or yearly ('YE') bars."""
    if rule is None:
        return df
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample(rule).agg(agg).dropna(subset=["Close"])


def daily_returns(close: pd.Series) -> pd.Series:
    """Percentage change from one day's close to the next, as a fraction (0.01 = 1%)."""
    return close.pct_change().dropna()


def max_drawdown(close: pd.Series) -> float:
    """Largest fall from a previous peak (a negative fraction, e.g. -0.25 = -25%)."""
    running_peak = close.cummax()
    return float((close / running_peak - 1).min())


def summary_stats(df: pd.DataFrame) -> dict:
    """Key statistics about the price history in `df` (daily bars expected)."""
    close = df["Close"]
    rets = daily_returns(close)
    daily_vol = float(rets.std(ddof=1)) if len(rets) > 1 else float("nan")
    return {
        "start_date": close.index[0],
        "end_date": close.index[-1],
        "trading_days": int(len(close)),
        "total_return": float(close.iloc[-1] / close.iloc[0] - 1),
        "avg_daily_return": float(rets.mean()) if len(rets) else float("nan"),
        "daily_volatility": daily_vol,
        "annual_volatility": daily_vol * float(np.sqrt(TRADING_DAYS)),
        "max_price": float(df["High"].max()),
        "max_price_date": df["High"].idxmax(),
        "min_price": float(df["Low"].min()),
        "min_price_date": df["Low"].idxmin(),
        "best_day": float(rets.max()) if len(rets) else float("nan"),
        "worst_day": float(rets.min()) if len(rets) else float("nan"),
        "max_drawdown": max_drawdown(close),
    }


def normalize(close: pd.Series) -> pd.Series:
    """Rescale a price series to start at 100 so different stocks can be compared."""
    return close / close.iloc[0] * 100


def period_return(close: pd.Series, days: int) -> float | None:
    """Return over the last `days` rows, or None if there is not enough data."""
    if len(close) <= days:
        return None
    return float(close.iloc[-1] / close.iloc[-1 - days] - 1)


def simulate_gbm(start_price, annual_return, annual_vol, days, n_paths=100, seed=None) -> pd.DataFrame:
    """HYPOTHETICAL prices from geometric Brownian motion (a standard textbook model).

    S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z),  Z ~ Normal(0, 1)
    These numbers are invented by a random number generator. They are NOT real prices.
    """
    rng = np.random.default_rng(seed)
    dt = 1 / TRADING_DAYS
    z = rng.standard_normal((days, n_paths))
    steps = (annual_return - 0.5 * annual_vol**2) * dt + annual_vol * np.sqrt(dt) * z
    prices = start_price * np.exp(np.vstack([np.zeros((1, n_paths)), np.cumsum(steps, axis=0)]))
    return pd.DataFrame(prices, columns=[f"Path {i + 1}" for i in range(n_paths)])
