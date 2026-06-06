"""Dispatcher + Telegram transport abstraction for the paper-trading bot.

:class:`Dispatcher` turns a parsed :class:`~telegram_crypto_trading_bot.commands.Command`
into a human-readable reply, executing trades against a :class:`PaperAccount`,
reading prices from a :class:`PriceSource`, and enforcing a :class:`RiskLimits`
policy on every buy.

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
from telegram_crypto_trading_bot.keyboard import callback_text
from telegram_crypto_trading_bot.paper import (
    InsufficientFundsError,
    InsufficientPositionError,
    PaperAccount,
    build_portfolio,
)
from telegram_crypto_trading_bot.risk import RiskError, RiskLimits, check_trade


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

    def snapshot(self) -> dict[str, float]:
        """Return a copy of the full price table (symbol -> price)."""
        return dict(self._prices)


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
    """Executes parsed commands against an account, price source, and risk policy.

    Args:
        account: The paper-trading account to mutate.
        prices: The price source used for trades and reporting.
        limits: Risk policy enforced on every buy. Defaults to unlimited.
    """

    def __init__(
        self,
        account: PaperAccount,
        prices: PriceSource,
        limits: RiskLimits | None = None,
    ) -> None:
        self.account = account
        self.prices = prices
        self.limits = limits or RiskLimits.unlimited()

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
        if isinstance(command, Positions):
            return self._handle_positions()
        if isinstance(command, ShowPortfolio):
            return self._handle_portfolio()
        if isinstance(command, Pnl):
            return self._handle_pnl()
        if isinstance(command, History):
            return self._handle_history(command)
        if isinstance(command, ShowRisk):
            return self._handle_risk()
        if isinstance(command, Help):
            return self._handle_help()
        return f"ERROR: unsupported command {type(command).__name__}"

    def handle_text(self, text: str) -> str:
        """Parse ``text`` and dispatch it, returning a reply.

        Parsing, risk, and execution errors are caught and rendered as
        ``ERROR: ...`` replies so a single bad message never crashes the loop.

        Args:
            text: Raw inbound message text.

        Returns:
            A reply string (an ``ERROR:`` line on failure).
        """
        try:
            command = parse_command(text)
            return self.dispatch(command)
        except (CommandError, RiskError, KeyError, ValueError) as exc:
            detail = exc.args[0] if exc.args else str(exc)
            return f"ERROR: {detail}"

    def handle_callback(self, callback_data: str) -> str:
        """Handle an inline-keyboard tap by mapping it to a command.

        Args:
            callback_data: The opaque payload from a tapped button.

        Returns:
            The dispatched reply, or an ``ERROR:`` line on an unknown payload.
        """
        try:
            text = callback_text(callback_data)
        except ValueError as exc:
            return f"ERROR: {exc}"
        return self.handle_text(text)

    def _marks(self) -> dict[str, float]:
        """Best-effort mark prices for held symbols (avg cost if unquoted)."""
        marks: dict[str, float] = {}
        for sym, pos in self.account.open_positions.items():
            try:
                marks[sym] = self.prices.get_price(sym)
            except KeyError:
                marks[sym] = pos.avg_price
        return marks

    def _handle_trade(self, trade: Trade) -> str:
        price = self.prices.get_price(trade.symbol)
        decision = check_trade(trade, price, self.account, self.limits)
        if not decision.allowed:
            return f"ERROR: rejected by risk policy ({decision.reason})"
        if trade.side is Side.BUY:
            try:
                cost = self.account.buy(trade.symbol, trade.quantity, price)
            except InsufficientFundsError as exc:
                return f"ERROR: {exc}"
            return (
                f"BOUGHT {trade.quantity:g} {trade.symbol} @ {price:.2f} "
                f"(cost {cost:.2f}); cash {self.account.cash:.2f}"
            )
        try:
            proceeds = self.account.sell(trade.symbol, trade.quantity, price)
        except InsufficientPositionError as exc:
            return f"ERROR: {exc}"
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

    def _handle_positions(self) -> str:
        positions = self.account.open_positions
        if not positions:
            return "No open positions."
        lines = ["Open positions:"]
        for sym, pos in sorted(positions.items()):
            lines.append(
                f"  {sym}: {pos.quantity:g} @ avg {pos.avg_price:.2f} (basis {pos.cost_basis:.2f})"
            )
        return "\n".join(lines)

    def _handle_portfolio(self) -> str:
        portfolio = build_portfolio(self.account, self._marks())
        lines = [
            "Portfolio:",
            f"  Cash: {portfolio.cash:.2f}",
        ]
        for row in portfolio.rows:
            lines.append(
                f"  {row.symbol}: {row.quantity:g} @ {row.mark:.2f} "
                f"= {row.market_value:.2f} "
                f"(uPnL {row.unrealized_pnl:+.2f} / {row.unrealized_pct:+.2f}%)"
            )
        lines.append(f"  Equity: {portfolio.equity:.2f}")
        lines.append(
            f"  Total PnL: {portfolio.total_pnl:+.2f} ({portfolio.total_return_pct:+.2f}%)"
        )
        return "\n".join(lines)

    def _handle_pnl(self) -> str:
        marks = self._marks()
        realized = self.account.realized_pnl
        unrealized = self.account.unrealized_pnl(marks)
        total = realized + unrealized
        return f"PnL - realized {realized:+.2f} | unrealized {unrealized:+.2f} | total {total:+.2f}"

    def _handle_history(self, history: History) -> str:
        fills = self.account.fills
        if not fills:
            return "No trade history."
        if history.limit is not None:
            fills = fills[-history.limit :]
        lines = ["Trade history:"]
        for fill in fills:
            verb = fill.side.value.upper()
            extra = f" rPnL {fill.realized_pnl:+.2f}" if fill.side is Side.SELL else ""
            lines.append(
                f"  #{fill.seq} {verb} {fill.quantity:g} {fill.symbol} @ {fill.price:.2f}{extra}"
            )
        return "\n".join(lines)

    def _handle_risk(self) -> str:
        lines = ["Risk limits:"]
        lines.extend(f"  {line}" for line in self.limits.describe())
        open_count = len(self.account.positions)
        if self.limits.max_open_positions is not None:
            lines.append(f"  Usage: {open_count}/{self.limits.max_open_positions} positions open")
        else:
            lines.append(f"  Usage: {open_count} positions open")
        return "\n".join(lines)

    @staticmethod
    def _handle_help() -> str:
        return (
            "Commands:\n"
            "  /buy <SYM> <QTY>   buy at market\n"
            "  /sell <SYM> <QTY>  sell at market\n"
            "  /price <SYM>       quote a symbol\n"
            "  /balance           cash + holdings\n"
            "  /positions         open positions w/ cost basis\n"
            "  /portfolio         full mark-to-market table\n"
            "  /pnl               realized + unrealized PnL\n"
            "  /history [N]       recent fills\n"
            "  /risk              active risk limits\n"
            "  /help              this message"
        )


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
