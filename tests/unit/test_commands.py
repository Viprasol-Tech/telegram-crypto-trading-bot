from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.commands import (
    Balance,
    CommandError,
    Help,
    History,
    Pnl,
    Positions,
    Price,
    ShowPortfolio,
    ShowRisk,
    Side,
    Trade,
    parse_command,
)


def test_parse_buy() -> None:
    cmd = parse_command("/buy BTC 0.5")
    assert isinstance(cmd, Trade)
    assert cmd.side is Side.BUY
    assert cmd.symbol == "BTC"
    assert cmd.quantity == 0.5


def test_parse_sell_lowercase_symbol_is_normalized() -> None:
    cmd = parse_command("/sell eth 2")
    assert isinstance(cmd, Trade)
    assert cmd.side is Side.SELL
    assert cmd.symbol == "ETH"
    assert cmd.quantity == 2.0


def test_parse_balance() -> None:
    assert isinstance(parse_command("/balance"), Balance)


def test_parse_price() -> None:
    cmd = parse_command("/price BTC")
    assert isinstance(cmd, Price)
    assert cmd.symbol == "BTC"


def test_parse_positions_and_alias() -> None:
    assert isinstance(parse_command("/positions"), Positions)
    assert isinstance(parse_command("/pos"), Positions)


def test_parse_portfolio_and_alias() -> None:
    assert isinstance(parse_command("/portfolio"), ShowPortfolio)
    assert isinstance(parse_command("/port"), ShowPortfolio)


def test_parse_pnl() -> None:
    assert isinstance(parse_command("/pnl"), Pnl)


def test_parse_risk() -> None:
    assert isinstance(parse_command("/risk"), ShowRisk)


def test_parse_help_and_start_alias() -> None:
    assert isinstance(parse_command("/help"), Help)
    assert isinstance(parse_command("/start"), Help)


def test_parse_history_without_limit() -> None:
    cmd = parse_command("/history")
    assert isinstance(cmd, History)
    assert cmd.limit is None


def test_parse_history_with_limit() -> None:
    cmd = parse_command("/history 5")
    assert isinstance(cmd, History)
    assert cmd.limit == 5


def test_leading_slash_is_optional_and_whitespace_trimmed() -> None:
    cmd = parse_command("  buy  BTC  1  ")
    assert isinstance(cmd, Trade)
    assert cmd.quantity == 1.0


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "/unknown BTC 1",
        "/buy BTC",
        "/buy BTC 1 2",
        "/buy BTC abc",
        "/buy BTC 0",
        "/buy BTC -1",
        "/buy BT-C 1",
        "/buy BTC inf",
        "/buy BTC nan",
        "/price",
        "/price BTC ETH",
        "/balance now",
        "/positions extra",
        "/pnl now",
        "/risk now",
        "/portfolio x",
        "/history 0",
        "/history -1",
        "/history abc",
        "/history 1 2",
    ],
)
def test_malformed_raises(text: str) -> None:
    with pytest.raises(CommandError):
        parse_command(text)
