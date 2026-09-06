"""Fast offline smoke tests for the BioTrader demo engine."""

import os
import unittest

os.environ["BIO_TRADER_OFFLINE"] = "1"

from biotrader import BioTradingEngine, DemoPortfolio


class BioTraderSmokeTests(unittest.TestCase):
    def test_seeded_engine_has_five_demo_positions(self) -> None:
        engine = BioTradingEngine()
        snapshot = engine.snapshot()
        self.assertEqual(snapshot["mode"], "simulation")
        self.assertEqual(len(snapshot["candidates"]), 24)
        self.assertEqual(len(snapshot["positions"]), 5)
        self.assertEqual(snapshot["summary"]["used_margin"], 500.0)
        self.assertEqual(snapshot["summary"]["leverage"], 15)

    def test_repeated_scan_keeps_slot_count_and_records_equity(self) -> None:
        engine = BioTradingEngine()
        first = engine.snapshot()
        second = engine.scan(force=True, prefer_live=False)
        self.assertEqual(len(second["positions"]), 5)
        self.assertGreaterEqual(len(second["equity_curve"]), len(first["equity_curve"]))
        for position in second["positions"]:
            self.assertAlmostEqual(position["margin"], 100.0, places=6)
            self.assertAlmostEqual(position["notional"], 1500.0, places=5)

    def test_portfolio_reset_is_recoverable(self) -> None:
        portfolio = DemoPortfolio()
        portfolio.total_entries = 7
        portfolio.balance = 421.0
        portfolio.reset()
        self.assertEqual(portfolio.balance, 500.0)
        self.assertEqual(portfolio.total_entries, 0)
        self.assertEqual(portfolio.fees_paid, 0.0)


if __name__ == "__main__":
    unittest.main()
