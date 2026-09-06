"""Fast offline smoke tests for the upgraded BioTrader engine."""

import os
import tempfile
import unittest
from datetime import timedelta

os.environ["BIO_TRADER_OFFLINE"] = "1"

from bio_memory import BioMemory
from biotrader import (
    DemoPortfolio,
    RiskConfig,
    RiskManager,
    UltimateBioOrganism,
    evaluate_entry_gate,
    utc_now,
)
from biotrader import BioTradingEngine


def make_decision(**overrides):
    base = {
        "symbol": "TESTUSDT",
        "side": "LONG",
        "entry": 100.0,
        "ask": 100.05,
        "bid": 99.95,
        "last_price": 100.0,
        "tp": 103.0,
        "sl": 98.0,
        "stop_distance": 2.0,
        "reward_multiple": 1.5,
        "confidence": 0.8,
        "quality": 80.0,
        "consensus": 0.7,
        "signal": 0.55,
        "spread_bps": 5.0,
        "atr": 1.4,
        "atr_pct": 0.004,
        "htf_agree": 0.6,
        "regime": "TREND",
    }
    base.update(overrides)
    return base


class BioTraderSmokeTests(unittest.TestCase):
    def test_seeded_engine_has_five_demo_positions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = BioTradingEngine(os.path.join(temp_dir, "bio.sqlite"))
            snapshot = engine.snapshot()
            engine.memory.close()
        self.assertEqual(snapshot["mode"], "simulation")
        self.assertEqual(len(snapshot["candidates"]), 24)
        self.assertEqual(len(snapshot["positions"]), 5)
        # Bootstrap skips the sniper gate but NOT risk-based sizing: every
        # slot respects per-trade caps and the total must fit the book.
        cfg = engine.portfolio.risk.config
        used = sum(p["margin"] for p in snapshot["positions"])
        for position in snapshot["positions"]:
            self.assertGreaterEqual(position["margin"], cfg.min_margin_per_trade - 0.01)
            self.assertLessEqual(position["margin"], cfg.max_margin_per_trade + 0.01)
        self.assertGreaterEqual(used, 5 * cfg.min_margin_per_trade * 0.5)
        self.assertLessEqual(used, snapshot["summary"]["equity"] + 0.01)
        self.assertEqual(snapshot["summary"]["leverage"], 15)
        self.assertEqual(snapshot["organism"]["cortex"]["neuron_count"], 3072)

    def test_strict_scan_respects_slots_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = BioTradingEngine(os.path.join(temp_dir, "scan.sqlite"))
            first = engine.snapshot()
            second = engine.scan(force=True, prefer_live=False)
            engine.memory.close()
        self.assertLessEqual(len(second["positions"]), 5)
        self.assertGreaterEqual(len(second["equity_curve"]), len(first["equity_curve"]))
        cfg = engine.portfolio.risk.config
        for position in second["positions"]:
            self.assertGreaterEqual(position["margin"], cfg.min_margin_per_trade * 0.5)
            self.assertLessEqual(position["margin"], cfg.max_margin_per_trade + 1e-9)
            # Accounting edge case: after a partial take-profit the remaining
            # qty shrinks while the booked margin stays at its initial value,
            # and the last fill may be clamped to leftover cash.  The identity
            # therefore only bounds qty from above (full-size) and below.
            full_size_qty = position["margin"] * 15.0 / max(position["entry"], 1e-12)
            self.assertLessEqual(position["qty"], full_size_qty + 0.05)
            self.assertGreaterEqual(position["qty"], full_size_qty * 0.5 - 0.05)
        # Every candidate must carry an auditable sniper-gate verdict.
        for candidate in second["candidates"]:
            self.assertIn("gate", candidate)

    def test_portfolio_reset_is_recoverable(self) -> None:
        memory = BioMemory(":memory:")
        portfolio = DemoPortfolio(memory=memory)
        portfolio.total_entries = 7
        portfolio.balance = 421.0
        portfolio.reset()
        self.assertEqual(portfolio.balance, 500.0)
        self.assertEqual(portfolio.total_entries, 0)
        self.assertEqual(portfolio.fees_paid, 0.0)
        memory.close()

    def test_trade_journal_is_written_and_closed(self) -> None:
        memory = BioMemory(":memory:")
        portfolio = DemoPortfolio(memory=memory)
        portfolio.update([make_decision()], 72)
        self.assertEqual(len(memory.journal()), 1)
        portfolio.update([], 72)
        journal = memory.journal()
        self.assertEqual(journal[0]["status"], "CLOSED")
        self.assertIsNotNone(journal[0]["net_pnl"])
        memory.close()

    def test_sniper_gate_blocks_weak_and_passes_strong_setups(self) -> None:
        cfg = RiskConfig()
        weak = evaluate_entry_gate(make_decision(quality=30.0, confidence=0.2), cfg)
        self.assertFalse(weak["allowed"])
        self.assertTrue(weak["reasons"])

        wide_spread = evaluate_entry_gate(
            make_decision(spread_bps=40.0), cfg, market_allows=False
        )
        self.assertFalse(wide_spread["allowed"])

        strong = evaluate_entry_gate(make_decision(), cfg)
        self.assertTrue(strong["allowed"])
        self.assertGreater(strong["ev_r"], cfg.min_ev_r)

    def test_risk_manager_cooldown_after_loss_streak(self) -> None:
        manager = RiskManager(config=RiskConfig(loss_streak_limit=3, cooldown_minutes=30))
        for _ in range(3):
            manager.on_trade_closed(-4.0)
        allowed, reason = manager.trade_allowed()
        self.assertFalse(allowed)
        self.assertIn("خنک", reason)
        self.assertLessEqual(manager.sizing_multiplier(), 0.65)
        manager.cooldown_until = utc_now() - timedelta(seconds=1)
        allowed, _ = manager.trade_allowed()
        self.assertTrue(allowed)

    def test_risk_manager_daily_halt(self) -> None:
        manager = RiskManager(config=RiskConfig(daily_loss_limit_pct=3.0))
        manager.on_trade_closed(-10.0)
        manager.on_trade_closed(-8.0)
        allowed, reason = manager.trade_allowed()
        self.assertFalse(allowed)
        self.assertIn("روزانه", reason)

    def test_drawdown_kill_switch_disarms_entries(self) -> None:
        manager = RiskManager(config=RiskConfig(hard_drawdown_pct=9.0))
        manager.begin_scan(500.0)
        manager.update_equity(440.0)  # -12% from peak
        allowed, reason = manager.trade_allowed()
        self.assertFalse(allowed)
        self.assertIn("کیل", reason)
        self.assertLessEqual(manager.sizing_multiplier(), 0.5)

    def test_partial_take_profit_banks_half_and_moves_stop(self) -> None:
        memory = BioMemory(":memory:")
        portfolio = DemoPortfolio(memory=memory)
        portfolio.update([make_decision()], 72)
        symbol = next(iter(portfolio.positions))
        position = portfolio.positions[symbol]
        balance_before = portfolio.balance
        qty_before = position.qty
        # Push mark to +1.4R (stop distance is 2.0 -> move of 2.8).
        runner = make_decision(symbol=symbol, side="LONG", ask=102.85, bid=102.75, last_price=102.8)
        reason = portfolio._manage(symbol, runner)
        self.assertIsNone(reason)
        self.assertTrue(position.partial_taken)
        self.assertAlmostEqual(position.qty, qty_before * 0.5, places=8)
        self.assertGreater(position.sl, position.entry)
        self.assertGreater(portfolio.balance, balance_before)
        # Chandelier trail must never loosen the protective stop afterwards.
        sl_after_partial = position.sl
        pullback = make_decision(symbol=symbol, side="LONG", ask=101.9, bid=101.8, last_price=101.85, atr=1.0)
        portfolio._manage(symbol, pullback)
        self.assertGreaterEqual(position.sl, sl_after_partial)
        memory.close()

    def test_time_stop_retires_tired_scalps(self) -> None:
        memory = BioMemory(":memory:")
        portfolio = DemoPortfolio(memory=memory)
        portfolio.update([make_decision()], 72)
        symbol = next(iter(portfolio.positions))
        position = portfolio.positions[symbol]
        position.opened_dt = utc_now() - timedelta(hours=5)
        stale = make_decision(symbol=symbol, side="LONG", ask=100.02, bid=99.98, last_price=100.0)
        reason = portfolio._manage(symbol, stale)
        self.assertIsNotNone(reason)
        self.assertIn("زمان", reason)
        memory.close()

    def test_genome_mutations_resume_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "genome.sqlite")
            first_memory = BioMemory(path)
            first = UltimateBioOrganism(memory=first_memory)
            before = first.genome["retina"].mutation
            first.learn(18.0, "unit-test")
            after = first.genome["retina"].mutation
            first_memory.close()
            second_memory = BioMemory(path)
            second = UltimateBioOrganism(memory=second_memory)
            self.assertNotEqual(before, after)
            self.assertAlmostEqual(second.genome["retina"].mutation, after, places=7)
            self.assertGreaterEqual(second.generation, 1)
            self.assertGreaterEqual(len(second.memory.mutation_history()), 1)
            second_memory.close()

    def test_calibration_talks_overconfident_model_down(self) -> None:
        memory = BioMemory(":memory:")
        organism = UltimateBioOrganism(memory=memory)
        trades = [
            {"realized_pnl": -3.0, "regime": "RANGE", "confidence": 0.8} for _ in range(12)
        ]
        for trade in trades:
            fake_position = type(
                "FakePosition",
                (),
                {
                    "symbol": "XUSDT",
                    "side": "LONG",
                    "entry": 100.0,
                    "mark": 99.0,
                    "tp": 103.0,
                    "sl": 98.0,
                    "margin": 50.0,
                    "leverage": 15,
                    "qty": 7.5,
                    "confidence": trade["confidence"],
                    "quality": 60.0,
                    "regime": trade["regime"],
                    "heartbeat_at_open": 72,
                    "opened_at": utc_now().isoformat(),
                    "entry_fee": 0.0,
                    "entry_spread_cost": 0.0,
                },
            )()
            memory.record_close(
                None,
                fake_position,
                gross_pnl=trade["realized_pnl"],
                exit_fee=0.0,
                net_pnl=trade["realized_pnl"],
                reason="unit-test",
            )
        organism.learn_stats(trades)
        # A model promising ~80% confidence while losing everything must be
        # talked down below its starting calibration.
        self.assertLess(organism.calibration, 1.0)
        self.assertGreaterEqual(organism.regime_stats["RANGE"]["n"], 12.0)
        memory.close()


if __name__ == "__main__":
    unittest.main()
