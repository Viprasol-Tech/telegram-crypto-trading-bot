from __future__ import annotations

from telegram_crypto_trading_bot.bot import (
    Dispatcher,
    InMemoryTransport,
    StaticPriceSource,
    run_once,
)
from telegram_crypto_trading_bot.commands import Trade, parse_command
from telegram_crypto_trading_bot.paper import PaperAccount
from telegram_crypto_trading_bot.risk import RiskLimits


def _dispatcher(cash: float = 10_000.0, limits: RiskLimits | None = None) -> Dispatcher:
    prices = StaticPriceSource({"BTC": 100.0, "ETH": 50.0})
    return Dispatcher(PaperAccount(cash=cash), prices, limits=limits)


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


def test_positions_command_lists_cost_basis() -> None:
    disp = _dispatcher(cash=10_000.0)
    disp.handle_text("/buy BTC 2")
    reply = disp.handle_text("/positions")
    assert "BTC" in reply
    assert "avg 100.00" in reply


def test_positions_empty() -> None:
    disp = _dispatcher()
    assert "No open positions" in disp.handle_text("/positions")


def test_pnl_reports_realized_and_unrealized() -> None:
    disp = _dispatcher(cash=10_000.0)
    disp.handle_text("/buy BTC 2")  # avg 100
    disp.handle_text("/sell BTC 1")  # realized 0 at same price
    reply = disp.handle_text("/pnl")
    assert "realized" in reply
    assert "unrealized" in reply
    assert "total" in reply


def test_portfolio_shows_equity_and_pnl() -> None:
    disp = _dispatcher(cash=10_000.0)
    disp.handle_text("/buy BTC 2")
    reply = disp.handle_text("/portfolio")
    assert "Equity" in reply
    assert "Total PnL" in reply
    assert "BTC" in reply


def test_history_command_and_limit() -> None:
    disp = _dispatcher(cash=10_000.0)
    disp.handle_text("/buy BTC 1")
    disp.handle_text("/buy ETH 1")
    disp.handle_text("/sell BTC 1")
    full = disp.handle_text("/history")
    assert full.count("#") == 3
    limited = disp.handle_text("/history 1")
    assert limited.count("#") == 1
    assert "#3" in limited


def test_history_empty() -> None:
    disp = _dispatcher()
    assert "No trade history" in disp.handle_text("/history")


def test_risk_command_shows_limits_and_usage() -> None:
    limits = RiskLimits(max_open_positions=3, max_order_notional=5_000.0)
    disp = _dispatcher(cash=100_000.0, limits=limits)
    disp.handle_text("/buy BTC 1")
    reply = disp.handle_text("/risk")
    assert "Max open positions: 3" in reply
    assert "1/3 positions" in reply


def test_help_lists_commands() -> None:
    disp = _dispatcher()
    reply = disp.handle_text("/help")
    assert "/buy" in reply
    assert "/portfolio" in reply


def test_buy_rejected_by_risk_policy() -> None:
    limits = RiskLimits(max_order_notional=150.0)
    disp = _dispatcher(cash=10_000.0, limits=limits)
    reply = disp.handle_text("/buy BTC 2")  # notional 200 > 150
    assert reply.startswith("ERROR:")
    assert "risk policy" in reply
    assert disp.account.position("BTC") == 0.0


def test_callback_maps_button_to_command() -> None:
    disp = _dispatcher(cash=10_000.0)
    reply = disp.handle_callback("cmd:buy BTC 1")
    assert "BOUGHT" in reply
    assert disp.account.position("BTC") == 1.0


def test_callback_unknown_payload_is_error() -> None:
    disp = _dispatcher()
    assert disp.handle_callback("garbage").startswith("ERROR:")


def test_static_price_source_snapshot() -> None:
    src = StaticPriceSource({"BTC": 100.0})
    assert src.snapshot() == {"BTC": 100.0}
