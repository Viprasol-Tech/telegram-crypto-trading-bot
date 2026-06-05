"""Dispatcher + Telegram transport abstraction for the paper-trading bot.

:class:`Dispatcher` turns a parsed :class:`~telegram_crypto_trading_bot.commands.Command`
into a human-readable reply, executing trades against a :class:`PaperAccount`
and reading prices from a :class:`PriceSource`.

The Telegram transport is abstracted behind :class:`Transport` so the bot runs
and tests without a token; :class:`InMemoryTransport` is a fake for tests/demos.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from telegram_crypto_trading_bot.commands import (
    Balance,
    Command,
    CommandError,
    Price,
    Side,
    Trade,
    parse_command,
)
from telegram_crypto_trading_bot.paper import PaperAccount


@runtime_checkable
class PriceSource(Protocol):
    """Anything that can quote a current price for a symbol."""

    def get_price(self, symbol: str) -> float:
        """Return the current price for ``symbol``."""
        ...


class StaticPriceSource:
    """A :class:`PriceSource` backed by a fixed price table (for tests/demos).

    Args:
        prices: Mapping of symbol -> price. Symbols are matched case-insensitively.
    """

    def __init__(self, prices: Mapping[str, float]) -> None:
        self._prices = {sym.upper(): float(p) for sym, p in prices.items()}

    def get_price(self, symbol: str) -> float:
        """Return the configured price for ``symbol``.

        Raises:
            KeyError: If ``symbol`` is not in the price table.
        """
        key = symbol.upper()
        if key not in self._prices:
            raise KeyError(key)
        return self._prices[key]


@runtime_checkable
class Transport(Protocol):
    """A bidirectional message transport (e.g. a Telegram client)."""

    def receive(self) -> list[str]:
        """Return and consume any pending inbound message texts."""
        ...

    def send(self, text: str) -> None:
        """Deliver an outbound message ``text``."""
        ...


class InMemoryTransport:
    """An in-memory :class:`Transport` fake for tests and the CLI demo."""

    def __init__(self, inbound: list[str] | None = None) -> None:
        self.inbound: list[str] = list(inbound or [])
        self.outbound: list[str] = []

    def receive(self) -> list[str]:
        """Drain and return all queued inbound messages."""
        messages = list(self.inbound)
        self.inbound.clear()
        return messages

    def send(self, text: str) -> None:
        """Record an outbound message."""
        self.outbound.append(text)


class Dispatcher:
    """Executes parsed commands against an account and a price source.

    Args:
        account: The paper-trading account to mutate.
        prices: The price source used for trades and ``/price`` queries.
    """

    def __init__(self, account: PaperAccount, prices: PriceSource) -> None:
        self.account = account
        self.prices = prices

    def dispatch(self, command: Command) -> str:
        """Execute ``command`` and return a reply string.

        Args:
            command: A parsed command instance.

        Returns:
            A human-readable reply describing the result.
        """
        if isinstance(command, Trade):
            return self._handle_trade(command)
        if isinstance(command, Balance):
            return self._handle_balance()
        if isinstance(command, Price):
            return self._handle_price(command)
        return f"ERROR: unsupported command {type(command).__name__}"

    def handle_text(self, text: str) -> str:
        """Parse ``text`` and dispatch it, returning a reply.

        Parsing and execution errors are caught and rendered as ``ERROR: ...``
        replies so a single bad message never crashes the bot loop.

        Args:
            text: Raw inbound message text.

        Returns:
            A reply string (an ``ERROR:`` line on failure).
        """
        try:
            command = parse_command(text)
            return self.dispatch(command)
        except (CommandError, KeyError, ValueError) as exc:
            detail = exc.args[0] if exc.args else str(exc)
            return f"ERROR: {detail}"

    def _handle_trade(self, trade: Trade) -> str:
        price = self.prices.get_price(trade.symbol)
        if trade.side is Side.BUY:
            cost = self.account.buy(trade.symbol, trade.quantity, price)
            return (
                f"BOUGHT {trade.quantity:g} {trade.symbol} @ {price:.2f} "
                f"(cost {cost:.2f}); cash {self.account.cash:.2f}"
            )
        proceeds = self.account.sell(trade.symbol, trade.quantity, price)
        return (
            f"SOLD {trade.quantity:g} {trade.symbol} @ {price:.2f} "
            f"(proceeds {proceeds:.2f}); cash {self.account.cash:.2f}"
        )

    def _handle_balance(self) -> str:
        positions = self.account.positions
        if positions:
            holdings = ", ".join(f"{sym} {qty:g}" for sym, qty in sorted(positions.items()))
        else:
            holdings = "none"
        return f"Cash {self.account.cash:.2f} | Positions: {holdings}"

    def _handle_price(self, price: Price) -> str:
        quote = self.prices.get_price(price.symbol)
        return f"{price.symbol} = {quote:.2f}"


def run_once(dispatcher: Dispatcher, transport: Transport) -> list[str]:
    """Drain inbound messages, dispatch each, and send replies.

    Args:
        dispatcher: The command dispatcher.
        transport: The message transport to read from and write to.

    Returns:
        The list of reply strings that were sent, in order.
    """
    replies: list[str] = []
    for text in transport.receive():
        reply = dispatcher.handle_text(text)
        transport.send(reply)
        replies.append(reply)
    return replies
