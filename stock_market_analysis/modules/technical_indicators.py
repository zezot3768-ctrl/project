"""Technical indicators calculated with Pandas. Each function takes a price Series."""
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average: the plain average of the last `window` closes."""
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average: like SMA, but recent prices count more."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index (0-100) using Wilder's smoothing.

    RSI = 100 - 100 / (1 + average gain / average loss)
    """
    change = close.diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    result = 100 - 100 / (1 + avg_gain / avg_loss)
    result = result.where(avg_loss != 0, 100.0)  # no losses at all -> RSI is 100
    return result.where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD = EMA(fast) - EMA(slow); signal = EMA of the MACD line; histogram = MACD - signal."""
    macd_line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"MACD": macd_line, "Signal": signal_line, "Histogram": macd_line - signal_line})


def volume_analysis(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Volume, its moving average, and relative volume (today's volume / average)."""
    out = pd.DataFrame({"Volume": df["Volume"]})
    out["Volume SMA"] = sma(df["Volume"], window)
    out["Relative volume"] = out["Volume"] / out["Volume SMA"]
    return out


INDICATOR_HELP = {
    "SMA (Simple Moving Average)": (
        "The average closing price over the last N periods (for example 20 or 50 days). "
        "It smooths out daily noise so the trend is easier to see. "
        "Formula: SMA = (P1 + P2 + ... + PN) / N."
    ),
    "EMA (Exponential Moving Average)": (
        "A moving average that gives more weight to recent prices, so it reacts faster than the SMA. "
        "Formula: EMA(today) = alpha x Price(today) + (1 - alpha) x EMA(yesterday), where alpha = 2 / (N + 1)."
    ),
    "RSI (Relative Strength Index)": (
        "A momentum score between 0 and 100 that compares recent gains with recent losses (default 14 periods). "
        "Readings above 70 are often called 'overbought' and below 30 'oversold', but this is only a rule of thumb, "
        "not a prediction. Formula: RSI = 100 - 100 / (1 + average gain / average loss)."
    ),
    "MACD (Moving Average Convergence Divergence)": (
        "Shows the gap between a fast EMA (12) and a slow EMA (26). The signal line is a 9-period EMA of the MACD line. "
        "When MACD crosses above the signal line, momentum is turning upward; below, downward."
    ),
    "Trading volume": (
        "The number of shares traded in a period. High volume means many participants were active. "
        "Relative volume compares today's volume with its 20-period average."
    ),
    "Daily return": "Today's close divided by yesterday's close, minus 1. A return of 0.01 means +1%.",
    "Volatility": (
        "How widely daily returns vary: the standard deviation of daily returns. "
        "Annualized volatility = daily volatility x square root of 252 (trading days per year)."
    ),
    "Maximum drawdown": "The largest percentage fall from a previous high point to a later low point.",
}
