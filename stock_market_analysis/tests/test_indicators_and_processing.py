import unittest

import numpy as np
import pandas as pd

from modules import data_processor as dp
from modules import technical_indicators as ti
from modules.errors import DataError
from tests.helpers import fake_ohlcv


class IndicatorTests(unittest.TestCase):
    def test_sma_matches_manual_average(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        out = ti.sma(s, 3)
        self.assertTrue(np.isnan(out.iloc[1]))
        self.assertAlmostEqual(out.iloc[2], 2.0)
        self.assertAlmostEqual(out.iloc[4], 4.0)

    def test_ema_first_value_and_recursion(self):
        s = pd.Series([10, 11, 12, 13], dtype=float)
        out = s.ewm(span=3, adjust=False).mean()
        alpha = 2 / (3 + 1)
        self.assertAlmostEqual(out.iloc[1], alpha * 11 + (1 - alpha) * 10)
        self.assertAlmostEqual(ti.ema(s, 3).iloc[2], out.iloc[2])

    def test_rsi_bounds_and_extremes(self):
        up = pd.Series(np.arange(1, 60, dtype=float))
        self.assertAlmostEqual(ti.rsi(up).iloc[-1], 100.0)
        down = pd.Series(np.arange(60, 1, -1, dtype=float))
        self.assertAlmostEqual(ti.rsi(down).iloc[-1], 0.0, places=6)
        r = ti.rsi(fake_ohlcv()["Close"]).dropna()
        self.assertTrue(((r >= 0) & (r <= 100)).all())

    def test_macd_is_fast_minus_slow(self):
        close = fake_ohlcv()["Close"]
        m = ti.macd(close)
        expected = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        pd.testing.assert_series_equal(m["MACD"], expected, check_names=False)
        pd.testing.assert_series_equal(m["Histogram"], m["MACD"] - m["Signal"], check_names=False)

    def test_volume_analysis_columns(self):
        v = ti.volume_analysis(fake_ohlcv(), 20)
        self.assertEqual(list(v.columns), ["Volume", "Volume SMA", "Relative volume"])


class ProcessorTests(unittest.TestCase):
    def test_clean_removes_bad_rows_and_fills(self):
        df = fake_ohlcv(10)
        df.iloc[2, df.columns.get_loc("Close")] = np.nan
        df.iloc[3, df.columns.get_loc("Open")] = np.nan
        df.iloc[4, df.columns.get_loc("Volume")] = np.nan
        df = pd.concat([df, df.iloc[[0]]])  # duplicate date
        out = dp.clean_ohlcv(df)
        self.assertEqual(len(out), 9)
        self.assertFalse(out.isna().any().any())
        self.assertTrue(out.index.is_monotonic_increasing)
        self.assertTrue((out["High"] >= out["Close"]).all())

    def test_clean_rejects_missing_columns_and_empty(self):
        with self.assertRaises(DataError):
            dp.clean_ohlcv(pd.DataFrame({"Close": [1, 2]}))
        with self.assertRaises(DataError):
            dp.clean_ohlcv(pd.DataFrame())

    def test_returns_and_stats(self):
        idx = pd.bdate_range("2024-01-01", periods=4)
        df = pd.DataFrame({"Open": [100, 110, 99, 99], "High": [101, 111, 100, 105], "Low": [99, 108, 98, 98],
                           "Close": [100.0, 110.0, 99.0, 99.0], "Volume": [1, 1, 1, 1]}, index=idx)
        rets = dp.daily_returns(df["Close"])
        self.assertAlmostEqual(rets.iloc[0], 0.10)
        self.assertAlmostEqual(rets.iloc[1], -0.10)
        st = dp.summary_stats(df)
        self.assertAlmostEqual(st["total_return"], -0.01)
        self.assertAlmostEqual(st["max_drawdown"], -0.10)
        self.assertEqual(st["max_price"], 111)
        self.assertEqual(st["min_price"], 98)
        self.assertAlmostEqual(st["annual_volatility"], st["daily_volatility"] * np.sqrt(252))

    def test_resample_weekly_ohlc_rules(self):
        df = fake_ohlcv(10)
        w = dp.resample_ohlcv(df, "W-FRI")
        first_week = df.iloc[:5]
        self.assertAlmostEqual(w.iloc[0]["Open"], first_week["Open"].iloc[0])
        self.assertAlmostEqual(w.iloc[0]["High"], first_week["High"].max())
        self.assertAlmostEqual(w.iloc[0]["Close"], first_week["Close"].iloc[-1])
        self.assertAlmostEqual(w.iloc[0]["Volume"], first_week["Volume"].sum())
        self.assertEqual(len(dp.resample_ohlcv(fake_ohlcv(300), "ME")), 14)

    def test_normalize_and_period_return(self):
        s = pd.Series([50.0, 55.0, 60.0])
        self.assertTrue(np.allclose(dp.normalize(s), [100.0, 110.0, 120.0]))
        self.assertAlmostEqual(dp.period_return(s, 1), 60 / 55 - 1)
        self.assertIsNone(dp.period_return(s, 5))

    def test_gbm_is_reproducible_and_shaped(self):
        a = dp.simulate_gbm(100, 0.08, 0.2, 50, 10, seed=7)
        b = dp.simulate_gbm(100, 0.08, 0.2, 50, 10, seed=7)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(a.shape, (51, 10))
        self.assertTrue((a.iloc[0] == 100).all())
        self.assertTrue((a > 0).all().all())
        zero_vol = dp.simulate_gbm(100, 0.10, 0.0, 252, 1, seed=1)
        self.assertAlmostEqual(zero_vol.iloc[-1, 0], 100 * np.exp(0.10), places=6)


if __name__ == "__main__":
    unittest.main()
