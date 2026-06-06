from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.commands import Side, Trade
from telegram_crypto_trading_bot.paper import PaperAccount
from telegram_crypto_trading_bot.risk import RiskLimits, check_trade


def _buy(symbol: str = "BTC", qty: float = 1.0) -> Trade:
    return Trade(side=Side.BUY, symbol=symbol, quantity=qty)


def _sell(symbol: str = "BTC", qty: float = 1.0) -> Trade:
    return Trade(side=Side.SELL, symbol=symbol, quantity=qty)


def test_unlimited_allows_everything() -> None:
    acc = PaperAccount(cash=100.0)
    decision = check_trade(_buy(qty=10.0), 50.0, acc, RiskLimits.unlimited())
    assert decision.allowed


def test_sells_are_always_allowed() -> None:
    acc = PaperAccount(cash=0.0)
    limits = RiskLimits(max_order_notional=1.0, min_cash_reserve=1_000.0)
    assert check_trade(_sell(qty=5.0), 100.0, acc, limits).allowed


def test_max_order_notional_blocks_large_order() -> None:
    acc = PaperAccount(cash=10_000.0)
    limits = RiskLimits(max_order_notional=150.0)
    decision = check_trade(_buy(qty=2.0), 100.0, acc, limits)  # notional 200
    assert not decision.allowed
    assert "order notional" in decision.reason


def test_max_order_notional_allows_at_boundary() -> None:
    acc = PaperAccount(cash=10_000.0)
    limits = RiskLimits(max_order_notional=200.0)
    assert check_trade(_buy(qty=2.0), 100.0, acc, limits).allowed


def test_max_position_notional_accounts_for_existing_holdings() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)  # existing 100 notional
    limits = RiskLimits(max_position_notional=150.0)
    decision = check_trade(_buy(qty=1.0), 100.0, acc, limits)  # would be 200
    assert not decision.allowed
    assert "position notional" in decision.reason


def test_max_open_positions_blocks_new_symbol() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)
    limits = RiskLimits(max_open_positions=1)
    decision = check_trade(_buy("ETH", 1.0), 50.0, acc, limits)
    assert not decision.allowed
    assert "max open positions" in decision.reason


def test_max_open_positions_allows_adding_to_existing_symbol() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)
    limits = RiskLimits(max_open_positions=1)
    assert check_trade(_buy("BTC", 1.0), 100.0, acc, limits).allowed


def test_min_cash_reserve_blocks_breaching_buy() -> None:
    acc = PaperAccount(cash=1_000.0)
    limits = RiskLimits(min_cash_reserve=900.0)
    decision = check_trade(_buy(qty=2.0), 100.0, acc, limits)  # cash after 800
    assert not decision.allowed
    assert "reserve" in decision.reason


def test_min_cash_reserve_allows_when_safe() -> None:
    acc = PaperAccount(cash=1_000.0)
    limits = RiskLimits(min_cash_reserve=700.0)
    assert check_trade(_buy(qty=2.0), 100.0, acc, limits).allowed


def test_describe_lists_all_configured_limits() -> None:
    limits = RiskLimits(
        max_order_notional=1_000.0,
        max_position_notional=5_000.0,
        max_open_positions=3,
        min_cash_reserve=500.0,
    )
    lines = limits.describe()
    assert len(lines) == 4
    assert any("Max order notional" in line for line in lines)


def test_describe_unlimited_says_so() -> None:
    assert "unlimited" in RiskLimits.unlimited().describe()[0].lower()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_order_notional": 0},
        {"max_order_notional": -1},
        {"max_open_positions": 0},
        {"min_cash_reserve": -1},
    ],
)
def test_invalid_limits_rejected_on_construction(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        RiskLimits(**kwargs)
