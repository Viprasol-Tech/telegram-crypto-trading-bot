from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.paper import (
    InsufficientFundsError,
    InsufficientPositionError,
    PaperAccount,
)


def test_buy_debits_cash_and_adds_position() -> None:
    acc = PaperAccount(cash=1_000.0)
    cost = acc.buy("BTC", 2.0, 100.0)
    assert cost == 200.0
    assert acc.cash == 800.0
    assert acc.position("BTC") == 2.0


def test_sell_credits_cash_and_reduces_position() -> None:
    acc = PaperAccount(cash=1_000.0)
    acc.buy("BTC", 2.0, 100.0)
    proceeds = acc.sell("BTC", 1.0, 150.0)
    assert proceeds == 150.0
    assert acc.cash == 950.0
    assert acc.position("BTC") == 1.0


def test_full_sell_clears_position() -> None:
    acc = PaperAccount(cash=1_000.0)
    acc.buy("eth", 3.0, 50.0)
    acc.sell("ETH", 3.0, 50.0)
    assert acc.position("ETH") == 0.0
    assert acc.positions == {}


def test_buy_beyond_cash_raises() -> None:
    acc = PaperAccount(cash=100.0)
    with pytest.raises(InsufficientFundsError):
        acc.buy("BTC", 2.0, 100.0)


def test_sell_beyond_holdings_raises() -> None:
    acc = PaperAccount(cash=1_000.0)
    acc.buy("BTC", 1.0, 100.0)
    with pytest.raises(InsufficientPositionError):
        acc.sell("BTC", 2.0, 100.0)


def test_equity_marks_positions() -> None:
    acc = PaperAccount(cash=500.0)
    acc.buy("BTC", 2.0, 100.0)  # cash now 300, holds 2 BTC
    assert acc.equity({"BTC": 120.0}) == 300.0 + 240.0


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_positive_quantity_rejected(bad: float) -> None:
    acc = PaperAccount(cash=1_000.0)
    with pytest.raises(ValueError):
        acc.buy("BTC", bad, 100.0)
