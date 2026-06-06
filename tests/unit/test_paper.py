from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.commands import Side
from telegram_crypto_trading_bot.paper import (
    InsufficientFundsError,
    InsufficientPositionError,
    PaperAccount,
    build_portfolio,
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


def test_sell_with_no_position_raises() -> None:
    acc = PaperAccount(cash=1_000.0)
    with pytest.raises(InsufficientPositionError):
        acc.sell("BTC", 1.0, 100.0)


def test_equity_marks_positions() -> None:
    acc = PaperAccount(cash=500.0)
    acc.buy("BTC", 2.0, 100.0)  # cash now 300, holds 2 BTC
    assert acc.equity({"BTC": 120.0}) == 300.0 + 240.0


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_positive_quantity_rejected(bad: float) -> None:
    acc = PaperAccount(cash=1_000.0)
    with pytest.raises(ValueError):
        acc.buy("BTC", bad, 100.0)


def test_negative_starting_cash_rejected() -> None:
    with pytest.raises(ValueError):
        PaperAccount(cash=-1.0)


def test_buy_at_non_positive_price_rejected() -> None:
    acc = PaperAccount(cash=1_000.0)
    with pytest.raises(ValueError):
        acc.buy("BTC", 1.0, 0.0)


def test_average_cost_basis_blends_on_multiple_buys() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)
    acc.buy("BTC", 1.0, 200.0)
    assert acc.position("BTC") == 2.0
    assert acc.avg_price("BTC") == pytest.approx(150.0)


def test_realized_pnl_locked_in_on_sell() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 2.0, 100.0)  # avg 100
    acc.sell("BTC", 1.0, 150.0)  # realize +50
    assert acc.realized_pnl == pytest.approx(50.0)
    # remaining position keeps the original average cost
    assert acc.avg_price("BTC") == pytest.approx(100.0)


def test_unrealized_pnl_marks_to_market() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 2.0, 100.0)
    assert acc.unrealized_pnl({"BTC": 130.0}) == pytest.approx(60.0)
    assert acc.total_pnl({"BTC": 130.0}) == pytest.approx(60.0)


def test_unmarked_symbol_contributes_zero_unrealized() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)
    # no mark provided -> marked at avg cost -> zero unrealized
    assert acc.unrealized_pnl({}) == pytest.approx(0.0)


def test_fill_ledger_records_each_trade_with_sequence() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)
    acc.sell("BTC", 1.0, 120.0)
    fills = acc.fills
    assert [f.seq for f in fills] == [1, 2]
    assert fills[0].side is Side.BUY
    assert fills[0].cash_delta == pytest.approx(-100.0)
    assert fills[1].side is Side.SELL
    assert fills[1].cash_delta == pytest.approx(120.0)
    assert fills[1].realized_pnl == pytest.approx(20.0)
    assert fills[1].notional == pytest.approx(120.0)


def test_fills_returns_a_copy() -> None:
    acc = PaperAccount(cash=10_000.0)
    acc.buy("BTC", 1.0, 100.0)
    snapshot = acc.fills
    snapshot.clear()
    assert len(acc.fills) == 1


def test_build_portfolio_snapshot() -> None:
    acc = PaperAccount(cash=1_000.0)
    acc.buy("BTC", 2.0, 100.0)  # cash 800
    portfolio = build_portfolio(acc, {"BTC": 150.0})
    assert portfolio.cash == pytest.approx(800.0)
    assert portfolio.positions_value == pytest.approx(300.0)
    assert portfolio.equity == pytest.approx(1_100.0)
    assert portfolio.unrealized_pnl == pytest.approx(100.0)
    assert portfolio.starting_cash == pytest.approx(1_000.0)
    assert portfolio.total_return_pct == pytest.approx(10.0)
    (row,) = portfolio.rows
    assert row.symbol == "BTC"
    assert row.unrealized_pct == pytest.approx(50.0)


def test_empty_portfolio_has_no_rows() -> None:
    acc = PaperAccount(cash=500.0)
    portfolio = build_portfolio(acc, {})
    assert portfolio.rows == ()
    assert portfolio.equity == pytest.approx(500.0)
    assert portfolio.total_pnl == pytest.approx(0.0)
