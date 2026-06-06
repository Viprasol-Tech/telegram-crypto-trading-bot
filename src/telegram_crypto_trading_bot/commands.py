"""Parse Telegram text commands into typed :class:`Command` objects.

Supported commands::

    /buy BTC 0.5      -> Trade(side=BUY, symbol="BTC", quantity=0.5)
    /sell BTC 0.5     -> Trade(side=SELL, symbol="BTC", quantity=0.5)
    /balance          -> Balance()
    /price BTC        -> Price(symbol="BTC")
    /positions        -> Positions()
    /portfolio        -> ShowPortfolio()
    /pnl              -> Pnl()
    /history          -> History(limit=None)
    /history 5        -> History(limit=5)
    /risk             -> ShowRisk()
    /help             -> Help()

Malformed input raises :class:`CommandError`.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class CommandError(ValueError):
    """Raised when a text command cannot be parsed into a valid command."""


class Side(str, Enum):
    """Trade direction."""

    BUY = "buy"
    SELL = "sell"


class Command(BaseModel):
    """Base class for all parsed commands."""

    model_config = ConfigDict(frozen=True)


class Trade(Command):
    """A buy or sell order for ``quantity`` units of ``symbol``."""

    side: Side
    symbol: str
    quantity: float


class Balance(Command):
    """A request to show cash and a compact list of holdings."""


class Price(Command):
    """A request for the current price of ``symbol``."""

    symbol: str


class Positions(Command):
    """A request to list open positions with cost basis."""


class ShowPortfolio(Command):
    """A request for a full mark-to-market portfolio table."""


class Pnl(Command):
    """A request for realized + unrealized profit/loss."""


class History(Command):
    """A request for recent fills, optionally capped at ``limit`` rows."""

    limit: int | None = None


class ShowRisk(Command):
    """A request to display the active risk limits and current usage."""


class Help(Command):
    """A request for the command reference."""


def _normalize_symbol(raw: str) -> str:
    """Validate and upper-case a ticker symbol.

    Args:
        raw: The raw symbol token (e.g. ``"btc"``).

    Returns:
        The upper-cased symbol (e.g. ``"BTC"``).

    Raises:
        CommandError: If ``raw`` is not a plain alphanumeric ticker.
    """
    symbol = raw.strip().upper()
    if not symbol or not symbol.isalnum():
        raise CommandError(f"invalid symbol: {raw!r}")
    return symbol


def _parse_quantity(raw: str) -> float:
    """Parse and validate a positive trade quantity.

    Args:
        raw: The raw quantity token (e.g. ``"0.5"``).

    Returns:
        The parsed quantity as a float.

    Raises:
        CommandError: If ``raw`` is not a finite, strictly-positive number.
    """
    try:
        quantity = float(raw)
    except ValueError as exc:
        raise CommandError(f"invalid quantity: {raw!r}") from exc
    if quantity != quantity or quantity in (float("inf"), float("-inf")):
        raise CommandError(f"invalid quantity: {raw!r}")
    if quantity <= 0:
        raise CommandError(f"quantity must be positive: {raw!r}")
    return quantity


def _parse_limit(raw: str) -> int:
    """Parse and validate a positive integer row limit.

    Args:
        raw: The raw limit token (e.g. ``"5"``).

    Returns:
        The parsed limit as an int.

    Raises:
        CommandError: If ``raw`` is not a strictly-positive integer.
    """
    try:
        limit = int(raw)
    except ValueError as exc:
        raise CommandError(f"invalid limit: {raw!r}") from exc
    if limit <= 0:
        raise CommandError(f"limit must be positive: {raw!r}")
    return limit


def _parse_trade(verb: str, args: list[str]) -> Trade:
    if len(args) != 2:
        raise CommandError(f"/{verb} expects: /{verb} <SYMBOL> <QUANTITY>")
    side = Side.BUY if verb == "buy" else Side.SELL
    return Trade(
        side=side,
        symbol=_normalize_symbol(args[0]),
        quantity=_parse_quantity(args[1]),
    )


def _parse_history(args: list[str]) -> History:
    if len(args) > 1:
        raise CommandError("/history expects: /history [LIMIT]")
    limit = _parse_limit(args[0]) if args else None
    return History(limit=limit)


def _no_args(verb: str, args: list[str], command: Command) -> Command:
    if args:
        raise CommandError(f"/{verb} takes no arguments")
    return command


def parse_command(text: str) -> Command:
    """Parse a single Telegram text command into a typed :class:`Command`.

    Args:
        text: The raw message text, e.g. ``"/buy BTC 0.5"``. A leading slash
            is optional and surrounding whitespace is ignored.

    Returns:
        A concrete :class:`Command` instance.

    Raises:
        CommandError: If the text is empty, the verb is unknown, or the
            arguments do not match the command's expected shape.
    """
    stripped = text.strip()
    if not stripped:
        raise CommandError("empty command")

    tokens = stripped.split()
    verb = tokens[0].lstrip("/").lower()
    args = tokens[1:]

    if verb in ("buy", "sell"):
        return _parse_trade(verb, args)
    if verb == "price":
        if len(args) != 1:
            raise CommandError("/price expects: /price <SYMBOL>")
        return Price(symbol=_normalize_symbol(args[0]))
    if verb == "history":
        return _parse_history(args)
    if verb == "balance":
        return _no_args(verb, args, Balance())
    if verb in ("positions", "pos"):
        return _no_args("positions", args, Positions())
    if verb in ("portfolio", "port"):
        return _no_args("portfolio", args, ShowPortfolio())
    if verb == "pnl":
        return _no_args(verb, args, Pnl())
    if verb == "risk":
        return _no_args(verb, args, ShowRisk())
    if verb in ("help", "start"):
        return _no_args("help", args, Help())

    raise CommandError(f"unknown command: {tokens[0]!r}")
