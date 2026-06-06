from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.commands import Side
from telegram_crypto_trading_bot.paper import PaperAccount
from telegram_crypto_trading_bot.risk import RiskLimits
from telegram_crypto_trading_bot.strategy import (
    Signal,
    SmaCrossStrategy,
    StrategyRunner,
    ThresholdStrategy,
)


def test_signal_as_trade_roundtrip() -> None:
    sig = Signal(Side.BUY, "BTC", 1.5, reason="x")
    trade = sig.as_trade()
    assert trade.side is Side.BUY
    assert trade.symbol == "BTC"
    assert trade.quantity == 1.5


def test_threshold_buys_below_floor() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    signals = strat.generate({"BTC": 85.0}, acc)
    assert len(signals) == 1
    assert signals[0].side is Side.BUY


def test_threshold_no_signal_in_band() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    assert strat.generate({"BTC": 100.0}, acc) == []


def test_threshold_sells_above_ceiling_only_when_holding() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=2.0)
    acc = PaperAccount(cash=10_000.0)
    assert strat.generate({"BTC": 120.0}, acc) == []  # nothing held
    acc.buy("BTC", 1.0, 100.0)
    signals = strat.generate({"BTC": 120.0}, acc)
    assert signals[0].side is Side.SELL
    assert signals[0].quantity == 1.0  # capped at holdings


def test_threshold_ignores_unrelated_symbol() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    assert strat.generate({"ETH": 1.0}, acc) == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"buy_below": 100.0, "sell_above": 90.0, "quantity": 1.0},
        {"buy_below": 90.0, "sell_above": 110.0, "quantity": 0.0},
    ],
)
def test_threshold_invalid_config(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        ThresholdStrategy("BTC", **kwargs)


def test_sma_cross_needs_full_window_before_signalling() -> None:
    strat = SmaCrossStrategy("BTC", fast=2, slow=4, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    assert strat.generate({"BTC": 100.0}, acc) == []
    assert strat.generate({"BTC": 101.0}, acc) == []
    assert strat.generate({"BTC": 102.0}, acc) == []  # still < slow window


def test_sma_cross_emits_buy_on_upward_cross() -> None:
    strat = SmaCrossStrategy("BTC", fast=2, slow=4, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    buys = 0
    for price in [100.0, 98.0, 96.0, 94.0, 110.0, 120.0]:
        for sig in strat.generate({"BTC": price}, acc):
            if sig.side is Side.BUY:
                buys += 1
    assert buys >= 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fast": 0, "slow": 4, "quantity": 1.0},
        {"fast": 4, "slow": 4, "quantity": 1.0},
        {"fast": 2, "slow": 4, "quantity": 0.0},
    ],
)
def test_sma_invalid_config(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        SmaCrossStrategy("BTC", **kwargs)


def test_runner_executes_buy_signal() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    runner = StrategyRunner(strat, acc)
    results = runner.step({"BTC": 85.0})
    assert results[0].executed
    assert acc.position("BTC") == 1.0


def test_runner_blocks_signal_violating_risk() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=10.0)
    acc = PaperAccount(cash=10_000.0)
    runner = StrategyRunner(strat, acc, limits=RiskLimits(max_order_notional=100.0))
    results = runner.step({"BTC": 85.0})  # notional 850 > 100
    assert not results[0].executed
    assert "risk" in results[0].detail
    assert acc.position("BTC") == 0.0


def test_runner_reports_missing_price() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    runner = StrategyRunner(strat, acc)
    # generate sees BTC, but if a signal references an unpriced symbol it is reported
    sig = Signal(Side.BUY, "ETH", 1.0)
    res = runner._execute(sig, {"BTC": 100.0})
    assert not res.executed
    assert "no price" in res.detail


def test_runner_handles_insufficient_funds_gracefully() -> None:
    strat = ThresholdStrategy("BTC", buy_below=90.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10.0)
    runner = StrategyRunner(strat, acc)
    results = runner.step({"BTC": 85.0})
    assert not results[0].executed
    assert "error" in results[0].detail


def test_runner_run_replays_history() -> None:
    strat = ThresholdStrategy("BTC", buy_below=95.0, sell_above=110.0, quantity=1.0)
    acc = PaperAccount(cash=10_000.0)
    runner = StrategyRunner(strat, acc)
    history = [{"BTC": 90.0}, {"BTC": 92.0}, {"BTC": 115.0}]
    results = runner.run(history)
    executed = [r for r in results if r.executed]
    assert len(executed) >= 2  # two buys then a sell
    assert acc.realized_pnl != 0.0
