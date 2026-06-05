from __future__ import annotations

from telegram_crypto_trading_bot.bot import (
    Dispatcher,
    InMemoryTransport,
    StaticPriceSource,
    run_once,
)
from telegram_crypto_trading_bot.commands import Trade, parse_command
from telegram_crypto_trading_bot.paper import PaperAccount


def _dispatcher(cash: float = 10_000.0) -> Dispatcher:
    prices = StaticPriceSource({"BTC": 100.0})
    return Dispatcher(PaperAccount(cash=cash), prices)


def test_dispatch_buy_then_balance_reflects_it() -> None:
    disp = _dispatcher(cash=1_000.0)

    buy_reply = disp.dispatch(parse_command("/buy BTC 2"))
    assert "BOUGHT" in buy_reply
    assert disp.account.cash == 800.0
    assert disp.account.position("BTC") == 2.0

    balance_reply = disp.dispatch(parse_command("/balance"))
    assert "800.00" in balance_reply
    assert "BTC 2" in balance_reply


def test_price_query() -> None:
    disp = _dispatcher()
    assert disp.handle_text("/price BTC") == "BTC = 100.00"


def test_handle_text_wraps_parse_error() -> None:
    disp = _dispatcher()
    reply = disp.handle_text("/buy BTC")
    assert reply.startswith("ERROR:")


def test_handle_text_wraps_unknown_symbol_price() -> None:
    disp = _dispatcher()
    reply = disp.handle_text("/price XRP")
    assert reply.startswith("ERROR:")


def test_handle_text_wraps_insufficient_funds() -> None:
    disp = _dispatcher(cash=10.0)
    reply = disp.handle_text("/buy BTC 5")
    assert reply.startswith("ERROR:")


def test_run_once_drains_transport_and_sends_replies() -> None:
    disp = _dispatcher(cash=1_000.0)
    transport = InMemoryTransport(inbound=["/buy BTC 1", "/balance"])

    replies = run_once(disp, transport)

    assert len(replies) == 2
    assert transport.outbound == replies
    assert transport.receive() == []  # drained
    assert "BTC 1" in replies[1]


def test_parse_then_dispatch_roundtrip_sell() -> None:
    disp = _dispatcher(cash=1_000.0)
    disp.dispatch(parse_command("/buy BTC 3"))
    cmd = parse_command("/sell BTC 1")
    assert isinstance(cmd, Trade)
    reply = disp.dispatch(cmd)
    assert "SOLD" in reply
    assert disp.account.position("BTC") == 2.0
