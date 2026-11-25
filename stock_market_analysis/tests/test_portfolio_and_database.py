import os
import tempfile
import unittest

import pandas as pd

from modules import database as db
from modules.constants import START_CASH
from modules.portfolio import ReplaySession, compute_holdings, portfolio_summary, validate_trade


def tx(side, symbol, shares, price):
    return {"side": side, "symbol": symbol, "shares": shares, "price": price}


class PortfolioTests(unittest.TestCase):
    def test_average_cost_and_sell(self):
        h = compute_holdings([tx("BUY", "AAPL", 10, 100), tx("BUY", "AAPL", 10, 120), tx("SELL", "AAPL", 5, 150)])
        self.assertEqual(h["AAPL"].shares, 15)
        self.assertAlmostEqual(h["AAPL"].avg_cost, 110.0)

    def test_selling_everything_removes_holding(self):
        self.assertEqual(compute_holdings([tx("BUY", "X", 3, 10), tx("SELL", "X", 3, 12)]), {})

    def test_validation_rules(self):
        h = compute_holdings([tx("BUY", "AAPL", 5, 100)])
        self.assertFalse(validate_trade(100, h, "BUY", "AAPL", 2, 100)[0])      # not enough cash
        self.assertTrue(validate_trade(200, h, "BUY", "AAPL", 2, 100)[0])
        self.assertFalse(validate_trade(0, h, "SELL", "AAPL", 6, 100)[0])       # more than owned
        self.assertFalse(validate_trade(0, h, "SELL", "NVDA", 1, 100)[0])       # not owned
        self.assertFalse(validate_trade(500, h, "BUY", "AAPL", 0, 100)[0])      # zero shares
        self.assertFalse(validate_trade(500, h, "BUY", "AAPL", 1.5, 100)[0])    # fractional
        self.assertFalse(validate_trade(500, h, "BUY", "AAPL", 1, float("nan"))[0])

    def test_summary_numbers(self):
        h = compute_holdings([tx("BUY", "AAPL", 10, 100)])
        s = portfolio_summary(9000, h, {"AAPL": 110})
        self.assertAlmostEqual(s["total_value"], 10100)
        self.assertAlmostEqual(s["unrealized_pl"], 100)
        self.assertAlmostEqual(s["total_pl"], 100)
        self.assertEqual(s["missing_prices"], [])
        self.assertEqual(portfolio_summary(9000, h, {})["missing_prices"], ["AAPL"])

    def test_replay_session(self):
        close = pd.Series([100.0, 110.0, 99.0, 120.0], index=pd.bdate_range("2024-01-01", periods=4))
        s = ReplaySession(close, "TEST")
        self.assertEqual(s.bh_shares, 100)
        ok, _ = s.trade("BUY", 50)                 # buy 50 at 100
        self.assertTrue(ok)
        self.assertFalse(s.trade("BUY", 100)[0])   # not enough cash
        s.step(); s.step()                         # price 99
        self.assertTrue(s.trade("SELL", 50)[0])
        self.assertFalse(s.trade("SELL", 1)[0])
        s.step()
        self.assertTrue(s.finished)
        self.assertFalse(s.step())
        r = s.result()
        self.assertAlmostEqual(r["portfolio_value"], 10000 - 50 + 0)   # bought at 100, sold at 99
        self.assertAlmostEqual(r["buy_hold_value"], 12000)
        self.assertFalse(r["beat_buy_hold"])
        self.assertEqual(len(s.history()), 4)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")

    def tearDown(self):
        self.dir.cleanup()

    def test_new_account_defaults(self):
        st = db.get_state("alice", self.path)
        self.assertEqual(st["cash"], START_CASH)
        self.assertEqual(db.get_watchlist("alice", self.path), ["AAPL", "NVDA"])

    def test_buy_sell_cycle_persists(self):
        self.assertTrue(db.execute_trade("bob", "AAPL", "BUY", 10, 150.0, "Delayed", self.path).ok)
        st = db.get_state("bob", self.path)
        self.assertAlmostEqual(st["cash"], 8500.0)
        self.assertTrue(db.execute_trade("bob", "AAPL", "SELL", 4, 160.0, "Delayed", self.path).ok)
        st = db.get_state("bob", self.path)
        self.assertAlmostEqual(st["cash"], 9140.0)
        self.assertAlmostEqual(st["realized_pl"], 40.0)
        self.assertEqual(len(st["transactions"]), 2)
        self.assertEqual(st["transactions"][0]["data_category"], "Delayed")

    def test_rejections_change_nothing(self):
        self.assertFalse(db.execute_trade("cy", "AAPL", "BUY", 1000, 150.0, "Delayed", self.path).ok)
        self.assertFalse(db.execute_trade("cy", "AAPL", "SELL", 1, 150.0, "Delayed", self.path).ok)
        st = db.get_state("cy", self.path)
        self.assertEqual(st["cash"], START_CASH)
        self.assertEqual(st["transactions"], [])

    def test_users_are_separate_and_reset_works(self):
        db.execute_trade("u1", "NVDA", "BUY", 1, 100.0, "Delayed", self.path)
        self.assertEqual(db.get_state("u2", self.path)["transactions"], [])
        db.reset_account("u1", self.path)
        st = db.get_state("u1", self.path)
        self.assertEqual((st["cash"], st["transactions"]), (START_CASH, []))

    def test_watchlist_add_remove_and_user_cleaning(self):
        db.add_to_watchlist("dee", "MSFT", self.path)
        db.add_to_watchlist("dee", "MSFT", self.path)  # duplicate ignored
        self.assertEqual(db.get_watchlist("dee", self.path).count("MSFT"), 1)
        db.remove_from_watchlist("dee", "AAPL", self.path)
        self.assertNotIn("AAPL", db.get_watchlist("dee", self.path))
        self.assertEqual(db.clean_user("  Bob; DROP TABLE--  "), "bobdroptable--")
        self.assertEqual(db.clean_user(""), "student")


if __name__ == "__main__":
    unittest.main()
