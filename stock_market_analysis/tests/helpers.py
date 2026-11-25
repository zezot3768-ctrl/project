"""Synthetic prices used ONLY by the automated tests. The app itself never uses fake data."""
import numpy as np
import pandas as pd


def fake_ohlcv(n=300, seed=1, start=100.0):
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({
        "Open": close * 0.998, "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float)}, index=idx)
