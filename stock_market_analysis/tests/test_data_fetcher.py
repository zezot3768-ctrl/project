import unittest
from datetime import datetime, timezone
from unittest import mock

import pandas as pd
import requests

from modules import data_fetcher as df_
from modules.data_fetcher import AlphaVantageProvider, DataCategory, MarketData, Quote, RateLimiter
from modules.errors import DataError, ProviderConfigError, RateLimitError
from tests.helpers import fake_ohlcv


class FakeProvider(df_.BaseProvider):
    """A stand-in provider for tests. It can be told to fail."""
    key, label = "fake", "Fake test provider"

    def __init__(self):
        self.fail = False
        self.calls = 0

    def _maybe_fail(self):
        self.calls += 1
        if self.fail:
            raise requests.exceptions.ConnectionError("boom")

    def get_history(self, symbol, period="1y"):
        self._maybe_fail()
        return fake_ohlcv(60)

    def get_quote(self, symbol):
        self._maybe_fail()
        return Quote(symbol, symbol, 101.0, 100.0, 10.0, None, datetime(2024, 1, 2), "fake", DataCategory.HISTORICAL)

    def get_fundamentals(self, symbol):
        self._maybe_fail()
        return {"market_cap": 1.0}


class ServiceTests(unittest.TestCase):
    def test_caching_avoids_second_request(self):
        p = FakeProvider(); svc = MarketData(p)
        svc.quote("AAPL"); svc.quote("AAPL")
        self.assertEqual(p.calls, 1)
        svc.quote("AAPL", force=True)
        self.assertEqual(p.calls, 2)

    def test_failure_returns_stale_then_error(self):
        p = FakeProvider(); svc = MarketData(p)
        self.assertTrue(svc.quote("AAPL").ok)
        p.fail = True
        stale = svc.quote("AAPL", force=True)
        self.assertTrue(stale.ok and stale.stale)
        self.assertIn("Could not reach", stale.message)
        nodata = svc.quote("MSFT")
        self.assertFalse(nodata.ok)
        self.assertIsNone(nodata.data)

    def test_invalid_symbol_is_rejected_without_request(self):
        p = FakeProvider(); svc = MarketData(p)
        res = svc.quote("DROP TABLE;")
        self.assertFalse(res.ok)
        self.assertEqual(p.calls, 0)

    def test_history_is_cleaned_and_clear_quotes(self):
        p = FakeProvider(); svc = MarketData(p)
        h = svc.history("AAPL", "1y")
        self.assertTrue(h.ok and "Close" in h.data.columns)
        svc.quote("AAPL"); svc.clear_quotes(); svc.quote("AAPL")
        self.assertEqual(p.calls, 3)   # history + quote + quote again
        self.assertIsNotNone(svc.last_success())

    def test_rate_limiter(self):
        rl = RateLimiter(2, 60)
        rl.check(); rl.check()
        with self.assertRaises(RateLimitError):
            rl.check()

    def test_quotes_to_frame_skips_failures(self):
        p = FakeProvider(); svc = MarketData(p)
        ok = svc.quote("AAPL")
        res = {"AAPL": ok, "BAD": df_.FetchResult(message="x")}
        frame = df_.quotes_to_frame(res)
        self.assertEqual(list(frame["Symbol"]), ["AAPL"])
        self.assertAlmostEqual(frame.iloc[0]["Change %"], 1.0)


class AlphaVantageTests(unittest.TestCase):
    """Uses the documented Alpha Vantage JSON layout with a mocked HTTP call (no internet)."""

    def _provider(self, payload):
        p = AlphaVantageProvider("demo-key")
        resp = mock.Mock(); resp.raise_for_status = lambda: None; resp.json = lambda: payload
        return p, mock.patch("modules.data_fetcher.requests.get", return_value=resp)

    def test_missing_key_is_a_config_error(self):
        with self.assertRaises(ProviderConfigError):
            AlphaVantageProvider(None)

    def test_history_parsing(self):
        payload = {"Time Series (Daily)": {
            "2024-01-03": {"1. open": "11", "2. high": "12", "3. low": "10", "4. close": "11.5", "5. volume": "200"},
            "2024-01-02": {"1. open": "10", "2. high": "11", "3. low": "9", "4. close": "10.5", "5. volume": "100"}}}
        p, patcher = self._provider(payload)
        with patcher:
            out = p.get_history("AAPL", "1mo")
        self.assertEqual(list(out["Close"]), [10.5, 11.5])
        self.assertTrue(out.index.is_monotonic_increasing)

    def test_quote_parsing(self):
        payload = {"Global Quote": {"05. price": "190.50", "06. volume": "1000", "07. latest trading day": "2024-01-02", "08. previous close": "189.00"}}
        p, patcher = self._provider(payload)
        with patcher:
            q = p.get_quote("AAPL")
        self.assertAlmostEqual(q.price, 190.5)
        self.assertAlmostEqual(q.change, 1.5)
        self.assertIsNone(q.market_cap)

    def test_limit_message_becomes_rate_limit_error(self):
        p, patcher = self._provider({"Information": "Thank you... our standard API rate limit is 25 requests per day."})
        with patcher, self.assertRaises(RateLimitError):
            p.get_quote("AAPL")

    def test_error_message_becomes_data_error(self):
        p, patcher = self._provider({"Error Message": "Invalid API call."})
        with patcher, self.assertRaises(DataError):
            p.get_history("ZZZZ")


class MarketStatusTests(unittest.TestCase):
    def test_weekend_hours_and_holiday(self):
        sat = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(df_.market_status(None, sat)[0], False)
        mon_open = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)      # 10:00 New York
        self.assertTrue(df_.market_status(None, mon_open)[0])
        self.assertTrue(df_.market_status(mon_open.date(), mon_open)[0])
        self.assertFalse(df_.market_status(datetime(2026, 11, 20).date(), mon_open)[0])  # stale bar -> holiday
        night = datetime(2026, 11, 23, 23, 0, tzinfo=timezone.utc)
        self.assertFalse(df_.market_status(None, night)[0])

    def test_symbol_validation(self):
        self.assertEqual(df_.normalize_symbol(" aapl "), "AAPL")
        self.assertEqual(df_.normalize_symbol("^gspc"), "^GSPC")
        with self.assertRaises(DataError):
            df_.normalize_symbol("not a ticker")


if __name__ == "__main__":
    unittest.main()
