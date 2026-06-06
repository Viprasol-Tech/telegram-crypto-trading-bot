"""A paper-trading account: cash, positions, cost basis, PnL, and a fill ledger.

No real exchange, no real money — every fill executes against a price you
supply, so the bot can be exercised end-to-end without API keys or risk.

The account tracks **average cost basis** per symbol so it can report both
**realized** PnL (locked in on sells) and **unrealized** PnL (mark-to-market on
open positions). Every fill is appended to an immutable :class:`Fill` ledger,
which powers ``/history`` and the portfolio view.

Part of Telegram Crypto Trading Bot by Viprasol Tech Private Limited
(https://viprasol.com).
"""

from __future__ import annotations

from dataclasses import dataclass

from telegram_crypto_trading_bot.commands import Side


class InsufficientFundsError(ValueError):
    """Raised when a buy would cost more cash than the account holds."""


class InsufficientPositionError(ValueError):
    """Raised when a sell exceeds the quantity currently held."""


@dataclass(frozen=True, slots=True)
class Fill:
    """An immutable record of a single executed paper trade.

    Args:
        side: Direction of the fill (:attr:`Side.BUY` or :attr:`Side.SELL`).
        symbol: Upper-cased ticker that was traded.
        quantity: Units filled (always strictly positive).
        price: Per-unit fill price.
        cash_delta: Signed change to cash (negative on buys, positive on sells).
        realized_pnl: Realized profit/loss locked in by this fill (sells only).
        seq: Monotonic 1-based sequence number within the owning account.
    """

    side: Side
    symbol: str
    quantity: float
    price: float
    cash_delta: float
    realized_pnl: float
    seq: int

    @property
    def notional(self) -> float:
        """Absolute traded value (``quantity * price``)."""
        return self.quantity * self.price


@dataclass(slots=True)
class Position:
    """An open spot position with running average cost basis.

    Args:
        quantity: Units currently held (strictly positive while open).
        avg_price: Volume-weighted average entry price.
    """

    quantity: float
    avg_price: float

    @property
    def cost_basis(self) -> float:
        """Total capital tied up in this position (``quantity * avg_price``)."""
        return self.quantity * self.avg_price

    def market_value(self, price: float) -> float:
        """Mark-to-market value of the position at ``price``."""
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        """Unrealized profit/loss at ``price`` versus average cost."""
        return (price - self.avg_price) * self.quantity


class PaperAccount:
    """A simulated cash + spot account with cost-basis and PnL accounting.

    Args:
        cash: Starting quote-currency balance (e.g. USD). Must be non-negative.

    Raises:
        ValueError: If ``cash`` is negative.
    """

    def __init__(self, cash: float = 10_000.0) -> None:
        if cash < 0:
            raise ValueError("starting cash must be non-negative")
        self._starting_cash: float = float(cash)
        self._cash: float = float(cash)
        self._positions: dict[str, Position] = {}
        self._realized_pnl: float = 0.0
        self._fills: list[Fill] = []

    @property
    def cash(self) -> float:
        """Current free quote-currency balance."""
        return self._cash

    @property
    def starting_cash(self) -> float:
        """The cash the account was opened with."""
        return self._starting_cash

    @property
    def realized_pnl(self) -> float:
        """Cumulative realized profit/loss locked in across all sells."""
        return self._realized_pnl

    @property
    def positions(self) -> dict[str, float]:
        """A copy of held positions, mapping symbol -> quantity."""
        return {sym: pos.quantity for sym, pos in self._positions.items()}

    @property
    def open_positions(self) -> dict[str, Position]:
        """A shallow copy of the rich :class:`Position` objects, keyed by symbol."""
        return dict(self._positions)

    @property
    def fills(self) -> list[Fill]:
        """A copy of the chronological fill ledger."""
        return list(self._fills)

    def position(self, symbol: str) -> float:
        """Return the quantity held for ``symbol`` (0.0 if none)."""
        pos = self._positions.get(symbol.upper())
        return pos.quantity if pos else 0.0

    def avg_price(self, symbol: str) -> float:
        """Return the average cost basis for ``symbol`` (0.0 if none)."""
        pos = self._positions.get(symbol.upper())
        return pos.avg_price if pos else 0.0

    def buy(self, symbol: str, quantity: float, price: float) -> float:
        """Buy ``quantity`` of ``symbol`` at ``price``, paying from cash.

        Updates the average cost basis and appends a :class:`Fill`.

        Args:
            symbol: Ticker to buy (case-insensitive).
            quantity: Units to buy; must be strictly positive.
            price: Per-unit price; must be strictly positive.

        Returns:
            The total cost debited from cash.

        Raises:
            ValueError: If ``quantity`` or ``price`` is not positive.
            InsufficientFundsError: If the cost exceeds available cash.
        """
        self._validate(quantity, price)
        cost = quantity * price
        if cost > self._cash:
            raise InsufficientFundsError(f"need {cost:.2f} but only {self._cash:.2f} available")
        key = symbol.upper()
        self._cash -= cost
        existing = self._positions.get(key)
        if existing is None:
            self._positions[key] = Position(quantity=quantity, avg_price=price)
        else:
            total_qty = existing.quantity + quantity
            existing.avg_price = (existing.cost_basis + cost) / total_qty
            existing.quantity = total_qty
        self._record(Side.BUY, key, quantity, price, cash_delta=-cost, realized=0.0)
        return cost

    def sell(self, symbol: str, quantity: float, price: float) -> float:
        """Sell ``quantity`` of ``symbol`` at ``price``, crediting cash.

        Realizes PnL against the average cost basis and appends a :class:`Fill`.

        Args:
            symbol: Ticker to sell (case-insensitive).
            quantity: Units to sell; must be strictly positive.
            price: Per-unit price; must be strictly positive.

        Returns:
            The total proceeds credited to cash.

        Raises:
            ValueError: If ``quantity`` or ``price`` is not positive.
            InsufficientPositionError: If ``quantity`` exceeds the held amount.
        """
        self._validate(quantity, price)
        key = symbol.upper()
        pos = self._positions.get(key)
        held = pos.quantity if pos else 0.0
        if pos is None or quantity > held:
            raise InsufficientPositionError(
                f"holding {held:g} {key} but tried to sell {quantity:g}"
            )
        proceeds = quantity * price
        realized = (price - pos.avg_price) * quantity
        self._cash += proceeds
        self._realized_pnl += realized
        remaining = held - quantity
        if remaining > 0:
            pos.quantity = remaining
        else:
            self._positions.pop(key, None)
        self._record(Side.SELL, key, quantity, price, cash_delta=proceeds, realized=realized)
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        """Total account value: cash plus positions marked at ``prices``.

        Args:
            prices: Mapping of symbol -> mark price. Symbols absent from the
                mapping are valued at zero.

        Returns:
            Cash plus the sum of ``quantity * price`` over all positions.
        """
        marked = sum(pos.quantity * prices.get(sym, 0.0) for sym, pos in self._positions.items())
        return self._cash + marked

    def unrealized_pnl(self, prices: dict[str, float]) -> float:
        """Total mark-to-market PnL across open positions at ``prices``.

        Args:
            prices: Mapping of symbol -> mark price. Symbols absent from the
                mapping are marked at their average cost (zero contribution).
        """
        total = 0.0
        for sym, pos in self._positions.items():
            mark = prices.get(sym, pos.avg_price)
            total += pos.unrealized_pnl(mark)
        return total

    def total_pnl(self, prices: dict[str, float]) -> float:
        """Realized plus unrealized PnL at ``prices``."""
        return self._realized_pnl + self.unrealized_pnl(prices)

    @staticmethod
    def _validate(quantity: float, price: float) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")

    def _record(
        self,
        side: Side,
        symbol: str,
        quantity: float,
        price: float,
        *,
        cash_delta: float,
        realized: float,
    ) -> None:
        self._fills.append(
            Fill(
                side=side,
                symbol=symbol,
                quantity=quantity,
                price=price,
                cash_delta=cash_delta,
                realized_pnl=realized,
                seq=len(self._fills) + 1,
            )
        )


