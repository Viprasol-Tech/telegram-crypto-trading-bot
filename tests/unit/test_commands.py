from __future__ import annotations

import pytest

from telegram_crypto_trading_bot.commands import (
    Balance,
    CommandError,
    Price,
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
        "/price",
        "/price BTC ETH",
        "/balance now",
    ],
)
def test_malformed_raises(text: str) -> None:
    with pytest.raises(CommandError):
        parse_command(text)