@dataclass(frozen=True, slots=True)
class PortfolioRow:
    """A single symbol's line in a portfolio snapshot.

    Args:
        symbol: Upper-cased ticker.
        quantity: Units held.
        avg_price: Average entry price.
        mark: Current mark price used for valuation.
        market_value: ``quantity * mark``.
        unrealized_pnl: Mark-to-market PnL versus average cost.
    """

    symbol: str
    quantity: float
    avg_price: float
    mark: float
    market_value: float
    unrealized_pnl: float

    @property
    def unrealized_pct(self) -> float:
        """Unrealized PnL as a percentage of cost basis (0.0 if no basis)."""
        basis = self.quantity * self.avg_price
        return (self.unrealized_pnl / basis) * 100.0 if basis else 0.0


@dataclass(frozen=True, slots=True)
class Portfolio:
    """An immutable mark-to-market snapshot of an account.

    Args:
        cash: Free cash at snapshot time.
        rows: Per-symbol :class:`PortfolioRow` entries (sorted by symbol).
        realized_pnl: Cumulative realized PnL.
        starting_cash: Cash the account opened with.
    """

    cash: float
    rows: tuple[PortfolioRow, ...]
    realized_pnl: float
    starting_cash: float = 0.0

    @property
    def positions_value(self) -> float:
        """Total market value of all open positions."""
        return sum(row.market_value for row in self.rows)

    @property
    def equity(self) -> float:
        """Cash plus positions value."""
        return self.cash + self.positions_value

    @property
    def unrealized_pnl(self) -> float:
        """Total unrealized PnL across rows."""
        return sum(row.unrealized_pnl for row in self.rows)

    @property
    def total_pnl(self) -> float:
        """Realized plus unrealized PnL."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def total_return_pct(self) -> float:
        """Total PnL as a percentage of starting cash (0.0 if none)."""
        return (self.total_pnl / self.starting_cash) * 100.0 if self.starting_cash else 0.0


def build_portfolio(account: PaperAccount, prices: dict[str, float]) -> Portfolio:
    """Build a :class:`Portfolio` snapshot of ``account`` marked at ``prices``.

    Args:
        account: The account to snapshot.
        prices: Mapping of symbol -> mark price. Symbols absent from the mapping
            are marked at their average cost.

    Returns:
        An immutable :class:`Portfolio` with one row per open position.
    """
    rows = tuple(
        PortfolioRow(
            symbol=sym,
            quantity=pos.quantity,
            avg_price=pos.avg_price,
            mark=(mark := prices.get(sym, pos.avg_price)),
            market_value=pos.market_value(mark),
            unrealized_pnl=pos.unrealized_pnl(mark),
        )
        for sym, pos in sorted(account.open_positions.items())
    )
    return Portfolio(
        cash=account.cash,
        rows=rows,
        realized_pnl=account.realized_pnl,
        starting_cash=account.starting_cash,
    )
